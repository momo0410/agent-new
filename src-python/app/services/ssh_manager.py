from __future__ import annotations

import asyncio
import os
import shlex
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
import asyncssh
from asyncssh.constants import (
    FILEXFER_TYPE_DIRECTORY,
    FILEXFER_TYPE_SYMLINK,
    FILEXFER_TYPE_UNKNOWN,
)
from app.models.types import (
    BashEnvironmentInfo,
    CommandCompletion,
    ConnectionInfo,
    SftpFileDetails,
    SftpFileInfo,
    SSHConnectionStatus,
    TerminalOutput,
)
class SSHManager:
    def __init__(self):
        self._connection: Optional[asyncssh.SSHClientConnection] = None
        self._sftp: Optional[asyncssh.SFTPClient] = None
        self._connection_info: Optional[ConnectionInfo] = None
        self._terminal_sessions: Dict[str, Any] = {}
        self._terminal_session_locks: Dict[str, asyncio.Lock] = {}
        self._connected = False
        self._host = ""
        self._port = 22
        self._username = ""
        self._last_state_note = "未连接"
        self._last_alive_probe_at = 0.0
        self._status_probe_ttl = 10.0
        max_channels_raw = os.getenv("SSH_MAX_CONCURRENT_CHANNELS", "6").strip()
        try:
            max_channels = int(max_channels_raw)
        except ValueError:
            max_channels = 6
        self._max_concurrent_channels = max(1, max_channels)
        self._channel_open_retries = 2
        self._channel_retry_base_delay = 0.12
        self._channel_semaphore = asyncio.Semaphore(self._max_concurrent_channels)

    @staticmethod
    def _looks_like_transport_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(
            token in msg
            for token in (
                "not connected",
                "connection lost",
                "connection reset",
                "broken pipe",
                "eof",
                "channel closed",
                "transport",
                "disconnected",
            )
        )

    @staticmethod
    def _looks_like_session_pressure_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(
            token in msg
            for token in (
                "session request failed",
                "session open refused",
                "open failed",
                "channel open failed",
                "administratively prohibited",
                "resource shortage",
                "too many sessions",
                "maxsessions",
            )
        )

    @staticmethod
    def _looks_like_exec_forbidden_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(
            token in msg
            for token in (
                "exec request failed",
                "shell request failed",
                "command not permitted",
                "administratively prohibited",
            )
        )

    @staticmethod
    def _looks_like_sftp_subsystem_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(
            token in msg
            for token in (
                "subsystem request failed",
                "subsystem not found",
                "couldn't start subsystem sftp",
                "unable to start sftp subsystem",
            )
        )

    @staticmethod
    def _call_bool_method(obj: Any, method_name: str) -> Optional[bool]:
        method = getattr(obj, method_name, None)
        if not callable(method):
            return None
        try:
            return bool(method())
        except Exception:
            return None

    @classmethod
    def _connection_closed_or_closing(cls, connection: Optional[Any]) -> bool:
        if connection is None:
            return True
        # asyncssh 不同版本连接对象方法名不一致：
        # 2.22.0 提供 is_closed()，部分版本/对象可能提供 is_closing()
        for method_name in ("is_closed", "is_closing"):
            state = cls._call_bool_method(connection, method_name)
            if state is not None:
                return state
        return False

    @classmethod
    def _channel_closed_or_closing(cls, channel: Any) -> bool:
        for method_name in ("is_closing", "is_closed"):
            state = cls._call_bool_method(channel, method_name)
            if state is not None:
                return state
        return False

    def _should_mark_connection_down(self, exc: Exception) -> bool:
        if isinstance(exc, ConnectionError):
            return True
        try:
            if self._connection_closed_or_closing(self._connection):
                return True
        except Exception:
            return True
        return self._looks_like_transport_error(exc)
    async def _open_terminal_process(
        self, cols: int, rows: int
    ) -> Tuple[Any, Any, Any, Any]:
        term_size = (rows, cols, 0, 0)
        shell_candidates: List[Tuple[Optional[str], float]] = [
            (None, 2.5),
            ("bash --noprofile --norc -i", 2.0),
            ("sh -i", 2.0),
        ]
        last_timeout: Optional[Exception] = None
        for command, timeout in shell_candidates:
            try:
                process = await asyncio.wait_for(
                    self._connection.create_process(
                        command,
                        term_type="xterm-256color",
                        term_size=term_size,
                        encoding=None,
                    ),
                    timeout=timeout,
                )
                return process.channel, process.stdin, process.stdout, process.stderr
            except asyncio.TimeoutError as exc:
                last_timeout = exc
                continue
        if last_timeout is not None:
            raise TimeoutError("创建终端通道超时，请重试")
        raise RuntimeError("创建终端通道失败")
    async def connect(
        self,
        host: str,
        port: int,
        username: str,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        key_passphrase: Optional[str] = None,
    ) -> str:
        if self._connected:
            await self.disconnect()
        kwargs: Dict[str, Any] = {
            "host": host,
            "port": port,
            "username": username,
            "known_hosts": None,
            "connect_timeout": 8,
            "login_timeout": 8,
            "keepalive_interval": 20,
            "keepalive_count_max": 3,
        }
        if password:
            kwargs["password"] = password
        if private_key:
            if os.path.isfile(private_key):
                kwargs["client_keys"] = [private_key]
                if key_passphrase:
                    kwargs["passphrase"] = key_passphrase
            else:
                kwargs["client_keys"] = [private_key]
        self._connection = await asyncssh.connect(**kwargs)
        self._connected = True
        self._host = host
        self._port = port
        self._username = username
        self._last_state_note = "已建立 SSH transport 连接"
        self._connection_info = ConnectionInfo(
            host=host,
            port=port,
            username=username,
            auth_method="key" if private_key else "password",
        )

        # 刚连接成功先进入短暂宽限期，避免“连接建立后立即探测”把瞬时会话拥塞误判为失败。
        # 后续由状态轮询与真实命令执行继续校验可用性。
        self._last_alive_probe_at = time.monotonic()

        return f"已连接到 {username}@{host}:{port}"
    async def disconnect(self) -> None:
        await self.close_all_terminal_sessions()
        if self._sftp:
            self._sftp.exit()
            self._sftp = None
        if self._connection:
            self._connection.close()
            await self._connection.wait_closed()
            self._connection = None
        self._connected = False
        self._last_state_note = "已主动断开连接"
        self._connection_info = None
        self._last_alive_probe_at = 0.0
    def is_connected(self) -> bool:
        """检查 SSH 连接是否有效（同步快速检查）"""
        if self._connection is None:
            return False
        # 额外检查连接对象是否真正存活
        try:
            # 检查底层传输是否关闭
            closing = self._connection_closed_or_closing(self._connection)
            if closing:
                self._connected = False
                self._last_state_note = "底层连接已关闭或正在关闭"
                print(f"[SSH] is_connected() 检测到连接已关闭/关闭中: _connected={self._connected}, is_closed_or_closing={closing}")
                return False
            if not self._connected:
                # 旁路通道错误可能把 _connected 标志置为 False，但 transport 仍可用，自动自愈。
                self._connected = True
            return True
        except Exception as e:
            self._connected = False
            self._last_state_note = f"is_connected 检查异常: {e}"
            print(f"[SSH] is_connected() 检查异常: {e}")
            return False

    async def check_alive(self) -> bool:
        """检查 SSH 连接是否真正存活（执行轻量命令验证）"""
        return await self._check_alive_internal(force=False)

    async def _check_alive_internal(self, force: bool = False) -> bool:
        """按需执行活性探测，避免高频轮询时每次都打远端命令。"""
        if not self.is_connected():
            return False

        now = time.monotonic()
        if not force and (now - self._last_alive_probe_at) < self._status_probe_ttl:
            return True

        try:
            result = await asyncio.wait_for(
                self._connection.run("echo ok", check=False, encoding=None),
                timeout=2
            )
            self._last_alive_probe_at = now
            # 只要能拿到命令执行结果，说明传输层仍可用。
            # 非零退出码可能来自受限策略/环境，不应在这里直接判定为断链。
            return True
        except Exception as e:
            if self._should_mark_connection_down(e):
                self._connected = False
                self._last_state_note = f"活性探测判定断链: {e}"
            self._last_alive_probe_at = now
            # 会话拥塞（如 MaxSessions）不应误判为断链，保留连接态。
            if self._looks_like_session_pressure_error(e):
                return True
            # 如果只是命令/子系统能力受限，也不应直接判定传输层断链。
            if self._looks_like_exec_forbidden_error(e) or self._looks_like_sftp_subsystem_error(e):
                return True
            return False
    async def execute_command(self, command: str) -> TerminalOutput:
        if not self.is_connected():
            # 连接已断开，更新内部状态
            print(f"[SSH] execute_command 失败: is_connected()=False, _connected={self._connected}, _connection={self._connection is not None}, command={command[:80]}...")
            self._connected = False
            self._last_state_note = "命令执行前发现连接不可用"
            raise ConnectionError("没有活动的 SSH 连接")
        try:
            async with self._channel_semaphore:
                for attempt in range(self._channel_open_retries + 1):
                    try:
                        result = await self._connection.run(command, check=False, encoding=None)
                        stdout_bytes = result.stdout or b""
                        output = stdout_bytes.decode("utf-8", errors="replace")
                        return TerminalOutput.create(
                            command=command, output=output, exit_code=result.exit_status
                        )
                    except (ConnectionError, OSError, asyncssh.Error) as e:
                        transient_session_pressure = (
                            self._looks_like_session_pressure_error(e)
                            and not self._should_mark_connection_down(e)
                        )
                        if (
                            self._looks_like_exec_forbidden_error(e)
                            and not self._should_mark_connection_down(e)
                        ):
                            raise ValueError(
                                "目标服务器禁止 exec 命令（可能配置了 ForceCommand/internal-sftp 或受限账号策略）"
                            ) from e
                        if transient_session_pressure and attempt < self._channel_open_retries:
                            await asyncio.sleep(self._channel_retry_base_delay * (attempt + 1))
                            continue
                        if self._should_mark_connection_down(e):
                            self._connected = False
                            self._sftp = None
                            self._last_state_note = f"命令执行判定断链: {e}"
                        raise
        except (ConnectionError, OSError, asyncssh.Error):
            raise
        except Exception as e:
            return TerminalOutput.create(command=command, output=str(e), exit_code=-1)
    async def execute_dashboard_command(self, command: str) -> TerminalOutput:
        return await self.execute_command(command)
    async def execute_dashboard_command_as_user(
        self, command: str, username: Optional[str] = None
    ) -> TerminalOutput:
        if username and username != self._username:
            return await self.execute_command(f"sudo -u {username} {command}")
        return await self.execute_command(command)
    async def get_connection_status(self) -> Optional[SSHConnectionStatus]:
        if not self.is_connected():
            return None

        # 对外暴露状态前做一次低频活性探测，减少“状态显示在线但操作失败”的窗口。
        if not await self._check_alive_internal(force=False):
            return None

        return SSHConnectionStatus(
            connected=True,
            host=self._host,
            port=self._port,
            username=self._username,
            last_activity=datetime.now(timezone.utc),
        )
    async def _ensure_sftp(self) -> asyncssh.SFTPClient:
        if not self.is_connected():
            raise ConnectionError("没有活动的 SSH 连接")
        if self._sftp is None:
            async with self._channel_semaphore:
                for attempt in range(self._channel_open_retries + 1):
                    try:
                        self._sftp = await self._connection.start_sftp_client()
                        break
                    except (ConnectionError, OSError, asyncssh.Error) as e:
                        transient_session_pressure = (
                            self._looks_like_session_pressure_error(e)
                            and not self._should_mark_connection_down(e)
                        )
                        if (
                            self._looks_like_sftp_subsystem_error(e)
                            and not self._should_mark_connection_down(e)
                        ):
                            raise ValueError(
                                "目标服务器未启用 SFTP 子系统或当前账号无 SFTP 权限"
                            ) from e
                        if transient_session_pressure and attempt < self._channel_open_retries:
                            await asyncio.sleep(self._channel_retry_base_delay * (attempt + 1))
                            continue
                        if self._should_mark_connection_down(e):
                            self._connected = False
                            self._last_state_note = f"SFTP 建链判定断链: {e}"
                        self._sftp = None
                        raise
        return self._sftp

    def get_connection_health(self) -> Dict[str, Any]:
        has_connection = self._connection is not None
        is_closed: Optional[bool] = None
        is_closing: Optional[bool] = None
        if self._connection is not None:
            is_closed = self._call_bool_method(self._connection, "is_closed")
            is_closing = self._call_bool_method(self._connection, "is_closing")
        return {
            "connected_flag": self._connected,
            "has_connection": has_connection,
            "is_closed": is_closed,
            "is_closing": is_closing,
            "host": self._host,
            "port": self._port,
            "username": self._username,
            "last_note": self._last_state_note,
        }
    @staticmethod
    def _join_remote(path: str, name: str) -> str:
        if path == "/":
            return f"/{name}"
        return f"{path.rstrip('/')}/{name}"
    @staticmethod
    def _sftp_entry_filename(entry: Any) -> str:
        raw = getattr(entry, "filename", None) or getattr(entry, "name", "") or ""
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw).decode("utf-8", errors="surrogateescape")
        return str(raw)
    @staticmethod
    def _perm_to_str(mode: Optional[int]) -> Optional[str]:
        if mode is None:
            return None
        perms = []
        file_type = "d" if (mode & 0o40000) else ("l" if (mode & 0o120000) else "-")
        perms.append(file_type)
        for shift in (6, 3, 0):
            p = (mode >> shift) & 0b111
            perms.append("r" if p & 0b100 else "-")
            perms.append("w" if p & 0b010 else "-")
            perms.append("x" if p & 0b001 else "-")
        return "".join(perms)
    @staticmethod
    def _epoch_to_iso(ts: Optional[int]) -> Optional[str]:
        if ts is None:
            return None
        try:
            t = int(ts)
            if t <= 0:
                return None
            return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
        except (OSError, OverflowError, ValueError):
            return None
    @staticmethod
    def _classify_sftp_entry(attrs: Optional[asyncssh.SFTPAttrs]) -> Tuple[str, bool]:
        mode = attrs.permissions if attrs else None
        file_type = "file"
        is_dir = False
        if attrs is not None and attrs.type != FILEXFER_TYPE_UNKNOWN:
            if attrs.type == FILEXFER_TYPE_DIRECTORY:
                return "directory", True
            if attrs.type == FILEXFER_TYPE_SYMLINK:
                return "symlink", False
        if mode is not None:
            if mode & 0o40000:
                return "directory", True
            if mode & 0o120000:
                return "symlink", False
        return file_type, is_dir
    async def list_sftp_files(self, path: str) -> List[SftpFileInfo]:
        sftp = await self._ensure_sftp()
        out: List[SftpFileInfo] = []
        for entry in await sftp.readdir(path):
            fname = self._sftp_entry_filename(entry)
            attrs = entry.attrs
            mode = attrs.permissions if attrs else None
            file_type, is_dir = self._classify_sftp_entry(attrs)
            out.append(
                SftpFileInfo(
                    name=fname,
                    path=self._join_remote(path, fname),
                    file_type=file_type,
                    is_dir=is_dir,
                    size=(attrs.size if attrs and attrs.size is not None else 0),
                    modified=self._epoch_to_iso(attrs.mtime if attrs else None),
                    permissions=self._perm_to_str(mode),
                )
            )
        return out
    async def read_sftp_file(self, path: str) -> bytes:
        sftp = await self._ensure_sftp()
        async with sftp.open(path, "rb") as f:
            return await f.read()
    async def write_sftp_file(self, path: str, content: bytes) -> None:
        sftp = await self._ensure_sftp()
        async with sftp.open(path, "wb", encoding=None) as f:
            await f.write(content)
    async def upload_file(
        self,
        local_path: str,
        remote_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> None:
        sftp = await self._ensure_sftp()
        chunk_size = 32768
        total_size = os.path.getsize(local_path)
        transferred = 0
        async with sftp.open(remote_path, "wb", encoding=None) as remote_f:
            with open(local_path, "rb") as local_f:
                while True:
                    chunk = local_f.read(chunk_size)
                    if not chunk:
                        break
                    await remote_f.write(chunk)
                    transferred += len(chunk)
                    if progress_callback:
                        progress_callback(transferred, total_size)
    async def download_file(self, remote_path: str, local_path: str) -> None:
        sftp = await self._ensure_sftp()
        chunk_size = 32768
        with open(local_path, "wb") as local_f:
            async with sftp.open(remote_path, "rb", encoding=None) as remote_f:
                while True:
                    chunk = await remote_f.read(chunk_size)
                    if not chunk:
                        break
                    local_f.write(chunk)
    async def create_directory(self, remote_path: str) -> None:
        sftp = await self._ensure_sftp()
        await sftp.mkdir(remote_path)
    async def chmod_sftp(self, path: str, mode: int) -> None:
        sftp = await self._ensure_sftp()
        await sftp.chmod(path, mode)
    async def get_file_details(self, path: str) -> SftpFileDetails:
        sftp = await self._ensure_sftp()
        attrs = await sftp.stat(path)
        mode = attrs.permissions if attrs else None
        file_type, _is_dir = self._classify_sftp_entry(attrs)
        crtime = getattr(attrs, "crtime", None) if attrs else None
        return SftpFileDetails(
            name=path.rsplit("/", 1)[-1],
            path=path,
            file_type=file_type,
            size=(attrs.size if attrs and attrs.size is not None else 0),
            permissions=self._perm_to_str(mode) or "",
            owner=str(attrs.uid) if attrs and attrs.uid is not None else None,
            group=str(attrs.gid) if attrs and attrs.gid is not None else None,
            created=self._epoch_to_iso(crtime),
            modified=self._epoch_to_iso(attrs.mtime if attrs else None),
            accessed=self._epoch_to_iso(attrs.atime if attrs else None),
        )
    async def compress_file(self, source_path: str, target_path: str, fmt: str) -> None:
        normalized_source = source_path.rstrip("/") or "/"
        parent_dir = os.path.dirname(normalized_source) or "/"
        entry_name = os.path.basename(normalized_source) or "."

        quoted_target = shlex.quote(target_path)
        quoted_parent = shlex.quote(parent_dir)
        quoted_entry = shlex.quote(entry_name)

        # 在源对象的父目录执行归档，确保“选中的文件/目录本身”被打进压缩包。
        if fmt in ("tar.gz", "tgz"):
            cmd = f'tar -czf {quoted_target} -C {quoted_parent} {quoted_entry}'
        elif fmt == "tar":
            cmd = f'tar -cf {quoted_target} -C {quoted_parent} {quoted_entry}'
        elif fmt in ("tar.bz2", "tbz2"):
            cmd = f'tar -cjf {quoted_target} -C {quoted_parent} {quoted_entry}'
        elif fmt == "zip":
            cmd = f'cd {quoted_parent} && zip -r {quoted_target} {quoted_entry}'
        else:
            cmd = f'tar -czf {quoted_target} -C {quoted_parent} {quoted_entry}'
        result = await self.execute_command(cmd)
        if result.exit_code and result.exit_code != 0:
            raise RuntimeError(result.output)
    async def extract_file(self, archive_path: str, target_dir: str) -> None:
        if archive_path.endswith((".tar.gz", ".tgz")):
            cmd = f'mkdir -p "{target_dir}" && tar -xzf "{archive_path}" -C "{target_dir}"'
        elif archive_path.endswith((".tar.bz2", ".tbz2")):
            cmd = f'mkdir -p "{target_dir}" && tar -xjf "{archive_path}" -C "{target_dir}"'
        elif archive_path.endswith(".tar"):
            cmd = (
                f'mkdir -p "{target_dir}" && tar -xf "{archive_path}" -C "{target_dir}"'
            )
        elif archive_path.endswith(".zip"):
            cmd = f'mkdir -p "{target_dir}" && unzip -o "{archive_path}" -d "{target_dir}"'
        else:
            cmd = f'mkdir -p "{target_dir}" && tar -xzf "{archive_path}" -C "{target_dir}"'
        result = await self.execute_command(cmd)
        if result.exit_code and result.exit_code != 0:
            raise RuntimeError(result.output)
    async def create_terminal_session(
        self, terminal_id: str, cols: int = 80, rows: int = 24
    ) -> str:
        if not self.is_connected():
            raise ConnectionError("没有活动的 SSH 连接")
        lock = self._terminal_session_locks.setdefault(terminal_id, asyncio.Lock())
        async with lock:
            session = self._terminal_sessions.get(terminal_id)
            if session:
                try:
                    if not self._channel_closed_or_closing(session["channel"]):
                        return terminal_id
                except Exception:
                    pass
                self._terminal_sessions.pop(terminal_id, None)
            # 创建新通道前验证连接是否真的存活
            if not await self.check_alive():
                self._connected = False
                raise ConnectionError("SSH 连接已断开")
            channel, stdin, stdout, stderr = await self._open_terminal_process(
                cols, rows
            )
            self._terminal_sessions[terminal_id] = {
                "channel": channel,
                "stdin": stdin,
                "stdout": stdout,
                "stderr": stderr,
                "cols": cols,
                "rows": rows,
            }
            return terminal_id
    def has_terminal_session(self, terminal_id: str) -> bool:
        return terminal_id in self._terminal_sessions
    async def close_terminal_session(self, terminal_id: str) -> None:
        session = self._terminal_sessions.pop(terminal_id, None)
        self._terminal_session_locks.pop(terminal_id, None)
        if session:
            try:
                session["channel"].close()
            except Exception:
                pass
    async def close_all_terminal_sessions(self) -> None:
        for tid in list(self._terminal_sessions.keys()):
            await self.close_terminal_session(tid)
    async def send_terminal_input(self, terminal_id: str, data: bytes) -> None:
        session = self._terminal_sessions.get(terminal_id)
        if not session:
            raise ValueError(f"终端会话不存在: {terminal_id}")
        session["stdin"].write(data)
        await session["stdin"].drain()
    async def read_terminal_output(
        self, terminal_id: str, timeout: float = 0.02
    ) -> bytes:
        session = self._terminal_sessions.get(terminal_id)
        if not session:
            raise ValueError(f"终端会话不存在: {terminal_id}")
        try:
            data = await asyncio.wait_for(session["stdout"].read(4096), timeout=timeout)
            if not data:
                return b""

            chunks = [data]
            total = len(data)

            # 已经读到首块数据后，快速追加后续就绪输出，减少一次命令被拆成多次推送。
            while total < 65536:
                try:
                    more = await asyncio.wait_for(session["stdout"].read(4096), timeout=0.001)
                    if not more:
                        break
                    chunks.append(more)
                    total += len(more)
                except asyncio.TimeoutError:
                    break

            return b"".join(chunks)
        except asyncio.TimeoutError:
            return b""
        except (ConnectionError, OSError, asyncssh.Error) as e:
            # 仅在传输层断开时标记连接失效，避免通道级瞬时错误污染全局连接态。
            if self._should_mark_connection_down(e):
                self._connected = False
            raise
        except Exception:
            return b""
    async def resize_terminal(self, terminal_id: str, cols: int, rows: int) -> None:
        session = self._terminal_sessions.get(terminal_id)
        if not session:
            raise ValueError(f"终端会话不存在: {terminal_id}")
        session["cols"] = cols
        session["rows"] = rows
        session["channel"].change_terminal_size((rows, cols, 0, 0))
    async def get_bash_environment_info(self) -> BashEnvironmentInfo:
        cmds = {
            "bash_version": "bash --version 2>/dev/null | head -1 || echo 'unknown'",
            "shell_type": "echo $SHELL 2>/dev/null || echo 'sh'",
            "ps1": "echo \"$PS1\" 2>/dev/null || echo '$ '",
            "pwd": "pwd",
            "home": "echo $HOME",
            "user": "whoami",
            "hostname": "hostname",
            "path": "echo $PATH",
        }
        out: Dict[str, str] = {}
        for k, cmd in cmds.items():
            try:
                r = await self.execute_command(cmd)
                out[k] = (r.output or "").strip()
            except Exception:
                out[k] = ""
        return BashEnvironmentInfo(**out)
    async def get_command_completion(self, input_text: str) -> CommandCompletion:
        words = input_text.split()
        completions: List[str] = []
        if not words or (len(words) == 1 and not input_text.endswith(" ")):
            common = [
                "ls",
                "cd",
                "pwd",
                "cat",
                "grep",
                "find",
                "ps",
                "top",
                "htop",
                "df",
                "du",
                "free",
                "uname",
                "whoami",
                "id",
                "groups",
                "chmod",
                "chown",
                "cp",
                "mv",
                "rm",
                "mkdir",
                "rmdir",
                "tar",
                "gzip",
                "gunzip",
                "zip",
                "unzip",
                "vim",
                "nano",
                "less",
                "more",
                "head",
                "tail",
                "ssh",
                "scp",
                "rsync",
                "wget",
                "curl",
                "systemctl",
                "service",
                "crontab",
                "history",
                "awk",
                "sed",
                "sort",
                "uniq",
                "wc",
                "tr",
            ]
            prefix = words[-1] if words else ""
            completions = [c for c in common if c.startswith(prefix)]
        else:
            last_word = words[-1]
            dir_path = "."
            if "/" in last_word:
                dir_path = last_word.rsplit("/", 1)[0] or "/"
            try:
                r = await self.execute_command(f"ls -1a {dir_path}")
                files = (r.output or "").split("\n")
                prefix = last_word.split("/")[-1]
                for f in files:
                    f = f.strip()
                    if f and f not in (".", "..") and f.startswith(prefix):
                        if "/" in last_word:
                            completions.append(
                                f"{last_word[: last_word.rfind('/') + 1]}{f}"
                            )
                        else:
                            completions.append(f)
            except Exception:
                pass
        return CommandCompletion(completions=completions, prefix=input_text)
