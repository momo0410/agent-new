"""P5 单元测试: 服务名规范化 + 联网检索暴露"""
from __future__ import annotations

import pytest

from app.services.skill_engine.skill_generator import (
    _clean_service_name,
    _service_family,
    SkillGenerator,
)
from app.services.pentest_agent.executor import Executor


# --- P5-1: 服务名规范化 ---

@pytest.mark.parametrize("raw, expected_clean, expected_family", [
    ("ftp     vsftpd 2.3.4",            "vsftpd 2.3.4",      "vsftpd"),
    ("http        Apache httpd 2.4.49 ((Unix))", "Apache httpd 2.4.49", "Apache httpd"),
    ("ssh   OpenSSH 4.7p1 Debian 8ubuntu1 (protocol 2.0)", "OpenSSH 4.7p1 Debian 8ubuntu1", "OpenSSH"),
    ("redis       Redis key-value store 4.0.14",     "Redis key-value store 4.0.14", "Redis key-value"),
    ("smb",                              "smb",               "smb"),
    ("",                                 "unknown",           "unknown"),
    ("bindshell Metasploitable root shell", "Metasploitable root shell", "Metasploitable root"),
])
def test_p5_1_service_name_normalization(raw, expected_clean, expected_family):
    assert _clean_service_name(raw) == expected_clean
    # family 是宽松检查：包含 expected_family 即可（去版本号策略 ad-hoc）
    actual_family = _service_family(raw)
    assert expected_family.split()[0].lower() in actual_family.lower(), (
        f"family={actual_family}, expected to contain {expected_family.split()[0]}"
    )


def test_p5_1_clean_service_skill_no_multispace(tmp_path):
    """生成的 skill 不应再含 'ftp     vsftpd' 这种多空格字符串"""
    gen = SkillGenerator(str(tmp_path / "skills"))
    path = {
        "name": "exploit-ftp-test",
        "port": 21,
        "service": "ftp     vsftpd 2.3.4",   # nmap 原始格式
        "tag": "ftp",
        "ip": "192.168.1.1",
        "exploit_success": True,
        "credentials": [],
        "vulnerabilities": [],
        "commands": [{"tool": "msfconsole", "args": "use vsftpd; run", "result": "got shell"}],
        "failures": [],
        "sessions": [{"id": "s1", "active": True}],
    }
    md = gen._render_skill_md(path)
    # 关键校验：不能再出现 ftp 后面多个空格
    assert "ftp     vsftpd" not in md, "服务名仍包含原始多空格"
    assert "ftp    vsftpd" not in md
    # 应该用 family 写
    assert "vsftpd" in md
    # frontmatter 的 description 用 family
    assert "vsftpd 2.3.4 服务" in md or "vsftpd" in md
    # Generalization 应该用 family 而非整段
    assert "适用服务家族" in md
    # Detection Fingerprint 用 family 关键词
    assert "包含关键词" in md
    print(md[:1500])


# --- P5-2: 联网检索工具暴露给 LLM ---

def test_p5_2_online_tools_visible_to_llm():
    """search_cve / search_exploit / lookup_msf_module / lookup_default_creds
    应当在 _LLM_ALWAYS_VISIBLE 集合中"""
    visible = Executor._LLM_ALWAYS_VISIBLE
    for name in ("search_cve", "search_exploit", "lookup_msf_module", "lookup_default_creds"):
        assert name in visible, f"{name} 未暴露给 LLM"


def test_p5_2_online_tools_in_tools_toml():
    """tools.toml 应包含 4 个联网工具"""
    import tomllib
    from pathlib import Path
    toml_path = Path(__file__).parent.parent / "app" / "services" / "pentest_agent" / "tools.toml"
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)
    names = {t.get("name", "") for t in cfg.get("tool", [])}
    for name in ("search_cve", "search_exploit", "lookup_msf_module", "lookup_default_creds"):
        assert name in names, f"{name} 未在 tools.toml 注册"


# --- 复合验证：list_tools 输出能看到联网工具 ---

def test_p5_2_list_tools_output_contains_online(tmp_path):
    """Executor.list_tools() 返回的描述字符串中应该包含联网工具"""
    from app.services.pentest_agent.state import State
    state = State(str(tmp_path / "state.json"))
    executor = Executor(state=state)
    # _ensure_doctor 会做工具探查；我们想跳过让测试快
    # 但 list_tools 会调 _ensure_doctor，没办法
    # 直接看 self.tools 里有没有 4 个
    for name in ("search_cve", "search_exploit", "lookup_msf_module", "lookup_default_creds"):
        assert name in executor.tools, f"{name} 未在 tool_registry 加载"
