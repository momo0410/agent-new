"""
SkillGenerator — 从渗透测试结果中自动生成可复用的 SKILL.md 技能文件

输入: 渗透完成后的 State 对象
输出: 按 service/vulnerability 类型生成 SKILL.md 到 skills/learned/ 目录

生成策略（双层架构 v2.0）:
  第一层 — 程序提取事实:
    从 state 中抽取 service/CVE/成功命令/失败尝试/凭据
  第二层 — LLM 反思生成:
    调用 LLM 把事实加工成 v2.0 五段式 SKILL.md（Principle / Detection /
    Workflow / Failure Modes / Generalization）。LLM 不可用时回退到模板。

  - 成功的 exploit 路径 → 完整 exploit skill (v2.0 格式)
  - 发现漏洞但未利用 → recon skill (仅检测步骤)
  - 失败的尝试 → 不单独生成，但会作为 Failure Modes 注入到对应 skill
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from datetime import datetime
from typing import Any, Optional


# 已知服务 → 标准化 service tag
SERVICE_TAG_MAP = {
    "ftp": "ftp", "ssh": "ssh", "telnet": "telnet", "smtp": "smtp",
    "http": "http", "https": "https", "apache": "http", "nginx": "http",
    "tomcat": "tomcat", "smb": "smb", "microsoft-ds": "smb", "netbios-ssn": "smb",
    "mysql": "mysql", "postgres": "postgresql", "postgresql": "postgresql",
    "vnc": "vnc", "irc": "irc", "distcc": "distcc", "rmi": "java-rmi",
    "bindshell": "shell", "backdoor": "backdoor",
    "shell": "shell", "login": "login", "exec": "exec",
}


def _normalize_service_tag(service: str) -> str:
    lowered = str(service or "").strip().lower()
    for key, tag in SERVICE_TAG_MAP.items():
        if key in lowered:
            return tag
    return lowered.split()[0] if lowered else "unknown"


def _sanitize_name(text: str) -> str:
    text = str(text or "").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:64] or "unnamed"


def _extract_version_tag(service: str) -> str:
    """从服务指纹中提取版本标签，如 'vsftpd 2.3.4' → 'vsftpd-234'"""
    lowered = str(service or "").strip().lower()
    # 提取服务名 + 版本号
    match = re.match(r"(\S+)\s+(\d+[\d.]*)", lowered)
    if match:
        name = match.group(1).strip()
        version = match.group(2).strip().replace(".", "")
        return f"{name}-{version}"
    # 只有服务名没有版本
    name = lowered.split()[0] if lowered else ""
    if name and len(name) >= 3:
        return name
    return ""


class SkillGenerator:
    """从渗透测试 State 中自动生成 SKILL.md 技能文件"""

    def __init__(self, skills_root: str, llm_client: Optional[Any] = None,
                 online_search_results: Optional[list[dict]] = None):
        """
        Args:
            skills_root: skills/ 根目录
            llm_client: 可选的 LLM 客户端（需要实现 chat(messages) -> str 接口）。
                       不传则回退到纯模板生成。
            online_search_results: 本次渗透的联网检索结果日志（来自
                       OnlineSearchService.get_results_log()）。注入到 LLM prompt，
                       让生成的 Principle 章节基于 NVD 权威信息而非模型记忆。
        """
        self.skills_root = skills_root
        # P0: 生成的 skill 默认进入 draft 目录，经过 LifecycleManager 自动晋升
        self.learned_dir = os.path.join(skills_root, "learned", "draft")
        self.llm_client = llm_client
        self.online_search_results = online_search_results or []
        self._existing_skill_names: set[str] = set()
        self._load_existing_skill_names()

    def _load_existing_skill_names(self):
        """扫描已有 skill 文件名，避免重复生成"""
        for root, dirs, files in os.walk(self.skills_root):
            for f in files:
                if f.endswith(".md"):
                    name = f.replace(".md", "").replace("SKILL", "").strip("-_").lower()
                    if name:
                        self._existing_skill_names.add(name)

    def _has_existing_skill(self, skill_name: str, path: dict) -> bool:
        """检查是否已有同名或功能相同的预置 skill"""
        # 精确名字匹配
        if skill_name in self._existing_skill_names:
            return True
        # 检查 service tag 是否有对应的 exploit skill
        tag = path.get("tag", "")
        if tag:
            for existing in self._existing_skill_names:
                if f"exploit-{tag}" in existing or f"{tag}-backdoor" in existing:
                    return True
        return False

    def generate_from_state(self, state) -> list[str]:
        """
        从完成的渗透状态中提取经验，生成 skill 文件。

        Returns:
            生成的 skill 文件路径列表
        """
        os.makedirs(self.learned_dir, exist_ok=True)

        data = state.data if hasattr(state, "data") else state
        findings = data.get("findings", [])
        actions = data.get("actions_taken", [])
        credentials = data.get("credentials", [])
        vulnerabilities = data.get("vulnerabilities", [])
        targets = data.get("targets", [])
        sessions = data.get("sessions", [])

        generated_files: list[str] = []

        # 1. 按 service 聚类成功的攻击路径（同时收集失败尝试用于 Failure Modes）
        attack_paths = self._extract_attack_paths(
            findings, actions, credentials, vulnerabilities, sessions, targets
        )

        # 2. 每条攻击路径生成一个 skill（跳过已有预置 skill 的）
        for path in attack_paths:
            skill_name = _sanitize_name(path['name'])
            if self._has_existing_skill(skill_name, path):
                continue

            # 优先用 LLM 反思生成 v2.0 格式；失败时回退到模板
            skill_content = None
            if self.llm_client is not None and path.get("exploit_success"):
                try:
                    skill_content = self._render_skill_md_v2_with_llm(path)
                except Exception as exc:
                    # LLM 失败不影响流程，回退模板
                    print(f"[SkillGenerator] LLM 生成失败，回退模板：{exc}")
                    skill_content = None

            if not skill_content:
                skill_content = self._render_skill_md(path)

            filename = f"{skill_name}.md"
            filepath = os.path.join(self.learned_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(skill_content)
            generated_files.append(filepath)

        # 3. 生成汇总 skill
        if attack_paths:
            summary = self._render_summary_skill(attack_paths, targets)
            summary_path = os.path.join(self.learned_dir, "pentest-summary.md")
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            generated_files.append(summary_path)

        return generated_files

    def _extract_attack_paths(
        self,
        findings: list[dict],
        actions: list[dict],
        credentials: list[dict],
        vulnerabilities: list[dict],
        sessions: list[dict],
        targets: list[str],
    ) -> list[dict]:
        """从渗透结果中提取成功的攻击路径"""
        paths: list[dict] = []

        # 按 port+service 聚类 findings
        service_map: dict[tuple[int, str], dict] = {}
        for f in findings:
            if not isinstance(f, dict):
                continue
            port = f.get("port")
            if isinstance(port, str) and port.isdigit():
                port = int(port)
            if not isinstance(port, int):
                continue
            service = str(f.get("service", "")).strip()
            ip = str(f.get("ip", "")).strip() or (targets[0] if targets else "")
            key = (port, _normalize_service_tag(service))
            if key not in service_map:
                service_map[key] = {
                    "port": port,
                    "service": service,
                    "ip": ip,
                    "tag": _normalize_service_tag(service),
                }

        # 找出每个 service 相关的成功 action
        successful_actions = [
            a for a in actions
            if isinstance(a, dict) and a.get("status") == "completed"
            and a.get("tool") not in {"_doctor", "_llm_wait", "_token_usage", "_done", "_skip", "_llm_error"}
        ]

        # 找出失败的 action（用于生成 Failure Modes）
        failed_actions = [
            a for a in actions
            if isinstance(a, dict)
            and a.get("status") in {"failed", "error", "timeout"}
            and a.get("tool") not in {"_doctor", "_llm_wait", "_token_usage", "_done", "_skip", "_llm_error"}
        ]

        # 找出有 exploit 成功证据的 action
        exploit_actions = [
            a for a in successful_actions
            if self._has_exploit_evidence(a)
        ]

        # 为每个高价值 service 生成攻击路径
        for (port, tag), svc_info in service_map.items():
            # 找与此 service 相关的成功 action
            related_actions = [
                a for a in successful_actions
                if self._action_targets_port(a, port) or self._action_targets_service(a, svc_info["service"])
            ]
            if not related_actions:
                continue

            # 找相关的 credential
            related_creds = [
                c for c in credentials
                if isinstance(c, dict) and self._cred_matches_service(c, tag)
            ]

            # 找相关的 vulnerability
            related_vulns = [
                v for v in vulnerabilities
                if isinstance(v, dict) and self._vuln_matches_port(v, port)
            ]

            # 找是否有 exploit 成功
            exploit_success = any(
                self._action_targets_port(a, port) and self._has_exploit_evidence(a)
                for a in exploit_actions
            )

            # 找成功的命令
            successful_commands = [
                {"tool": a.get("tool", ""), "args": a.get("args", ""), "result": (a.get("result", "") or "")[:200]}
                for a in related_actions
                if a.get("tool") not in {"_doctor", "_llm_wait", "_token_usage", "_done", "_skip", "_llm_error"}
            ]

            # 找此 service 相关的失败命令（→ Failure Modes 的素材）
            related_failures = [
                {
                    "tool": a.get("tool", ""),
                    "args": str(a.get("args", ""))[:200],
                    "error": (a.get("error", "") or str(a.get("result", "")))[:200],
                }
                for a in failed_actions
                if self._action_targets_port(a, port) or self._action_targets_service(a, svc_info["service"])
            ][:5]  # 最多取 5 条

            # 用服务版本构建更精确的 skill 名字
            version_tag = _extract_version_tag(svc_info["service"])
            if version_tag:
                name = f"exploit-{version_tag}" if exploit_success else f"recon-{version_tag}"
            else:
                name = f"exploit-{tag}-{port}" if exploit_success else f"recon-{tag}-{port}"

            path = {
                "name": name,
                "port": port,
                "service": svc_info["service"],
                "tag": tag,
                "ip": svc_info["ip"],
                "exploit_success": exploit_success,
                "credentials": related_creds,
                "vulnerabilities": related_vulns,
                "commands": successful_commands,
                "failures": related_failures,
                "sessions": [s for s in sessions if isinstance(s, dict)],
            }
            paths.append(path)

        # 按 exploit 成功优先排序
        paths.sort(key=lambda p: (not p["exploit_success"], p["port"]))
        return paths

    def _has_exploit_evidence(self, action: dict) -> bool:
        text = " ".join(str(action.get(k, "")) for k in ("result", "error", "full_stdout")).lower()
        indicators = [
            "uid=0(", "root@", "meterpreter session", "command shell session",
            "shell opened", "session opened", "login successful", "access granted",
            "interactive_session_connected", "nt authority\\system",
            "uid=", "whoami", "id;", "/bin/sh", "/bin/bash",
            "session 1 opened", "session 2 opened", "authenticated",
            "exploit completed", "exploit succeeded",
        ]
        # Also check if the action is msfconsole with status=completed (successful exploit)
        if action.get("tool") == "msfconsole" and action.get("status") == "completed":
            return True
        return any(ind in text for ind in indicators)

    def _action_targets_port(self, action: dict, port: int) -> bool:
        explicit_ports = {
            int(p) for p in (action.get("ports") or [])
            if isinstance(p, int) or str(p).isdigit()
        }
        if port in explicit_ports:
            return True
        args = str(action.get("args", ""))
        return bool(re.search(rf"(?:^|\D){port}(?:\D|$)", args))

    def _action_targets_service(self, action: dict, service: str) -> bool:
        if not service:
            return False
        args = str(action.get("args", "")).lower()
        surface = str(action.get("surface", "")).lower()
        svc_lower = service.lower()
        return svc_lower in args or svc_lower in surface

    def _cred_matches_service(self, cred: dict, tag: str) -> bool:
        source = str(cred.get("source", "")).lower()
        kind = str(cred.get("kind", "")).lower()
        return tag in source or tag in kind or not source

    def _vuln_matches_port(self, vuln: dict, port: int) -> bool:
        vuln_port = vuln.get("port")
        if isinstance(vuln_port, int):
            return vuln_port == port
        if isinstance(vuln_port, str) and vuln_port.isdigit():
            return int(vuln_port) == port
        target = str(vuln.get("target", ""))
        return str(port) in target

    # ─────────────────────────────────────────────────────────────
    # LLM 反思生成 v2.0 格式 SKILL.md
    # ─────────────────────────────────────────────────────────────

    # 内置的范例 skill（vsftpd 后门）作为 LLM 的格式标杆
    _V2_TEMPLATE_EXAMPLE = textwrap.dedent("""
    ---
    name: exploit-vsftpd-backdoor
    description: vsftpd 2.3.4 源码后门 RCE（CVE-2011-2523）。banner 含 "vsftpd 2.3.4" 即可触发。
    domain: penetration-testing
    subdomain: exploitation
    tags: [vsftpd, ftp, backdoor, CVE-2011-2523, supply-chain, rce]
    cve: CVE-2011-2523
    severity: critical
    version: '2.0'
    ---

    # exploit-vsftpd-backdoor

    ## Principle
    2011 年 vsftpd 2.3.4 官方源码包被植入恶意代码。FTP 客户端发送用户名含 `:)`
    时服务端在 6200 端口启动 root bindshell。这是源码供应链投毒，不是内存破坏。

    ## Detection Fingerprint
    必须满足以下条件之一才能触发：
    - `nmap -sV -p21` banner 显示 `vsftpd 2.3.4`
    - 触发后 `nc <target> 6200` 可连接

    反例（不要触发）：vsftpd 2.3.5 / 3.x 已修复；Debian 仓库版已打补丁。

    ## Workflow
    ### 方法 A：Metasploit
    ```
    msfconsole -q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS {target}; run'
    ```
    ### 方法 B：手动触发
    ```
    printf 'USER hacker:)\\r\\nPASS x\\r\\n' | nc -w 5 {target} 21
    nc {target} 6200
    ```

    ## Failure Modes
    | 现象 | 原因 | 下一步 |
    |---|---|---|
    | 6200 连接被拒绝 | 防火墙/发行版补丁 | 跳过，转 ssh-bruteforce |
    | msf 报 Exploit failed | 后门已清理 | 同上 |

    ## Generalization
    这是"源码供应链后门"漏洞类。识别套路：
    1. 服务版本号是单一精确值
    2. CVE 描述含 "backdoor" / "trojaned source"
    3. 利用 = 发送魔法字符串 → 连接后门端口/触发命令

    同类：UnrealIRCd 3.2.8.1 (CVE-2010-2075)、ProFTPd 1.3.3c。

    ## Key Concepts
    | 字段 | 值 |
    |---|---|
    | CVE | CVE-2011-2523 |
    | 影响版本 | vsftpd 2.3.4 |
    | 触发字符 | username 含 `:)` |
    | 后门端口 | 6200/tcp |
    """).strip()

    def _render_skill_md_v2_with_llm(self, path: dict) -> Optional[str]:
        """调用 LLM 把渗透事实加工成 v2.0 格式 SKILL.md。

        失败返回 None，让调用方回退到模板版。
        """
        if not self.llm_client:
            return None

        # 1) 准备事实摘要喂给 LLM
        service = path.get("service", "")
        port = path.get("port", "")
        commands = path.get("commands", [])
        credentials = path.get("credentials", [])
        vulnerabilities = path.get("vulnerabilities", [])
        failures = path.get("failures", [])

        # 提取可能的 CVE
        cves = set()
        for v in vulnerabilities:
            cve_id = v.get("cve") or v.get("name") or ""
            for m in re.findall(r"CVE-\d{4}-\d+", str(cve_id), re.IGNORECASE):
                cves.add(m.upper())
        for cmd in commands:
            text = f"{cmd.get('args','')} {cmd.get('result','')}"
            for m in re.findall(r"CVE-\d{4}-\d+", text, re.IGNORECASE):
                cves.add(m.upper())

        facts = {
            "service": service,
            "port": port,
            "detected_cves": sorted(cves),
            "successful_commands": [
                {"tool": c.get("tool", ""), "args": str(c.get("args", ""))[:150]}
                for c in commands[:6]
            ],
            "credentials_found": [
                {"user": c.get("username", "?"), "pass": c.get("password", "?")[:20]}
                for c in credentials[:3]
            ],
            "vulnerabilities": [
                {"name": v.get("name", ""), "severity": v.get("severity", "")}
                for v in vulnerabilities[:5]
            ],
            "failed_attempts": failures[:5],
        }

        skill_name = _sanitize_name(path.get("name", "auto-skill"))

        prompt = self._build_v2_generation_prompt(skill_name, facts)

        # 2) 调用 LLM
        messages = [
            {
                "role": "system",
                "content": (
                    "你是一名资深渗透测试技能文档作者。你的任务是把渗透测试的实际执行结果"
                    "整理成可复用、可教学的 SKILL.md 文档。要求：\n"
                    "1. 严格按用户给出的 v2.0 五段式格式（Principle / Detection Fingerprint / "
                    "Workflow / Failure Modes / Generalization）输出。\n"
                    "2. Principle 章节要解释漏洞的真正原理（不是怎么打，而是为什么能打）。\n"
                    "3. Generalization 章节必须给出同类漏洞列表和通用利用模板。\n"
                    "4. Failure Modes 用表格列出常见失败现象 + 原因 + 下一步建议。\n"
                    "5. 只输出 SKILL.md 的完整 Markdown 内容，不要任何额外说明。"
                ),
            },
            {"role": "user", "content": prompt},
        ]

        try:
            response = self._call_llm(messages)
        except Exception as exc:
            print(f"[SkillGenerator] LLM 调用异常: {exc}")
            return None

        if not response or not isinstance(response, str):
            return None

        # 3) 清洗响应（去掉可能的代码块包裹）
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # 去掉 ```markdown\n ... \n```
            cleaned = re.sub(r"^```[a-zA-Z]*\n", "", cleaned)
            cleaned = re.sub(r"\n```\s*$", "", cleaned)

        # 4) 基本校验：必须含 frontmatter 和至少 3 个 v2.0 章节
        required_sections = ["## Principle", "## Workflow", "## Generalization"]
        if not cleaned.startswith("---") or sum(s in cleaned for s in required_sections) < 2:
            print(f"[SkillGenerator] LLM 输出格式不合格，回退模板")
            return None

        return cleaned

    def _build_v2_generation_prompt(self, skill_name: str, facts: dict) -> str:
        """构造让 LLM 生成 v2.0 skill 的 prompt"""
        facts_json = json.dumps(facts, ensure_ascii=False, indent=2)

        # 注入联网检索结果（NVD 权威 CVE 信息），让 Principle 章节基于权威数据
        online_context = self._build_online_search_context(facts)

        online_section = ""
        if online_context:
            online_section = textwrap.dedent(f"""
            ## 联网检索到的权威信息（必须参考）
            以下是本次渗透中通过联网检索（NVD / Rapid7 等）查到的权威数据。
            **Principle 章节必须基于这些权威信息撰写**，不要凭训练记忆猜测 CVE 细节。
            ```json
            {online_context}
            ```
            """).strip()
        else:
            online_section = (
                "## 联网检索结果\n"
                "本次渗透未触发联网检索或无相关结果。Principle 章节基于渗透事实和你的"
                "专业知识撰写，但请在 Generalization 中注明'未经 NVD 查证，细节待核实'。"
            )

        return textwrap.dedent(f"""
        请根据以下渗透测试事实，生成一份 v2.0 格式的 SKILL.md 文档。

        ## 渗透事实
        ```json
        {facts_json}
        ```

        {online_section}

        ## skill 名称
        `{skill_name}`

        ## v2.0 格式范例（严格参考此结构和详细程度）
        ---START EXAMPLE---
        {self._V2_TEMPLATE_EXAMPLE}
        ---END EXAMPLE---

        ## 你的任务
        基于"渗透事实"和"联网检索到的权威信息"，按照上面范例的五段式结构
        （Principle / Detection Fingerprint / Workflow / Failure Modes /
        Generalization / Key Concepts），用**中文**写一份新的 SKILL.md。

        关键要求：
        1. **Principle**：解释这类漏洞的根本原理。如果检测到具体 CVE 且有联网检索结果，
           **必须以联网检索到的 NVD 描述为准**（权威性 > 训练记忆）。不要只写"漏洞利用"
           四个字，要讲清楚"为什么有这个漏洞、怎么形成的"。
        2. **Detection Fingerprint**：列出至少 2 条精确的检测条件 + 反例。
        3. **Workflow**：根据"successful_commands"提炼，给出 2-3 种方法（msf / 手动 / 备选）。
        4. **Failure Modes**：把"failed_attempts"总结成失败现象表，并补充常见失败场景。
           即使没有失败记录，也要根据漏洞原理推演 3-5 个常见失败情况。
        5. **Generalization**：**这是最重要的章节**。识别这是哪一类漏洞，列出同类漏洞，
           给出通用利用模板。
        6. frontmatter 必须含 name、description、domain、tags；若知道 CVE 加上 cve 字段。
        7. 输出**只能是 SKILL.md 内容本身**，不要解释、不要前置说明。

        现在请输出 SKILL.md：
        """).strip()

    def _build_online_search_context(self, facts: dict) -> str:
        """从联网检索结果中提取与当前 skill 相关的权威信息，格式化为 JSON 字符串。"""
        if not self.online_search_results:
            return ""

        # 当前 skill 涉及的 CVE（从 facts 中提取）
        related_cves = set(str(c).upper() for c in facts.get("detected_cves", []))
        service = str(facts.get("service", "")).lower()

        relevant: list[dict] = []
        for entry in self.online_search_results:
            if not entry.get("ok"):
                continue
            tool = entry.get("tool", "")
            data = entry.get("data") or {}

            # search_cve 结果：如果 CVE 与当前 skill 相关，收录
            if tool == "search_cve":
                cve_id = str(data.get("cve_id", "")).upper()
                if cve_id and (not related_cves or cve_id in related_cves):
                    relevant.append({
                        "source": "NVD",
                        "type": "cve_detail",
                        "cve_id": cve_id,
                        "description": data.get("description", ""),
                        "cvss_score": data.get("cvss_score"),
                        "cvss_severity": data.get("cvss_severity", ""),
                        "affected_products": [
                            a.get("cpe", "") for a in (data.get("affected_products") or [])[:5]
                        ],
                        "references": [
                            r.get("url", "") for r in (data.get("references") or [])[:5]
                        ],
                    })

            # search_exploit 结果：如果关键词与当前服务相关，收录
            elif tool == "search_exploit":
                keyword = str(data.get("keyword", "")).lower()
                if service and (service in keyword or keyword in service):
                    cve_matches = data.get("cve_matches") or []
                    relevant.append({
                        "source": "NVD-keyword",
                        "type": "exploit_search",
                        "keyword": data.get("keyword", ""),
                        "matched_cves": [
                            {"cve_id": c.get("cve_id", ""), "cvss": c.get("cvss_score"),
                             "description": c.get("description", "")[:150]}
                            for c in cve_matches[:5]
                        ],
                    })

            # lookup_msf_module / lookup_default_creds 结果：直接收录
            elif tool == "lookup_msf_module":
                module_name = str(data.get("module_name", "")).lower()
                if service and service in module_name:
                    relevant.append({
                        "source": "Rapid7",
                        "type": "msf_module",
                        "module_name": data.get("module_name", ""),
                        "description": data.get("description", ""),
                        "payloads": data.get("payloads", []),
                    })
            elif tool == "lookup_default_creds":
                product = str(data.get("product", "")).lower()
                if service and (service in product or product in service):
                    relevant.append({
                        "source": "default-creds-db",
                        "type": "default_credentials",
                        "product": data.get("product", ""),
                        "credentials": [
                            {"user": c.get("username", ""), "pass": c.get("password", "")}
                            for c in (data.get("credentials") or [])[:5]
                        ],
                    })

        if not relevant:
            return ""
        return json.dumps(relevant, ensure_ascii=False, indent=2)

    def _call_llm(self, messages: list[dict]) -> Optional[str]:
        """统一 LLM 调用入口。兼容多种客户端接口。"""
        client = self.llm_client
        if client is None:
            return None

        # 形态 1：实现了 chat(messages) -> str
        if hasattr(client, "chat") and callable(client.chat):
            try:
                return client.chat(messages)
            except TypeError:
                pass

        # 形态 2：实现了 complete(messages) / generate(messages)
        for method_name in ("complete", "generate", "invoke", "run"):
            method = getattr(client, method_name, None)
            if callable(method):
                try:
                    result = method(messages)
                    if isinstance(result, dict):
                        return (
                            result.get("content")
                            or result.get("text")
                            or result.get("response")
                            or str(result)
                        )
                    return str(result) if result is not None else None
                except TypeError:
                    continue

        # 形态 3：是一个 callable
        if callable(client):
            try:
                result = client(messages)
                return str(result) if result is not None else None
            except Exception:
                return None

        return None

    # ─────────────────────────────────────────────────────────────
    # 模板回退版（保留兼容）
    # ─────────────────────────────────────────────────────────────

    def _render_skill_md(self, path: dict) -> str:
        """渲染单个攻击路径为 SKILL.md"""
        tag = path["tag"]
        port = path["port"]
        service = path["service"]
        exploit_success = path["exploit_success"]
        name = path["name"]

        # YAML frontmatter
        tags = [tag, f"port-{port}"]
        if exploit_success:
            tags.append("exploit")
        else:
            tags.append("recon")
        if path["vulnerabilities"]:
            tags.append("vulnerability")

        description = (
            f"{'成功利用' if exploit_success else '检测到'} {service} 服务 (端口 {port})"
        )
        if path["credentials"]:
            creds_desc = ", ".join(f"{c.get('username','?')}" for c in path["credentials"][:3])
            description += f"，凭据: {creds_desc}"

        lines = [
            "---",
            f"name: {name}",
            f"description: '{description}'",
            f"domain: penetration-testing",
            f"subdomain: {tag}",
            f"tags: [{', '.join(tags)}]",
            f"version: '1.0'",
            f"source: auto-generated",
            "---",
            "",
            f"# {service.upper()} 端口 {port} {'利用' if exploit_success else '检测'} Skill",
            "",
            "## When to Use",
            f"- 目标开放端口 {port}/{service}",
            f"- nmap 服务指纹匹配 `{service}`",
            "",
            "## Prerequisites",
            f"- 目标可达，端口 {port} 开放",
        ]

        if path["credentials"]:
            lines.append("- 需要以下凭据:")
            for c in path["credentials"][:3]:
                lines.append(f"  - 用户名: `{c.get('username', '?')}` / 密码: `{c.get('password', '?')}`")

        lines.append("")
        lines.append("## Workflow")

        if exploit_success:
            lines.append(f"### 步骤 1: 确认服务")
            lines.append(f"```")
            lines.append(f"nmap -Pn -sV -p {port} TARGET")
            lines.append(f"```")
            lines.append("")

            if path["commands"]:
                lines.append("### 步骤 2: 利用")
                for i, cmd in enumerate(path["commands"][:5], start=1):
                    lines.append(f"```")
                    lines.append(f"# {cmd.get('tool', '?')}: {cmd.get('args', '?')[:120]}")
                    lines.append(f"```")
                lines.append("")

            if path["credentials"]:
                lines.append("### 步骤 3: 凭据利用")
                for c in path["credentials"][:3]:
                    lines.append(f"- `{c.get('username', '?')}` / `{c.get('password', '?')}` ({c.get('source', '?')})")
                lines.append("")

            lines.append("### 验证")
            lines.append("```")
            lines.append("id; whoami; uname -a")
            lines.append("```")
        else:
            lines.append(f"### 检测")
            lines.append(f"```")
            lines.append(f"nmap -Pn -sC -sV -p {port} TARGET")
            lines.append(f"```")
            if path["vulnerabilities"]:
                lines.append("")
                lines.append("### 发现的漏洞")
                for v in path["vulnerabilities"][:5]:
                    lines.append(f"- [{v.get('severity', '?')}] {v.get('name', '?')}")

        if path["sessions"]:
            lines.append("")
            lines.append("## 注意事项")
            lines.append(f"- 已获得 {len(path['sessions'])} 个会话")

        lines.append("")
        return "\n".join(lines)

    def _render_summary_skill(self, paths: list[dict], targets: list[str]) -> str:
        """渲染汇总 skill"""
        exploit_paths = [p for p in paths if p["exploit_success"]]
        recon_paths = [p for p in paths if not p["exploit_success"]]
        target_str = ", ".join(targets[:3]) if targets else "unknown"

        lines = [
            "---",
            f"name: pentest-summary",
            f"description: '渗透测试汇总: {len(exploit_paths)} 个成功利用, {len(recon_paths)} 个检测'",
            f"domain: penetration-testing",
            f"subdomain: summary",
            f"tags: [summary, pentest, {'exploit' if exploit_paths else 'recon'}]",
            f"version: '1.0'",
            f"source: auto-generated",
            "---",
            "",
            f"# 渗透测试汇总报告",
            "",
            f"## 目标",
            f"- {target_str}",
            "",
            f"## 成功利用 ({len(exploit_paths)})",
        ]

        for p in exploit_paths:
            creds = ""
            if p["credentials"]:
                creds = f" (凭据: {p['credentials'][0].get('username', '?')})"
            lines.append(f"- 端口 {p['port']}/{p['tag']}{creds}")

        if recon_paths:
            lines.append("")
            lines.append(f"## 已检测 ({len(recon_paths)})")
            for p in recon_paths:
                lines.append(f"- 端口 {p['port']}/{p['tag']}")

        lines.append("")
        return "\n".join(lines)
