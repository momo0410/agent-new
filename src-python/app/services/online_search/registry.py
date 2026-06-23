"""OnlineSearchService —— 联网检索统一入口

职责：
  - 暴露 4 个检索方法：search_cve / search_exploit / lookup_msf_module / lookup_default_creds
  - 三级缓存（委托给 OnlineSearchCache）
  - 每次渗透预算控制（默认最多 10 次联网查询）
  - 同一查询同次渗透去重（同一 CVE 最多查 1 次）
  - 离线兜底：任何失败都返回带 error 字段的结构，不抛异常

设计原则（见 handoff-03 第四节）：
  联网检索不是替代本地 skill，而是本地 skill 缺失时的补充 + 反哺 skill 生成。
"""
from __future__ import annotations

import os
import time
from typing import Any, Optional

from .cache import OnlineSearchCache, stable_cache_key
from .nvd_client import NvdClient
from .msf_module_client import MsfModuleClient


def _default_l2_cache_dir() -> str:
    """L2 磁盘缓存默认目录：用户家目录下 .cache/sdit/online_search"""
    return os.path.join(os.path.expanduser("~"), ".cache", "sdit", "online_search")


def _default_l3_cache_dir(skills_root: str) -> str:
    """L3 永久缓存默认目录：skills/knowledge_base/"""
    return os.path.join(skills_root, "knowledge_base")


class OnlineSearchService:
    """联网检索统一服务。

    一次渗透测试生命周期内共享一个实例。
    """

    # 4 个对外工具名（与 tool_registry / builtin skill 对应）
    TOOL_NAMES = ("search_cve", "search_exploit", "lookup_msf_module", "lookup_default_creds")

    def __init__(
        self,
        skills_root: Optional[str] = None,
        enabled: bool = True,
        max_calls_per_pentest: int = 10,
        timeout_seconds: int = 15,
        l2_cache_dir: Optional[str] = None,
        l3_cache_dir: Optional[str] = None,
        vulners_api_key: str = "",
        shodan_api_key: str = "",
    ):
        self.skills_root = skills_root or os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "..", "skills"
        )
        self.enabled = enabled
        self.max_calls = max_calls_per_pentest
        self.timeout = timeout_seconds
        self.vulners_api_key = vulners_api_key
        self.shodan_api_key = shodan_api_key

        self._cache = OnlineSearchCache(
            l2_dir=l2_cache_dir or _default_l2_cache_dir(),
            l3_dir=l3_cache_dir or _default_l3_cache_dir(self.skills_root),
        )
        self._nvd = NvdClient(timeout=timeout_seconds)

        # 预算与去重
        self._calls_made = 0
        self._queried_keys: set[str] = set()
        # 检索结果留底，供 SkillGenerator 自升级闭环使用
        self._results_log: list[dict[str, Any]] = []

    # ── 状态查询 ──────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "calls_made": self._calls_made,
            "calls_remaining": max(0, self.max_calls - self._calls_made),
            "max_calls": self.max_calls,
            "unique_queries": len(self._queried_keys),
            "l2_cache_size": self._cache.l2_size(),
            "results_logged": len(self._results_log),
        }

    def get_results_log(self) -> list[dict[str, Any]]:
        """返回本次渗透所有联网检索结果（供 SkillGenerator 注入 prompt）。"""
        return list(self._results_log)

    def clear_l2_cache(self) -> int:
        return self._cache.clear_l2()

    def test_connectivity(self) -> dict[str, Any]:
        """测试 NVD 连通性（不计入预算）。"""
        try:
            result = self._nvd.get_cve("CVE-2021-44228")  # Log4Shell，稳定存在
            if result:
                return {"ok": True, "sample_cve": result.get("cve_id", "")}
            return {"ok": False, "error": "NVD 返回空结果"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── 工具 1: search_cve（增强版）───────────────────────
    def search_cve(self, cve_id: str) -> dict[str, Any]:
        """查询 CVE 详情，并附加 exploit 利用信息。

        返回：
          - NVD 权威数据（CVSS、描述、影响版本、参考链接）
          - 附加 MSF 模块匹配（如果有）
          - 利用建议（如果有对应 exploit）
        """
        cve_id = str(cve_id or "").strip()
        if not cve_id:
            return self._error_result("search_cve", "cve_id 为空", cve_id)

        cache_key = stable_cache_key("cve", cve_id.upper())
        ns = "cve"

        # 缓存命中
        cached = self._cache.get(ns, cache_key)
        if cached is not None:
            return self._ok_result("search_cve", cached, from_cache=True, query=cve_id)

        if not self.enabled:
            return self._disabled_result("search_cve", cve_id)

        if not self._budget_available("search_cve", cve_id):
            return self._budget_exceeded_result("search_cve", cve_id)

        result = self._nvd.get_cve(cve_id)
        if result is None:
            return self._error_result(
                "search_cve", f"NVD 查询失败或无此 CVE: {cve_id}", cve_id
            )

        # 附加 exploit 利用信息
        self._enrich_cve_with_exploit_info(cve_id, result)

        # CVE 信息不变，写入 L3 永久缓存
        self._cache.put(ns, cache_key, result, permanent=True)
        return self._ok_result("search_cve", result, from_cache=False, query=cve_id)

    def _enrich_cve_with_exploit_info(self, cve_id: str, cve_data: dict) -> None:
        """给 CVE 数据中附加 exploit 利用信息（副作用修改 cve_data）。"""
        msf_mod = MsfModuleClient.match_cve_to_module(cve_id)
        if msf_mod:
            cve_data["msf_module"] = msf_mod.get("module_name", "")
            cve_data["msf_description"] = msf_mod.get("description", "")
            cve_data["msf_payloads"] = msf_mod.get("payloads", [])
            cve_data["msf_command"] = MsfModuleClient.gen_msf_command(
                msf_mod["module_name"]
            )
            cve_data["exploit_available"] = True
            cve_data["exploit_references"] = msf_mod.get("references", [])
        else:
            cve_data["exploit_available"] = False

    # ── 工具 2: search_exploit（增强版）────────────────────
    def search_exploit(self, keyword: str, search_mode: str = "exploit_db") -> dict[str, Any]:
        """搜索公开 exploit。返回可操作的渗透指南。

        输入：服务名+版本（如 "vsftpd 2.3.4" "tomcat 6.x"）
        返回：每个匹配 CVE 的漏洞原理、MSF 模块、利用步骤、可执行命令。
        """
        keyword = str(keyword or "").strip()
        if not keyword:
            return self._error_result("search_exploit", "keyword 为空", keyword)

        cache_key = stable_cache_key("exploit", keyword.lower(), search_mode)
        cached = self._cache.get("exploit", cache_key)
        if cached is not None:
            return self._ok_result("search_exploit", cached, from_cache=True, query=keyword)

        if not self.enabled:
            return self._disabled_result("search_exploit", keyword)

        if not self._budget_available("search_exploit", keyword):
            return self._budget_exceeded_result("search_exploit", keyword)

        # 1. NVD 关键词搜索（覆盖"服务版本 -> 已知 CVE"场景）
        raw_cves = self._nvd.search_by_keyword(keyword, max_results=10)

        # 2. 从离线 MSF 知识库匹配相关模块
        msf_matches = MsfModuleClient.search_offline_by_keyword(keyword)

        # 3. 对每个 CVE 补全 exploit 信息
        enriched_cves: list[dict[str, Any]] = []
        for cve in raw_cves:
            cve_id = cve.get("cve_id", "")
            enriched = dict(cve)

            # 尝试匹配 MSF 模块
            msf_mod = MsfModuleClient.match_cve_to_module(cve_id)
            if msf_mod:
                enriched["msf_module"] = msf_mod.get("module_name", "")
                enriched["msf_description"] = msf_mod.get("description", "")
                enriched["msf_payloads"] = msf_mod.get("payloads", [])
                enriched["msf_command"] = MsfModuleClient.gen_msf_command(
                    msf_mod["module_name"]
                )
                enriched["exploit_available"] = True
                enriched["principle_cn"] = msf_mod.get("description", cve.get("description", ""))
            else:
                enriched["exploit_available"] = False
                enriched["principle_cn"] = cve.get("description", "")

            enriched_cves.append(enriched)

        # 4. 从 MSF 匹配中提取没有对应 CVE 的模块（补充信息）
        extra_msf = []
        for m in msf_matches:
            module_cves = [r for r in m.get("references", []) if r.startswith("CVE-")]
            if not any(e.get("cve_id") in module_cves for e in enriched_cves):
                extra_msf.append(m)

        # 5. 生成渗透指南摘要
        guide = self._build_exploit_guide(keyword, enriched_cves, extra_msf)

        data = {
            "keyword": keyword,
            "search_mode": search_mode,
            "cve_matches": enriched_cves,
            "count": len(enriched_cves),
            "extra_msf_modules": extra_msf,
            "exploit_guide": guide,
            "source": "NVD-keyword + MSF-offline-KB",
        }
        self._cache.put("exploit", cache_key, data)
        return self._ok_result("search_exploit", data, from_cache=False, query=keyword)

    def _build_exploit_guide(
        self, keyword: str, enriched_cves: list[dict], extra_msf: list[dict]
    ) -> str:
        """生成渗透指南文本摘要。"""
        lines = [f"服务: {keyword}", ""]

        if enriched_cves:
            lines.append(f"发现 {len(enriched_cves)} 个相关 CVE:")
            for c in enriched_cves:
                cve_id = c.get("cve_id", "?")
                cvss = c.get("cvss_score", "?")
                sev = c.get("cvss_severity", "?")
                exploit_tag = "[有公开利用]" if c.get("exploit_available") else "[仅CVE]"
                desc = c.get("principle_cn", c.get("description", ""))[:150]
                lines.append(f"  {exploit_tag} {cve_id} CVSS={cvss}({sev})")
                lines.append(f"    原理: {desc}")
                if c.get("msf_module"):
                    lines.append(f"    MSF: {c['msf_module']}")
                    lines.append(f"    命令: {c.get('msf_command','')[:120]}")
                lines.append("")
        else:
            lines.append("NVD 关键词搜索未匹配到已知 CVE，可尝试更精确的关键词。")

        if extra_msf:
            lines.append(f"此外，离线 MSF 知识库匹配到 {len(extra_msf)} 个相关模块:")
            for m in extra_msf:
                lines.append(f"  - {m.get('module_name','')}: {m.get('description','')[:100]}")
                lines.append(f"    命令: {MsfModuleClient.gen_msf_command(m['module_name'])}")
            lines.append("")

        lines.append("提示: 本地 searchsploit 应为首选（由 Executor 执行 shell 命令），")
        lines.append("联网检索是当本地无匹配时的补充。")

        return "\n".join(lines)

    # ── 工具 3: lookup_msf_module ─────────────────────────
    def lookup_msf_module(self, module_name: str) -> dict[str, Any]:
        """查询 Metasploit 模块文档（Rapid7 db）。"""
        module_name = str(module_name or "").strip()
        if not module_name:
            return self._error_result("lookup_msf_module", "module_name 为空", module_name)

        cache_key = stable_cache_key("msf", module_name.lower())
        cached = self._cache.get("msf", cache_key)
        if cached is not None:
            return self._ok_result("lookup_msf_module", cached, from_cache=True, query=module_name)

        if not self.enabled:
            return self._disabled_result("lookup_msf_module", module_name)

        if not self._budget_available("lookup_msf_module", module_name):
            return self._budget_exceeded_result("lookup_msf_module", module_name)

        # 延迟导入，避免循环依赖；离线时模块不存在也不影响
        try:
            from .msf_module_client import MsfModuleClient  # type: ignore
            client = MsfModuleClient(timeout=self.timeout)
            data = client.lookup(module_name)
        except Exception as e:
            data = {
                "module_name": module_name,
                "error": f"MSF 模块查询不可用: {e}",
                "source": "rapid7",
                "fallback_advice": (
                    f"可手动执行: msfconsole -q -x 'use {module_name}; info; exit -y' "
                    f"查看模块说明"
                ),
            }

        if data:
            self._cache.put("msf", cache_key, data)
            return self._ok_result("lookup_msf_module", data, from_cache=False, query=module_name)
        return self._error_result("lookup_msf_module", f"未找到模块: {module_name}", module_name)

    # ── 工具 4: lookup_default_creds ──────────────────────
    def lookup_default_creds(self, product: str) -> dict[str, Any]:
        """查询设备/软件默认密码。"""
        product = str(product or "").strip()
        if not product:
            return self._error_result("lookup_default_creds", "product 为空", product)

        cache_key = stable_cache_key("creds", product.lower())
        cached = self._cache.get("creds", cache_key)
        if cached is not None:
            return self._ok_result("lookup_default_creds", cached, from_cache=True, query=product)

        if not self.enabled:
            return self._disabled_result("lookup_default_creds", product)

        if not self._budget_available("lookup_default_creds", product):
            return self._budget_exceeded_result("lookup_default_creds", product)

        try:
            from .default_creds_client import DefaultCredsClient  # type: ignore
            client = DefaultCredsClient(timeout=self.timeout)
            data = client.lookup(product)
        except Exception as e:
            data = {
                "product": product,
                "error": f"默认密码查询不可用: {e}",
                "source": "cirt.net",
                "fallback_advice": (
                    f"可手动查: https://cirt.net/passwords?criteria={product} "
                    f"或本地 /usr/share/wordlists/ 下的默认密码表"
                ),
            }

        if data:
            self._cache.put("creds", cache_key, data)
            return self._ok_result("lookup_default_creds", data, from_cache=False, query=product)
        return self._error_result("lookup_default_creds", f"未找到: {product}", product)

    # ── 通用分发（供 agent 按工具名调用）────────────────
    def call(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """按工具名 + 参数字典统一分发。供 Agent 拦截层调用。"""
        tool_name = str(tool_name or "").strip().lower()
        try:
            if tool_name == "search_cve":
                return self.search_cve(args.get("cve_id", ""))
            if tool_name == "search_exploit":
                return self.search_exploit(
                    args.get("keyword", ""),
                    search_mode=str(args.get("search_mode", "exploit_db")),
                )
            if tool_name == "lookup_msf_module":
                return self.lookup_msf_module(args.get("module_name", ""))
            if tool_name == "lookup_default_creds":
                return self.lookup_default_creds(args.get("product", ""))
        except Exception as e:
            return {
                "tool": tool_name,
                "ok": False,
                "error": f"调用异常: {e}",
                "offline_mode": True,
            }
        return {
            "tool": tool_name,
            "ok": False,
            "error": f"未知联网检索工具: {tool_name}",
        }

    @staticmethod
    def is_online_search_tool(tool_name: str) -> bool:
        return str(tool_name or "").strip().lower() in OnlineSearchService.TOOL_NAMES

    # ── 内部：预算 / 去重 / 结果封装 ──────────────────────
    def _budget_available(self, tool: str, query: str) -> bool:
        dedup_key = f"{tool}:{str(query).strip().lower()}"
        if dedup_key in self._queried_keys:
            return False  # 同次渗透同一查询去重
        if self._calls_made >= self.max_calls:
            return False
        self._queried_keys.add(dedup_key)
        self._calls_made += 1
        return True

    def _ok_result(
        self, tool: str, data: dict[str, Any], from_cache: bool, query: str = ""
    ) -> dict[str, Any]:
        result = {
            "tool": tool,
            "ok": True,
            "from_cache": from_cache,
            "query": query,
            "data": data,
            "timestamp": time.time(),
        }
        if not from_cache:
            self._results_log.append(result)
        return result

    def _error_result(self, tool: str, error: str, query: str = "") -> dict[str, Any]:
        return {
            "tool": tool,
            "ok": False,
            "error": error,
            "query": query,
            "offline_mode": True,
        }

    def _disabled_result(self, tool: str, query: str = "") -> dict[str, Any]:
        return {
            "tool": tool,
            "ok": False,
            "error": "联网检索已禁用",
            "query": query,
            "offline_mode": True,
        }

    def _budget_exceeded_result(self, tool: str, query: str = "") -> dict[str, Any]:
        return {
            "tool": tool,
            "ok": False,
            "error": (
                f"本次渗透联网检索预算已用尽 ({self.max_calls} 次)。"
                f"已有结果仍可从缓存复用。"
            ),
            "query": query,
            "budget_exceeded": True,
        }


# ── 单例工厂 ──────────────────────────────────────────────
_singleton: Optional[OnlineSearchService] = None


def get_online_search_service(
    skills_root: Optional[str] = None,
    **kwargs: Any,
) -> OnlineSearchService:
    """获取 OnlineSearchService 单例。每次渗透开始时调用 reset() 重建。"""
    global _singleton
    if _singleton is None:
        _singleton = OnlineSearchService(skills_root=skills_root, **kwargs)
    return _singleton


def reset_online_search_service() -> None:
    """重置单例（每次新渗透开始时调用，清空预算与去重状态）。"""
    global _singleton
    _singleton = None
