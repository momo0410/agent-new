"""P7 单测：Protocol Adapters (Redis / Mongo / JMX).

≥ 12 个测试 (4+4+4)。
通过 socketserver / monkeypatch 模拟服务，零网络依赖。
"""
from __future__ import annotations

import socket
import struct
import threading
import time
from contextlib import closing
from typing import Callable, Optional

import pytest

from app.services.pentest_agent.protocol_adapters import (
    AdapterResult,
    BaseProtocolAdapter,
    JMXAdapter,
    MongoAdapter,
    RedisAdapter,
    dispatch_protocol_tool,
)


# ── 通用 TCP 假服务器 ─────────────────────────────────────────
class FakeServer:
    """单连接、单次响应的最小 TCP 服务器。每次启一个，握手后 handler 处理。"""

    def __init__(self, handler: Callable[[socket.socket], None]):
        self.handler = handler
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self._th = threading.Thread(target=self._serve, daemon=True)
        self._stop = False
        self._th.start()

    def _serve(self):
        while not self._stop:
            try:
                self.sock.settimeout(0.5)
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                self.handler(conn)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except Exception:
            pass
        self._th.join(timeout=1)


@pytest.fixture
def make_server():
    servers: list[FakeServer] = []
    def _factory(handler: Callable[[socket.socket], None]) -> FakeServer:
        s = FakeServer(handler)
        servers.append(s)
        return s
    yield _factory
    for s in servers:
        s.close()


# ── RESP helpers ───────────────────────────────────────────────
def _resp_bulk(s: str) -> bytes:
    b = s.encode()
    return f"${len(b)}\r\n".encode() + b + b"\r\n"


def _resp_array(items: list[bytes]) -> bytes:
    return f"*{len(items)}\r\n".encode() + b"".join(items)


def _resp_status(s: str) -> bytes:
    return f"+{s}\r\n".encode()


def _resp_err(s: str) -> bytes:
    return f"-{s}\r\n".encode()


def _resp_int(n: int) -> bytes:
    return f":{n}\r\n".encode()


def _read_resp_command(conn: socket.socket) -> list[str]:
    """简易读：解析单条 RESP Array 命令并返回字符串数组。"""
    buf = b""
    conn.settimeout(2)
    def _readline() -> bytes:
        nonlocal buf
        while b"\r\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        if b"\r\n" not in buf:
            return buf
        idx = buf.index(b"\r\n")
        line, buf = buf[:idx], buf[idx + 2:]
        return line
    def _readn(n: int) -> bytes:
        nonlocal buf
        while len(buf) < n + 2:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        data = buf[:n]
        buf = buf[n + 2:]
        return data
    head = _readline()
    if not head or head[:1] != b"*":
        return []
    n = int(head[1:])
    out: list[str] = []
    for _ in range(n):
        h = _readline()
        if not h or h[:1] != b"$":
            return out
        length = int(h[1:])
        out.append(_readn(length).decode("utf-8", errors="replace"))
    return out


# ═════════════════════════════════════════════════════════════
# RedisAdapter
# ═════════════════════════════════════════════════════════════
class TestRedisAdapter:
    def test_info_parses_meta(self, make_server):
        info_payload = (
            "# Server\r\n"
            "redis_version:6.2.7\r\n"
            "redis_mode:standalone\r\n"
            "role:master\r\n"
            "tcp_port:6379\r\n"
            "dir:/var/lib/redis\r\n"
        )

        def handler(conn):
            cmd = _read_resp_command(conn)
            assert cmd[0].upper() == "INFO"
            conn.sendall(_resp_bulk(info_payload))

        srv = make_server(handler)
        a = RedisAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.info()
        assert r.success
        assert "redis_version=6.2.7" in r.evidence
        assert r.raw["meta"]["role"] == "master"

    def test_auth_failure(self, make_server):
        def handler(conn):
            cmd = _read_resp_command(conn)
            assert cmd[0].upper() == "AUTH"
            conn.sendall(_resp_err("ERR Client sent AUTH, but no password is set"))

        srv = make_server(handler)
        a = RedisAdapter("127.0.0.1", srv.port, timeout=2, password="wrong")
        r = a.info()
        assert not r.success
        assert "AUTH" in (r.error or "")

    def test_write_ssh_key_sequence(self, make_server):
        commands_seen: list[list[str]] = []

        def handler(conn):
            # 4 条命令依次返回 OK
            for _ in range(4):
                c = _read_resp_command(conn)
                if not c:
                    return
                commands_seen.append(c)
                if c[0].upper() == "SET":
                    conn.sendall(_resp_status("OK"))
                else:
                    conn.sendall(_resp_status("OK"))

        srv = make_server(handler)
        a = RedisAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.write_ssh_key({"public_key": "ssh-rsa AAAA TEST"})
        assert r.success, r.error
        assert "SSH key written" in r.evidence
        ops = [c[0].upper() for c in commands_seen]
        assert ops == ["CONFIG", "CONFIG", "SET", "SAVE"]
        # 顺序中第一条是 dir，第二条是 dbfilename
        assert commands_seen[0][1:] == ["SET", "dir", "/root/.ssh"]
        assert commands_seen[1][1:] == ["SET", "dbfilename", "authorized_keys"]
        assert "ssh-rsa AAAA TEST" in commands_seen[2][2]

    def test_keys_command_returns_array(self, make_server):
        def handler(conn):
            cmd = _read_resp_command(conn)
            assert cmd == ["KEYS", "*"]
            conn.sendall(_resp_array([_resp_bulk("foo"), _resp_bulk("bar")]))

        srv = make_server(handler)
        a = RedisAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.keys({"pattern": "*"})
        assert r.success
        assert set(r.raw) == {"foo", "bar"}

    def test_dispatch_unknown_action(self, make_server):
        def handler(conn):
            pass
        srv = make_server(handler)
        a = RedisAdapter("127.0.0.1", srv.port, timeout=1)
        r = a.dispatch("not_exist", {})
        assert not r.success
        assert "未知 redis action" in r.error


# ═════════════════════════════════════════════════════════════
# MongoAdapter
# ═════════════════════════════════════════════════════════════
class TestMongoAdapter:
    def _build_reply(self, doc: dict) -> bytes:
        """构造合法的 OP_REPLY 响应。"""
        from app.services.pentest_agent.protocol_adapters.mongo_adapter import _bson_encode
        body = _bson_encode(doc)
        # responseFlags i32, cursorID i64, startingFrom i32, numberReturned i32 + 1 doc
        payload = struct.pack("<iqii", 0, 0, 0, 1) + body
        # header: messageLength, requestID, responseTo, opCode=1
        header = struct.pack("<iiii", 16 + len(payload), 99, 0, 1)
        return header + payload

    def test_server_info(self, make_server):
        from app.services.pentest_agent.protocol_adapters.mongo_adapter import _bson_decode

        captured: dict = {}

        def handler(conn):
            conn.settimeout(2)
            # 读 header
            head = conn.recv(16)
            if len(head) < 16:
                return
            length = struct.unpack_from("<i", head)[0]
            rest = b""
            while len(rest) < length - 16:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                rest += chunk
            # rest = flags(4) + cstring(database.$cmd) + skip(4) + return(4) + bson_doc
            # 略过, 直接构造回复
            reply = self._build_reply({
                "version": "4.4.10",
                "gitVersion": "abc123",
                "ok": 1.0,
            })
            conn.sendall(reply)
            captured["sent"] = True

        srv = make_server(handler)
        a = MongoAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.server_info()
        assert r.success, r.error
        assert "4.4.10" in r.evidence
        assert captured.get("sent")

    def test_list_dbs(self, make_server):
        def handler(conn):
            conn.settimeout(2)
            head = conn.recv(16)
            length = struct.unpack_from("<i", head)[0]
            while True:
                rest = conn.recv(length - 16)
                if not rest or len(rest) >= length - 16:
                    break
            reply = self._build_reply({
                "databases": [
                    {"name": "admin", "sizeOnDisk": 32768.0},
                    {"name": "config", "sizeOnDisk": 73728.0},
                    {"name": "leaked", "sizeOnDisk": 1024.0},
                ],
                "totalSize": 107520.0,
                "ok": 1.0,
            })
            conn.sendall(reply)

        srv = make_server(handler)
        a = MongoAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.list_dbs()
        assert r.success, r.error
        assert "leaked" in r.raw

    def test_list_collections(self, make_server):
        def handler(conn):
            conn.settimeout(2)
            head = conn.recv(16)
            if len(head) < 16:
                return
            length = struct.unpack_from("<i", head)[0]
            _ = conn.recv(length - 16)
            reply = self._build_reply({
                "cursor": {
                    "id": 0,
                    "ns": "leaked.$cmd.listCollections",
                    "firstBatch": [
                        {"name": "users", "type": "collection"},
                        {"name": "tokens", "type": "collection"},
                    ],
                },
                "ok": 1.0,
            })
            conn.sendall(reply)

        srv = make_server(handler)
        a = MongoAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.list_collections({"db": "leaked"})
        assert r.success, r.error
        assert set(r.raw) == {"users", "tokens"}

    def test_errmsg_handled(self, make_server):
        def handler(conn):
            conn.settimeout(2)
            head = conn.recv(16)
            if len(head) < 16:
                return
            length = struct.unpack_from("<i", head)[0]
            _ = conn.recv(length - 16)
            reply = self._build_reply({
                "ok": 0.0,
                "errmsg": "not authorized on admin to execute command",
                "code": 13,
            })
            conn.sendall(reply)

        srv = make_server(handler)
        a = MongoAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.list_dbs()
        assert not r.success
        assert "not authorized" in r.error

    def test_dispatch_unknown(self, make_server):
        def handler(conn):
            pass
        srv = make_server(handler)
        a = MongoAdapter("127.0.0.1", srv.port, timeout=1)
        r = a.dispatch("does_not_exist", {})
        assert not r.success
        assert "未知 mongo action" in r.error


# ═════════════════════════════════════════════════════════════
# JMXAdapter
# ═════════════════════════════════════════════════════════════
class TestJMXAdapter:
    def test_rmi_probe_success(self, make_server):
        def handler(conn):
            conn.settimeout(2)
            data = conn.recv(64)
            assert data.startswith(b"JRMI")
            # 回 ProtocolAck (0x4e)
            conn.sendall(b"\x4e\x00\x06host\x00\x00\x00\x00")

        srv = make_server(handler)
        a = JMXAdapter("127.0.0.1", srv.port, timeout=2)
        r = a.probe()
        assert r.success, r.error
        assert "RMI listening" in r.evidence

    def test_rmi_probe_failure_on_closed_port(self):
        # 端口 1 通常关闭/被禁
        a = JMXAdapter("127.0.0.1", 1, timeout=1)
        r = a.probe()
        assert not r.success
        assert "RMI handshake" in r.error

    def test_dump_registry_missing_nmap(self, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda name: None)
        a = JMXAdapter("127.0.0.1", 1099, timeout=2)
        r = a.dump_registry()
        assert not r.success
        assert "nmap" in r.error

    def test_prepare_exploit_missing_ysoserial(self, monkeypatch):
        import app.services.pentest_agent.protocol_adapters.jmx_adapter as jmx_mod
        monkeypatch.setattr(jmx_mod, "_find_ysoserial", lambda: "")
        a = JMXAdapter("127.0.0.1", 1099, timeout=2)
        r = a.prepare_exploit({"cmd": "id"})
        assert not r.success
        assert "ysoserial" in r.error

    def test_prepare_exploit_success(self, monkeypatch, tmp_path):
        import app.services.pentest_agent.protocol_adapters.jmx_adapter as jmx_mod
        fake_jar = tmp_path / "ysoserial-all.jar"
        fake_jar.write_bytes(b"fake")
        monkeypatch.setattr(jmx_mod, "_find_ysoserial", lambda: str(fake_jar))
        import shutil
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/java" if name == "java" else None)

        def fake_run(cmd, timeout):
            # 模拟 ysoserial 输出 payload
            return 0, "SERIALIZED_DATA_xxxxxxx", ""

        monkeypatch.setattr(jmx_mod, "_run", fake_run)

        output_path = tmp_path / "out.ser"
        a = JMXAdapter("10.0.0.5", 1099, timeout=2)
        r = a.prepare_exploit({"gadget": "CommonsCollections5", "cmd": "id",
                                "output": str(output_path)})
        assert r.success, r.error
        assert output_path.exists()
        assert "RMIRegistryExploit 10.0.0.5 1099" in r.evidence


# ═════════════════════════════════════════════════════════════
# 顶层 dispatcher 测试
# ═════════════════════════════════════════════════════════════
class TestDispatcher:
    def test_invalid_json_returns_error(self):
        r = dispatch_protocol_tool("redis_eval", "not a json")
        assert not r["success"]
        assert "JSON" in r["error"]

    def test_unknown_tool(self):
        r = dispatch_protocol_tool("foo_bar", '{"host": "127.0.0.1", "action": "info"}')
        assert not r["success"]
        assert "未知协议工具" in r["error"]

    def test_missing_host(self):
        r = dispatch_protocol_tool("redis_eval", '{"action": "info"}')
        assert not r["success"]
        assert "host" in r["error"]

    def test_missing_action(self):
        r = dispatch_protocol_tool("redis_eval", '{"host": "127.0.0.1"}')
        assert not r["success"]
        assert "action" in r["error"]

    def test_redis_eval_round_trip(self, make_server):
        def handler(conn):
            cmd = _read_resp_command(conn)
            if cmd[0].upper() == "INFO":
                conn.sendall(_resp_bulk("redis_version:7.0.0\r\nrole:master\r\n"))

        srv = make_server(handler)
        args = '{"host": "127.0.0.1", "port": %d, "action": "info"}' % srv.port
        r = dispatch_protocol_tool("redis_eval", args)
        assert r["success"], r.get("error")
        assert "redis_version=7.0.0" in r["evidence"]
