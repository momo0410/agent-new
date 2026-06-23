"""Metasploit 模块文档客户端

数据源: Rapid7 db (https://www.rapid7.com/db/modules/)
- 无需 API Key
- 无官方 JSON API，通过页面抓取 + 结构化兜底

设计：
  - 优先返回结构化的模块信息（描述、rank、参考链接、常用选项）
  - 在线抓取失败时返回 msfconsole 手动查询命令作为兜底
  - 模块名格式: exploit/unix/ftp/vsftpd_234_backdoor
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

_RAPID7_BASE = "https://www.rapid7.com/db/modules/"
_USER_AGENT = "SDIT-PentestAgent/1.0 (security research)"


# 常见 MSF 模块的离线知识库（在线抓取失败时兜底）
# 仅收录渗透测试高频模块，避免维护成本
_OFFLINE_MODULE_KB: dict[str, dict[str, Any]] = {
    "exploit/unix/ftp/vsftpd_234_backdoor": {
        "module_name": "exploit/unix/ftp/vsftpd_234_backdoor",
        "description": "vsftpd 2.3.4 后门利用。发送含 :) 的用户名触发 6200 端口 bindshell。",
        "rank": "excellent",
        "references": ["CVE-2011-2523", "EDB-17491"],
        "options": [
            {"name": "RHOSTS", "required": True, "description": "目标主机"},
            {"name": "RPORT", "required": True, "default": "21", "description": "FTP 端口"},
        ],
        "payloads": ["cmd/unix/interact", "cmd/unix/reverse"],
    },
    "exploit/multi/samba/usermap_script": {
        "module_name": "exploit/multi/samba/usermap_script",
        "description": "Samba 3.0.20-25 usermap script 命令注入 (CVE-2007-2447)。",
        "rank": "excellent",
        "references": ["CVE-2007-2447", "EDB-16320"],
        "options": [
            {"name": "RHOSTS", "required": True, "description": "目标主机"},
            {"name": "RPORT", "required": True, "default": "139", "description": "SMB 端口"},
        ],
        "payloads": ["cmd/unix/reverse", "cmd/unix/reverse_netcat"],
    },
    "exploit/unix/irc/unreal_ircd_3281_backdoor": {
        "module_name": "exploit/unix/irc/unreal_ircd_3281_backdoor",
        "description": "UnrealIRCd 3.2.8.1 后门。源码包被植入 AB; 命令执行。",
        "rank": "excellent",
        "references": ["CVE-2010-2075", "EDB-13853"],
        "options": [{"name": "RHOSTS", "required": True}, {"name": "RPORT", "default": "6667"}],
        "payloads": ["cmd/unix/reverse", "cmd/unix/reverse_perl"],
    },
    "exploit/unix/misc/distcc_exec": {
        "module_name": "exploit/unix/misc/distcc_exec",
        "description": "distcc 命令执行 (CVE-2004-2687)。",
        "rank": "excellent",
        "references": ["CVE-2004-2687", "EDB-9915"],
        "options": [{"name": "RHOSTS", "required": True}, {"name": "RPORT", "default": "3632"}],
        "payloads": ["cmd/unix/reverse", "cmd/unix/reverse_netcat"],
    },
    "exploit/linux/postgres/postgres_copy_from_program": {
        "module_name": "exploit/linux/postgres/postgres_copy_from_program",
        "description": "PostgreSQL COPY FROM PROGRAM 命令执行 (CVE-2019-9193)。",
        "rank": "manual",
        "references": ["CVE-2019-9193"],
        "options": [
            {"name": "RHOSTS", "required": True},
            {"name": "USERNAME", "default": "postgres"},
            {"name": "PASSWORD", "required": True},
            {"name": "DATABASE", "default": "template1"},
        ],
        "payloads": ["cmd/unix/reverse_perl"],
    },
    "exploit/multi/http/php_cgi_arg_injection": {
        "module_name": "exploit/multi/http/php_cgi_arg_injection",
        "description": "PHP CGI 参数注入 (CVE-2012-1823)。",
        "rank": "excellent",
        "references": ["CVE-2012-1823", "EDB-18486"],
        "options": [{"name": "RHOSTS", "required": True}, {"name": "RPORT", "default": "80"}],
        "payloads": ["php/meterpreter/reverse_tcp", "cmd/unix/reverse"],
    },
}


class MsfModuleClient:
    """Metasploit 模块文档查询（Rapid7 + 离线兜底）。"""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    def lookup(self, module_name: str) -> dict[str, Any]:
        """查询 MSF 模块文档。

        Args:
            module_name: 模块全名，如 exploit/unix/ftp/vsftpd_234_backdoor

        Returns:
            模块信息字典。在线失败时返回离线兜底 + 手动查询命令。
        """
        module_name = str(module_name or "").strip().lower()
        if not module_name:
            return {"module_name": "", "error": "模块名为空"}

        # 1. 离线知识库优先（已收录的高频模块秒回，不耗网络）
        if module_name in _OFFLINE_MODULE_KB:
            data = dict(_OFFLINE_MODULE_KB[module_name])
            data["source"] = "offline-kb"
            data["rapid7_url"] = _RAPID7_BASE + module_name.replace("/", "/")
            return data

        # 2. 在线抓取 Rapid7 页面
        online_data = self._fetch_rapid7(module_name)
        if online_data:
            online_data["source"] = "rapid7"
            return online_data

        # 3. 兜底：返回结构化建议 + 手动查询命令
        return {
            "module_name": module_name,
            "description": "在线查询失败，模块未在离线知识库中。",
            "rapid7_url": _RAPID7_BASE + module_name.replace("/", "/") if "/" in module_name else "",
            "source": "fallback",
            "manual_command": (
                f"msfconsole -q -x 'use {module_name}; info; exit -y'"
            ),
            "fallback_advice": (
                f"执行上述 msfconsole 命令查看模块详情；"
                f"或访问 {self._rapid7_url(module_name)} 查看 Rapid7 文档"
            ),
        }

    @staticmethod
    def gen_msf_command(module_name: str, rhosts: str = "{target}", rport: str = "") -> str:
        """生成可直接执行的 msfconsole 命令。"""
        cmd = f"msfconsole -q -x '\nuse {module_name}\nset RHOSTS {rhosts}\n"
        if rport:
            cmd += f"set RPORT {rport}\n"
        cmd += "run\nexit -y\n'"
        return cmd

    @staticmethod
    def search_offline_by_keyword(keyword: str) -> list[dict[str, Any]]:
        """按关键词匹配离线知识库中的 MSF 模块。

        Args:
            keyword: 搜索关键词，如 vsftpd / samba / tomcat

        Returns:
            匹配的模块列表，按 rank 降序排列。
        """
        keyword = str(keyword or "").strip().lower()
        if not keyword:
            return []

        keywords = re.split(r"[\s/._-]+", keyword)
        keywords = [k for k in keywords if len(k) >= 3]

        matched: list[dict[str, Any]] = []
        seen: set[str] = set()

        for module_name, info in _OFFLINE_MODULE_KB.items():
            haystack = f"{module_name} {info.get('description','')} {' '.join(info.get('references',[]))}"
            if any(k in haystack.lower() for k in keywords):
                if module_name not in seen:
                    seen.add(module_name)
                    matched.append(dict(info))

        rank_order = {"excellent": 0, "great": 1, "good": 2, "normal": 3,
                      "average": 4, "low": 5, "manual": 6}
        matched.sort(key=lambda x: rank_order.get(x.get("rank", "manual"), 99))
        return matched

    @staticmethod
    def match_cve_to_module(cve_id: str) -> Optional[dict[str, Any]]:
        """通过 CVE 编号匹配离线知识库中的 MSF 模块。"""
        cve_id = str(cve_id or "").strip().upper()
        if not cve_id:
            return None
        for module_name, info in _OFFLINE_MODULE_KB.items():
            refs = [r.upper() for r in info.get("references", [])]
            if cve_id in refs:
                return dict(info)
        return None

    def _rapid7_url(self, module_name: str) -> str:
        if "/" not in module_name:
            return _RAPID7_BASE
        return _RAPID7_BASE + module_name.replace("/", "/")

    def _fetch_rapid7(self, module_name: str) -> Optional[dict[str, Any]]:
        """尝试抓取 Rapid7 模块页面。失败返回 None。"""
        url = self._rapid7_url(module_name)
        html = self._http_get(url)
        if not html:
            return None

        data: dict[str, Any] = {"module_name": module_name, "rapid7_url": url}

        # 提取描述（meta description 或页面标题）
        desc_match = re.search(
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if desc_match:
            data["description"] = desc_match.group(1).strip()

        # 提取标题
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            data["title"] = title_match.group(1).strip()

        # 提取页面中提到的 CVE
        cves = sorted(set(re.findall(r"CVE-\d{4}-\d{4,}", html, re.IGNORECASE)))
        if cves:
            data["references"] = cves

        # 如果没有任何有用信息，视为抓取失败
        if not data.get("description") and not data.get("title"):
            return None

        return data

    def _http_get(self, url: str) -> Optional[str]:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html",
            })
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
