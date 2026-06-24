"""P9 回归测试：自动情报增强 + 高价值攻击面完成门。

R8-MSF2 暴露的问题：
1. service_intel 只用 nmap 原始服务串搜索（如 "ftp         vsftpd 2.3.4"），NVD/CVE 匹配差。
2. auto-intel 只 search_exploit，不 follow-up lookup_msf_module / lookup_default_creds。
3. LLM 拿到 root shell 后过早进入 post/done，未继续覆盖 vsftpd/distccd/unreal/samba 等高价值 RCE 面。
"""
from __future__ import annotations

from app.services.pentest_agent.agent import (
    _auto_inject_service_intel,
    _auto_phase_switch,
    _collect_pending_exploit_surfaces,
    _normalize_service_search_key,
    _service_family_for_default_creds,
)
from app.services.pentest_agent.state import State
from app.services.pentest_agent.planner import SERVICE_EXPLOIT_TEMPLATES


class FakeOnlineSearch:
    def __init__(self):
        self.search_calls = []
        self.msf_calls = []
        self.creds_calls = []

    def search_exploit(self, keyword: str):
        self.search_calls.append(keyword)
        if keyword == "vsftpd 2.3.4":
            return {
                "ok": True,
                "data": {
                    "cve_matches": [{"cve_id": "CVE-2011-2523", "cvss_score": 9.8}],
                    "extra_msf_modules": [
                        {"module_name": "exploit/unix/ftp/vsftpd_234_backdoor"}
                    ],
                    "exploit_guide": "vsftpd backdoor guide",
                },
            }
        return {"ok": True, "data": {"cve_matches": [], "extra_msf_modules": [], "exploit_guide": ""}}

    def lookup_msf_module(self, module_name: str):
        self.msf_calls.append(module_name)
        return {
            "ok": True,
            "data": {
                "module_name": module_name,
                "payloads": ["cmd/unix/interact", "cmd/unix/reverse"],
                "options": [
                    {"name": "RHOSTS", "required": True, "description": "target"},
                    {"name": "RPORT", "required": True, "default": "21"},
                    {"name": "PAYLOAD", "required": True, "default": "cmd/unix/interact"},
                ],
                "recommended_msfconsole_args": "-q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS <target>; set RPORT 21; set PAYLOAD cmd/unix/interact; run; exit'",
            },
        }

    def lookup_default_creds(self, product: str):
        self.creds_calls.append(product)
        return {"ok": True, "data": {"product": product, "credentials": [{"username": "admin", "password": "admin"}]}}


def test_normalize_service_search_key_removes_nmap_padding_and_protocol_prefix():
    assert _normalize_service_search_key("ftp         vsftpd 2.3.4") == "vsftpd 2.3.4"
    assert _normalize_service_search_key("ssh         OpenSSH 4.7p1 Debian 8ubuntu1 (protocol 2.0)") == "OpenSSH 4.7p1 Debian 8ubuntu1"
    assert _normalize_service_search_key("http        Apache httpd 2.2.8 ((Ubuntu) DAV/2)") == "Apache httpd 2.2.8"
    assert _normalize_service_search_key("telnet      Linux telnetd") == "Linux telnetd"


def test_service_family_for_default_creds_extracts_product_family():
    assert _service_family_for_default_creds("Apache Tomcat/Coyote JSP engine 1.1") == "tomcat"
    assert _service_family_for_default_creds("Redis key-value store 4.0.14") == "redis"
    assert _service_family_for_default_creds("Samba smbd 3.X - 4.X") == "samba"
    assert _service_family_for_default_creds("OpenSSH 4.7p1 Debian") == "openssh"


def test_auto_inject_service_intel_enriches_search_with_msf_and_default_creds(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("192.168.136.137")
    fake = FakeOnlineSearch()
    task = {"tool": "nmap"}
    result = {
        "parsed": [
            {"ip": "192.168.136.137", "port": 21, "service": "ftp         vsftpd 2.3.4"},
        ]
    }

    _auto_inject_service_intel(state, task, result, fake)

    assert fake.search_calls == ["vsftpd 2.3.4"]
    assert fake.msf_calls == ["exploit/unix/ftp/vsftpd_234_backdoor"]
    assert fake.creds_calls == ["vsftpd"]
    intel = state.data["service_intel"][0]
    assert intel["service_key"] == "vsftpd 2.3.4"
    assert intel["raw_service"] == "ftp         vsftpd 2.3.4"
    assert intel["port"] == 21
    assert intel["msf_modules"][0]["payloads"][0] == "cmd/unix/interact"
    assert intel["default_creds"]["credentials"][0]["username"] == "admin"


def test_service_intel_summary_renders_msf_payload_options_and_commands(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_service_intel("vsftpd 2.3.4", {
        "cves": [{"cve_id": "CVE-2011-2523", "cvss_score": 9.8}],
        "msf_modules": [{
            "module_name": "exploit/unix/ftp/vsftpd_234_backdoor",
            "payloads": ["cmd/unix/interact", "cmd/unix/reverse"],
            "options": [
                {"name": "RHOSTS", "required": True},
                {"name": "PAYLOAD", "required": True, "default": "cmd/unix/interact"},
            ],
            "recommended_msfconsole_args": "-q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; set PAYLOAD cmd/unix/interact; run; exit'",
        }],
        "default_creds": {"credentials": [{"username": "admin", "password": "admin"}]},
    })

    text = state._build_service_intel_summary()

    assert "CVE-2011-2523" in text
    assert "exploit/unix/ftp/vsftpd_234_backdoor" in text
    assert "cmd/unix/interact" in text
    assert "PAYLOAD" in text
    assert "recommended" in text.lower() or "推荐" in text
    assert "admin/admin" in text


def test_verified_high_value_rce_surface_is_still_pending_until_exploited(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("192.168.136.137")
    state.add_finding({"ip": "192.168.136.137", "port": 21, "service": "ftp         vsftpd 2.3.4"})
    state.upsert_attack_surface("192.168.136.137|21", ports=[21], status="verified", purpose="vsftpd verify")

    pending = _collect_pending_exploit_surfaces(state)

    assert any(item["port"] == 21 for item in pending)


def test_exploited_high_value_rce_surface_is_not_pending(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("192.168.136.137")
    state.add_finding({"ip": "192.168.136.137", "port": 1524, "service": "bindshell   Metasploitable root shell"})
    state.upsert_attack_surface("192.168.136.137|1524", ports=[1524], status="exploited", purpose="root shell")

    pending = _collect_pending_exploit_surfaces(state)

    assert not any(item["port"] == 1524 for item in pending)


def test_auto_phase_switch_does_not_leave_exploit_while_high_value_rce_pending(tmp_path):
    state = State(str(tmp_path / "state.json"))
    state.add_target("192.168.136.137")
    state.set_phase("exploit")
    state.add_finding({"ip": "192.168.136.137", "port": 21, "service": "ftp         vsftpd 2.3.4"})
    state.upsert_attack_surface("192.168.136.137|21", ports=[21], status="verified", purpose="vsftpd verify")
    state.upsert_session({
        "session_id": "s1",
        "kind": "interactive",
        "status": "connected",
        "transport": "nc",
        "banner_preview": "root@metasploitable:/#",
    })

    _auto_phase_switch(state)

    assert state.data["phase"] == "exploit"


def test_planner_templates_do_not_suggest_rockyou_and_vsftpd_sets_interact_payload():
    args_blob = "\n".join(str(t.get("args", "")) for t in SERVICE_EXPLOIT_TEMPLATES)
    assert "rockyou" not in args_blob.lower()
    vsftpd = next(t for t in SERVICE_EXPLOIT_TEMPLATES if "vsftpd" in str(t.get("purpose", "")).lower())
    assert "set PAYLOAD cmd/unix/interact" in vsftpd["args"]
    assert "exploit -j" not in vsftpd["args"]
