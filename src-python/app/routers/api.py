from __future__ import annotations
import json
import hashlib
import os
import tempfile
import time
import asyncio
import logging
logger = logging.getLogger(__name__)
import re
import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar, Literal
from urllib.parse import urlparse
import asyncssh
import httpx
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.models.types import (
    SSHConnection,
    TerminalOutput,
)
from app.services import detection_manager, file_analysis, log_analysis
from app.services.ssh_connection_manager import SSHConnectionManager
from app.services.ssh_manager import SSHManager
from app.services.settings import (
    AppSettings,
    load_settings,
    read_settings_file,
    save_settings,
    write_settings_file,
)
from app.services.theme_manager import get_theme_settings
from app.services.device_info import get_device_uuid
from app.services.window_manager import WindowManager
from app.core.secret_store import SecretRef, SecretStore
from app.utils.crypto import get_rsa_public_key
from app.utils.system_fonts import get_system_fonts
router = APIRouter(prefix="/api/v1", tags=["sdit"])
T = TypeVar("T")
async def _wrap_ssh_transport(factory: Callable[[], Awaitable[T]]) -> T:
    try:
        return await factory()
    except ConnectionError as e:
        msg = str(e) or "没有活动的 SSH 连接，请先在应用中连接 SSH 后再使用 SFTP。"
        raise HTTPException(status_code=400, detail=msg) from e
    except asyncssh.Error as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
_ssh_manager: Optional[SSHManager] = None
"""SSH 实时连接管理器单例，持有当前活动的 SSH/PTY 连接和 SFTP 会话。"""
_ssh_connection_manager: Optional[SSHConnectionManager] = None
"""SSH 连接配置管理器单例，负责连接配置的加密存储、加载、删除等持久化操作。"""
_window_manager: Optional[WindowManager] = None
"""桌面窗口管理器单例，支持最小化、最大化、关闭及开发者工具等窗口操作。"""
_app_settings: Optional[AppSettings] = None
"""应用设置单例（主题、语言、快捷键等），启动时从本地配置文件加载。"""
_sftp_upload_progress: Dict[str, Dict[str, Any]] = {}
_ssh_secret_store = SecretStore(service="sdit-ssh-runtime", persistent=False)
_model_secret_store = SecretStore(service="sdit-model-api-key", persistent=True)
"""SFTP 上传进度缓存，按 upload_id 记录当前阶段与字节进度。"""


def _set_sftp_upload_progress(
    upload_id: str,
    *,
    stage: str,
    transferred_bytes: int,
    total_bytes: int,
    done: bool = False,
    success: bool = False,
    error: Optional[str] = None,
) -> None:
    safe_total = max(int(total_bytes or 0), 0)
    safe_transferred = max(0, min(int(transferred_bytes or 0), safe_total if safe_total > 0 else int(transferred_bytes or 0)))
    percent = 100.0 if done and success else (safe_transferred / safe_total * 100 if safe_total > 0 else 0.0)
    _sftp_upload_progress[upload_id] = {
        "upload_id": upload_id,
        "stage": stage,
        "transferred_bytes": safe_transferred,
        "total_bytes": safe_total,
        "percent": percent,
        "done": done,
        "success": success,
        "error": error,
        "updated_at": time.time(),
    }
def init_state():
    global _ssh_manager, _ssh_connection_manager, _window_manager, _app_settings
    _ssh_manager = SSHManager()
    _ssh_connection_manager = SSHConnectionManager()
    _window_manager = WindowManager()
    _app_settings = load_settings()
    print("SDIT Python 后端初始化完成")
def get_ssh_manager() -> SSHManager:
    if _ssh_manager is None:
        raise HTTPException(status_code=500, detail="SSH管理器未初始化")
    return _ssh_manager
def get_connection_manager() -> SSHConnectionManager:
    if _ssh_connection_manager is None:
        raise HTTPException(status_code=500, detail="SSH连接管理器未初始化")
    return _ssh_connection_manager


def _resolve_secret_ref(value: Optional[str]) -> Optional[str]:
    """Resolve an opaque runtime reference without returning its value to clients."""
    if value is None or not str(value).strip():
        return value
    candidate = str(value).strip()
    if not candidate.startswith("secret_"):
        return candidate
    resolved = _ssh_secret_store.resolve(candidate)
    if resolved is None:
        raise HTTPException(status_code=400, detail="secret reference expired")
    return resolved


def _resolve_model_api_key(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate.startswith("secret_"):
        return candidate
    resolved = _model_secret_store.resolve(candidate)
    if resolved is None:
        raise HTTPException(status_code=400, detail="model secret reference expired")
    return resolved
class ConnectDirectRequest(BaseModel):
    host: str
    """目标服务器 IP 或域名"""
    port: int = 22
    """SSH 端口，默认 22"""
    username: str
    """登录用户名"""
    password: Optional[str] = None
    secret_ref: Optional[str] = None
    """短时运行时凭据引用；优先于 password。"""
class ConnectWithAuthRequest(BaseModel):
    host: str
    """目标服务器 IP 或域名"""
    port: int = 22
    """SSH 端口，默认 22"""
    username: str
    """登录用户名"""
    auth_type: str = "password"
    """认证类型：password / key / certificate"""
    password: Optional[str] = None
    secret_ref: Optional[str] = None
    """短时运行时凭据引用；优先于 password。"""
    key_path: Optional[str] = None
    """私钥文件路径（auth_type=key 时必需）"""
    key_passphrase: Optional[str] = None
    """私钥密码（auth_type=key 时可选）"""
    certificate_path: Optional[str] = None
    """证书文件路径（auth_type=certificate 时必需）"""
class ExecuteCommandRequest(BaseModel):
    command: str
    """要执行的 Shell 命令"""
    username: Optional[str] = None
    """以指定用户身份执行（可选），底层使用 sudo -u 实现"""
class SftpWriteRequest(BaseModel):
    path: str
    """远程文件绝对路径"""
    content: str
    """要写入的文本内容（UTF-8 编码后写入）"""
class SftpCompressRequest(BaseModel):
    source_path: str
    """要压缩的源文件/目录路径"""
    target_path: str
    """压缩后的目标文件路径（含文件名，如 /tmp/backup.tar.gz）"""
    format: str = "tar.gz"
    """压缩格式，当前支持 tar.gz / zip"""
class SftpExtractRequest(BaseModel):
    archive_path: str
    """远程压缩包路径"""
    target_dir: str
    """解压目标目录"""
    overwrite: bool = True
    """是否覆盖已存在的文件，默认 True"""
class SftpUploadRequest(BaseModel):
    local_path: str
    """本地文件绝对路径"""
    remote_path: str
    """远程目标路径"""
class SftpDownloadRequest(BaseModel):
    remote_path: str
    """远程文件路径"""
    local_path: str
    """本地保存路径"""
class SftpChmodRequest(BaseModel):
    path: str
    """远程文件/目录路径"""
    mode: int
    """权限模式（八进制，如 0o755 对应十进制 493）"""
class SaveTempFileRequest(BaseModel):
    file_name: str
    """文件名"""
    data: str
    """Base64 编码的文件内容"""
class DockerActionRequest(BaseModel):
    container_id: str
    """Docker 容器 ID 或名称"""
    action: str
    """操作类型：start / stop / restart / pause / unpause / remove"""
class DockerLogsOptions(BaseModel):
    stdout: bool = True
    """是否包含标准输出日志，默认 True"""
    stderr: bool = True
    """是否包含标准错误日志，默认 True"""
    timestamps: bool = False
    """是否显示时间戳，默认 False"""
    tail: Optional[int] = None
    """只显示最后 N 行日志"""
    since: Optional[str] = None
    """从指定时间开始显示（如 "2024-01-01T00:00:00"）"""
    until: Optional[str] = None
    """显示到指定时间为止（如 "2024-01-02T00:00:00"）"""
    follow: bool = False
    """是否持续跟踪日志输出（类似 tail -f），默认 False"""
class DockerLogsRequest(BaseModel):
    container_id: str
    """Docker 容器 ID 或名称"""
    options: Optional[DockerLogsOptions] = None
    """日志查看选项，为 None 时使用默认选项"""
class DockerExecRequest(BaseModel):
    container_id: str
    """Docker 容器 ID 或名称"""
    command: str
    """要在容器内执行的命令"""
    shell: str = "sh"
    """使用的 Shell 类型，默认 sh（也可用 bash）"""
class DockerWriteFileRequest(BaseModel):
    container_id: str
    """Docker 容器 ID 或名称"""
    path: str
    """容器内的目标文件路径"""
    content: str
    """要写入的文本内容"""
class DockerCopyRequest(BaseModel):
    container_id: str
    """Docker 容器 ID 或名称"""
    direction: str
    """复制方向：to_container（本地→容器）/ from_container（容器→本地）"""
    source: str
    """源路径"""
    target: str
    """目标路径"""
class CreateTerminalSessionRequest(BaseModel):
    terminal_id: str
    """终端会话的唯一标识（由前端生成 UUID）"""
    cols: int = 80
    """终端列数（每行字符数），默认 80"""
    rows: int = 24
    """终端行数，默认 24"""
class SendTerminalInputRequest(BaseModel):
    terminal_id: str
    """目标终端会话 ID"""
    data: str
    """要发送的输入数据（键盘按键、控制序列等）"""
class SetThemeRequest(BaseModel):
    theme: str
    """主题名称，如 "light" / "dark"，由前端主题管理器定义"""
class SaveSettingsRequest(BaseModel):
    settings: Dict[str, Any]
    """设置键值对字典，会通过 AppSettings.model_validate 校验"""
class WriteSettingsFileRequest(BaseModel):
    content: str
    """配置文件的原始文本内容"""
class RemediationBudgetRequest(BaseModel):
    max_steps: int = 5
    """允许的总步骤数"""
    max_mutation_steps: int = 2
    """允许的变更类步骤数"""
    max_ssh_commands: int = 4
    """允许的 SSH 命令数"""
    max_http_requests: int = 0
    """预留的 HTTP 请求预算"""
class SelectedRemediationFinding(BaseModel):
    finding_id: str
    """漏洞或修复项 ID"""
    title: str
    """前端展示标题"""
    commands: List[str] = Field(default_factory=list)
    """执行修复时要运行的命令"""
    verify_commands: List[str] = Field(default_factory=list)
    """修复后验证命令"""
    rollback_commands: List[str] = Field(default_factory=list)
    """回滚命令"""
class ExecuteSelectedRemediationsRequest(BaseModel):
    task: str
    """执行任务标题"""
    dry_run: bool = False
    """是否仅预览不真实执行"""
    auto_approve: bool = False
    """是否自动批准高风险步骤"""
    approval_ids: List[str] = Field(default_factory=list)
    """审批票据 ID"""
    approved_finding_ids: List[str] = Field(default_factory=list)
    """已批准的 finding ID"""
    rollback_mode: str = "none"
    """回滚模式: none / preview / execute"""
    budget: RemediationBudgetRequest = Field(default_factory=RemediationBudgetRequest)
    """执行预算"""
    selected_findings: List[SelectedRemediationFinding] = Field(default_factory=list)
    """需要执行的修复项"""
class EncryptPasswordRequest(BaseModel):
    password: str
    """明文密码"""
class DecryptPasswordRequest(BaseModel):
    encrypted_password: str
    """已加密的密码字符串"""
class ReadSystemLogRequest(BaseModel):
    log_path: str
    """远程日志文件绝对路径（如 /var/log/syslog）"""
    page: int = 1
    """页码，从 1 开始，默认第 1 页"""
    page_size: int = 100
    """每页行数，默认 100"""
    filter: Optional[str] = None
    """关键字过滤（grep 风格），为 None 时不过滤"""
    date_filter: Optional[str] = None
    """日期过滤（格式如 "2024-01-01"），为 None 时不过滤"""
    level_filter: Optional[str] = None
    """日志级别过滤（如 "error,warning"），为 None 时不过滤"""
class ReadJournalctlLogRequest(BaseModel):
    page: int = 1
    """页码，从 1 开始"""
    page_size: int = 100
    """每页条目数"""
    unit: Optional[str] = None
    """systemd 服务单元名（如 sshd.service），为 None 时显示所有单元"""
    filter: Optional[str] = None
    """关键字过滤，为 None 时不过滤"""
    since: Optional[str] = None
    """起始时间（如 "2024-01-01" 或 "1 hour ago"）"""
    until: Optional[str] = None
    """截止时间（如 "2024-01-02"）"""
    level_filter: Optional[str] = None
    """日志级别过滤（如 "error,warning"），为 None 时不过滤"""
class FileAnalysisRequest(BaseModel):
    path: str
    """远程服务器上的文件绝对路径"""
    action: Optional[str] = None
    """可选的分析动作（如 md5 / sha256 / strings / elf 等），
       为 None 时执行完整分析"""
class DialogFilterRequest(BaseModel):
    name: Optional[str] = None
    """过滤器显示名称（如 "文本文件"）"""
    extensions: List[str] = Field(default_factory=list)
    """文件扩展名列表（如 [".txt", ".md"]）"""
class OpenDialogRequest(BaseModel):
    multiple: bool = False
    """是否允许多选文件，默认 False"""
    directory: bool = False
    """是否选择目录（directory=True 时忽略 multiple 参数），默认 False"""
    filters: List[DialogFilterRequest] = Field(default_factory=list)
    """文件类型过滤器列表"""
    default_path: Optional[str] = None
    """对话框打开时的默认路径"""
class SaveDialogRequest(BaseModel):
    filters: List[DialogFilterRequest] = Field(default_factory=list)
    """文件类型过滤器列表"""
    default_path: Optional[str] = None
    """对话框打开时的默认路径和默认文件名"""
class AIChatProxyRequest(BaseModel):
    url: str
    """目标 AI 接口地址"""
    headers: Dict[str, str] = Field(default_factory=dict)
    """请求头（Authorization / x-api-key 等）"""
    body: Dict[str, Any] = Field(default_factory=dict)
    """请求体（兼容 OpenAI / Claude / Ollama）"""
    timeout_seconds: float = 90.0
    """超时时间（秒）"""
def _validate_proxy_target_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="AI 目标 URL 不能为空")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="AI 目标 URL 仅支持 http/https")
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="AI 目标 URL 缺少主机名")
    return url
def _normalize_timeout(timeout_seconds: float) -> httpx.Timeout:
    value = float(timeout_seconds or 90.0)
    if value <= 0:
        value = 90.0
    connect_timeout = min(30.0, max(5.0, value / 3))
    return httpx.Timeout(timeout=value, connect=connect_timeout)
def _normalize_proxy_headers(headers: Dict[str, str]) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    for key, value in (headers or {}).items():
        k = str(key).strip()
        if not k:
            continue
        kl = k.lower()
        if kl in ("host", "content-length"):
            continue
        normalized[k] = str(value)
    return normalized
def _extract_error_detail_from_text(raw: str, fallback: str) -> str:
    text = (raw or "").strip()
    if not text:
        return fallback
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    if isinstance(parsed, dict):
        detail = parsed.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        message = parsed.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        error = parsed.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        if isinstance(error, dict):
            nested = error.get("message") or error.get("detail") or error.get("error")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return json.dumps(parsed, ensure_ascii=False)
    return text
async def _read_upstream_error_detail(response: httpx.Response) -> str:
    fallback = f"HTTP {response.status_code}"
    try:
        raw = await response.aread()
    except Exception:
        return fallback
    text = raw.decode("utf-8", errors="ignore")
    return _extract_error_detail_from_text(text, fallback)
def _read_json_or_text(response: httpx.Response) -> Any:
    content_type = (response.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            return response.json()
        except Exception:
            pass
    text = response.text if response.text is not None else ""
    text = text.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {"text": text}
def _build_approval_ticket(task: str, finding: SelectedRemediationFinding) -> Dict[str, Any]:
    ticket_id = f"approval-{finding.finding_id}-{time.time_ns()}"
    return {
        "id": ticket_id,
        "finding_id": finding.finding_id,
        "title": finding.title,
        "task": task,
        "status": "draft",
    }
def _is_remediation_approved(
    req: ExecuteSelectedRemediationsRequest,
    finding: SelectedRemediationFinding,
) -> bool:
    if req.auto_approve:
        return True
    if finding.finding_id in req.approved_finding_ids:
        return True
    if finding.finding_id in req.approval_ids:
        return True
    return False
def _safe_get_remediation_ssh() -> tuple[Optional[Any], Optional[str]]:
    try:
        return get_ssh_manager(), None
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return None, detail
    except Exception as exc:
        return None, str(exc)
def _is_ssh_connected_for_remediation(ssh: Any) -> bool:
    if ssh is None:
        return False
    checker = getattr(ssh, "is_connected", None)
    if not callable(checker):
        return False
    try:
        return bool(checker())
    except Exception:
        return False
def _build_budget_snapshot(
    budget: RemediationBudgetRequest,
    finding: SelectedRemediationFinding,
    rollback_mode: str,
) -> Dict[str, int]:
    if rollback_mode == "execute":
        requested_steps = len(finding.rollback_commands)
        requested_mutation_steps = len(finding.rollback_commands)
        requested_ssh_commands = len(finding.rollback_commands)
    else:
        requested_steps = len(finding.commands) + len(finding.verify_commands)
        requested_mutation_steps = len(finding.commands)
        requested_ssh_commands = requested_steps
    return {
        "max_steps": budget.max_steps,
        "max_mutation_steps": budget.max_mutation_steps,
        "max_ssh_commands": budget.max_ssh_commands,
        "max_http_requests": budget.max_http_requests,
        "requested_steps": requested_steps,
        "requested_mutation_steps": requested_mutation_steps,
        "requested_ssh_commands": requested_ssh_commands,
        "requested_http_requests": 0,
    }
def _budget_violation(snapshot: Dict[str, int]) -> Optional[str]:
    checks = (
        ("max_steps", "requested_steps"),
        ("max_mutation_steps", "requested_mutation_steps"),
        ("max_ssh_commands", "requested_ssh_commands"),
        ("max_http_requests", "requested_http_requests"),
    )
    for max_key, requested_key in checks:
        if snapshot[requested_key] > snapshot[max_key]:
            return f"Budget exceeded: {requested_key}={snapshot[requested_key]} > {max_key}={snapshot[max_key]}"
    return None
async def _execute_ssh_commands(ssh: Any, commands: List[str]) -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    for command in commands:
        raw = await ssh.execute_command(command)
        if hasattr(raw, "model_dump"):
            normalized = raw.model_dump(mode="json")
        elif isinstance(raw, dict):
            normalized = dict(raw)
        else:
            normalized = {"output": str(raw)}
        normalized.setdefault("command", command)
        outputs.append(normalized)
    return outputs
def _run_native_dialog(kind: str, options: Dict[str, Any]) -> Any:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise RuntimeError("当前环境不支持本机文件对话框") from exc
    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    root.update()
    filters = options.get("filters") or []
    filetypes = []
    for item in filters:
        name = item.get("name") or "支持的文件"
        extensions = item.get("extensions") or []
        patterns = []
        for ext in extensions:
            if ext == "*":
                patterns.append("*.*")
            else:
                patterns.append(ext if ext.startswith("*.") else f"*.{ext.lstrip('.')}")
        if patterns:
            filetypes.append((name, " ".join(patterns)))
    if not filetypes:
        filetypes = [("所有文件", "*.*")]
    initialdir = None
    initialfile = None
    default_path = options.get("default_path")
    if default_path:
        normalized = os.path.normpath(default_path)
        if os.path.isdir(normalized):
            initialdir = normalized
        else:
            initialdir = os.path.dirname(normalized) or None
            initialfile = os.path.basename(normalized) or None
    dialog_kwargs: Dict[str, Any] = {"parent": root}
    if initialdir:
        dialog_kwargs["initialdir"] = initialdir
    if initialfile:
        dialog_kwargs["initialfile"] = initialfile
    if kind != "open_directory":
        dialog_kwargs["filetypes"] = filetypes
    try:
        if kind == "open_directory":
            result = filedialog.askdirectory(**dialog_kwargs)
        elif kind == "open_files":
            result = filedialog.askopenfilenames(**dialog_kwargs)
        elif kind == "open_file":
            result = filedialog.askopenfilename(**dialog_kwargs)
        elif kind == "save_file":
            result = filedialog.asksaveasfilename(**dialog_kwargs)
        else:
            raise RuntimeError("不支持的对话框类型")
    finally:
        root.destroy()
    if kind == "open_files":
        return list(result) if result else []
    return result or None
@router.post("/window/minimize")
async def minimize_window():
    return {"event": "window-minimize"}
@router.post("/window/toggle-maximize")
async def toggle_maximize():
    return {"event": "window-toggle-maximize"}
@router.post("/window/close")
async def close_window():
    return {"event": "window-close"}
@router.post("/window/open-devtools")
async def open_devtools():
    return {"event": "window-open-devtools"}
@router.post("/dialog/open")
async def open_dialog(req: OpenDialogRequest):
    kind = (
        "open_directory"
        if req.directory
        else "open_files"
        if req.multiple
        else "open_file"
    )
    try:
        path = await asyncio.to_thread(
            _run_native_dialog,
            kind,
            req.model_dump(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"打开文件对话框失败: {exc}"
        ) from exc
    return {"path": path if path else None}
@router.post("/dialog/save")
async def save_dialog(req: SaveDialogRequest):
    try:
        path = await asyncio.to_thread(
            _run_native_dialog,
            "save_file",
            req.model_dump(),
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"打开保存对话框失败: {exc}"
        ) from exc
    return {"path": path if path else None}
@router.get("/theme/settings")
async def get_theme():
    current_theme = _app_settings.theme if _app_settings else "light"
    return get_theme_settings(current_theme)
@router.post("/theme/set")
async def set_current_theme(req: SetThemeRequest):
    global _app_settings
    if _app_settings:
        _app_settings.theme = req.theme
        save_settings(_app_settings)
    return {"event": "theme-changed", "theme": req.theme}
@router.get("/settings")
async def get_app_settings():
    global _app_settings
    if _app_settings is None:
        _app_settings = load_settings()
    return _app_settings.model_dump()
@router.post("/settings/save")
async def save_app_settings(req: SaveSettingsRequest):
    global _app_settings
    try:
        _app_settings = AppSettings.model_validate(req.settings)
        save_settings(_app_settings)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.get("/settings/file")
async def read_settings():
    return {"content": read_settings_file()}
@router.post("/settings/file/write")
async def write_settings(req: WriteSettingsFileRequest):
    write_settings_file(req.content)
    return {"success": True}
@router.post("/ai/chat-proxy")
async def ai_chat_proxy(req: AIChatProxyRequest):
    url = _validate_proxy_target_url(req.url)
    headers = _normalize_proxy_headers(req.headers)
    body = req.body or {}
    timeout = _normalize_timeout(req.timeout_seconds)
    stream_enabled = bool(body.get("stream"))
    if stream_enabled:
        client = httpx.AsyncClient(timeout=timeout)
        try:
            request_obj = client.build_request("POST", url, headers=headers, json=body)
            upstream = await client.send(request_obj, stream=True)
        except httpx.RequestError as e:
            await client.aclose()
            raise HTTPException(status_code=502, detail=f"AI 代理请求失败: {e}") from e
        except Exception as e:
            await client.aclose()
            raise HTTPException(status_code=500, detail=f"AI 代理内部错误: {e}") from e
        if upstream.status_code >= 400:
            detail = await _read_upstream_error_detail(upstream)
            await upstream.aclose()
            await client.aclose()
            raise HTTPException(
                status_code=502,
                detail=f"AI 上游返回 {upstream.status_code}: {detail}",
            )
        media_type = upstream.headers.get("content-type") or "text/event-stream"
        async def _stream_body():
            try:
                async for chunk in upstream.aiter_raw():
                    if chunk:
                        yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()
        return StreamingResponse(_stream_body(), media_type=media_type)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.post(url, headers=headers, json=body)
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"AI 代理请求失败: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 代理内部错误: {e}") from e
    if upstream.status_code >= 400:
        detail = _extract_error_detail_from_text(upstream.text, f"HTTP {upstream.status_code}")
        raise HTTPException(
            status_code=502,
            detail=f"AI 上游返回 {upstream.status_code}: {detail}",
        )
    return {
        "status_code": upstream.status_code,
        "data": _read_json_or_text(upstream),
    }
@router.get("/system/fonts")
async def get_fonts():
    return {"fonts": get_system_fonts()}
@router.get("/ssh/connections")
async def load_ssh_connections():
    manager = get_connection_manager()
    connections = manager.load_connections()
    return [c.model_dump(mode="json") for c in connections]
@router.post("/ssh/connections/save")
async def save_ssh_connections(connections: List[SSHConnection]):
    manager = get_connection_manager()
    manager.save_connections(connections)
    return {"success": True}
@router.post("/ssh/encrypt-password")
async def encrypt_password(req: EncryptPasswordRequest):
    manager = get_connection_manager()
    return {"encrypted": manager.encrypt_password(req.password)}
@router.post("/ssh/decrypt-password")
async def decrypt_password(req: DecryptPasswordRequest):
    manager = get_connection_manager()
    try:
        secret = manager.decrypt_password(req.encrypted_password)
        ref: SecretRef = _ssh_secret_store.put(
            secret,
            kind="ssh-password",
            ttl_seconds=300,
        )
        return {
            "secret_ref": ref.ref,
            "kind": ref.kind,
            "fingerprint": ref.fingerprint,
            "expires_at": ref.expires_at,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail="encrypted credential could not be opened") from exc
@router.post("/ssh/connect")
async def ssh_connect_with_auth(req: ConnectWithAuthRequest):
    ssh = get_ssh_manager()
    try:
        password = _resolve_secret_ref(req.secret_ref or req.password)
        result = await ssh.connect(
            host=req.host,
            port=req.port,
            username=req.username,
            password=password,
            private_key=req.key_path,
            key_passphrase=req.key_passphrase,
        )
        return {"message": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.post("/ssh/test-connection")
async def ssh_test_connection(req: ConnectWithAuthRequest):
    ssh = get_ssh_manager()
    try:
        password = _resolve_secret_ref(req.secret_ref or req.password)
        await ssh.connect(
            host=req.host,
            port=req.port,
            username=req.username,
            password=password,
            private_key=req.key_path,
            key_passphrase=req.key_passphrase,
        )
        await ssh.disconnect()
        return {"success": True}
    except Exception:
        return {"success": False}
@router.post("/ssh/execute-command")
async def ssh_execute_command(req: ExecuteCommandRequest):
    ssh = get_ssh_manager()
    result = await ssh.execute_command(req.command)
    return result.model_dump(mode="json")
@router.post("/ssh/disconnect")
async def ssh_disconnect():
    ssh = get_ssh_manager()
    await ssh.disconnect()
    return {"success": True}
@router.post("/ssh/connect-direct")
async def ssh_connect_direct(req: ConnectDirectRequest):
    ssh = get_ssh_manager()
    try:
        await ssh.connect(
            host=req.host,
            port=req.port,
            username=req.username,
            password=_resolve_secret_ref(req.secret_ref or req.password),
        )
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.post("/ssh/disconnect-direct")
async def ssh_disconnect_direct():
    ssh = get_ssh_manager()
    await ssh.disconnect()
    return {"success": True}
@router.post("/ssh/execute-command-direct")
async def ssh_execute_command_direct(req: ExecuteCommandRequest):
    ssh = get_ssh_manager()
    result = await ssh.execute_dashboard_command_as_user(req.command, req.username)
    return result.model_dump(mode="json")
@router.post("/ssh/execute-dashboard-command")
async def ssh_execute_dashboard_command(req: ExecuteCommandRequest):
    ssh = get_ssh_manager()
    result = await ssh.execute_dashboard_command(req.command)
    return result.model_dump(mode="json")
@router.post("/ssh/execute-emergency-command")
async def ssh_execute_emergency_command(req: ExecuteCommandRequest):
    ssh = get_ssh_manager()
    if req.username:
        result = await ssh.execute_dashboard_command_as_user(req.command, req.username)
    else:
        result = await ssh.execute_dashboard_command(req.command)
    return result.model_dump(mode="json")
@router.post("/ssh/execute-detection-command")
async def execute_detection_command(req: ExecuteCommandRequest):
    ssh = get_ssh_manager()
    result = await ssh.execute_dashboard_command(req.command)
    return result.model_dump(mode="json")
@router.post("/execute-selected-remediations")
async def execute_selected_remediations(req: ExecuteSelectedRemediationsRequest):
    if req.rollback_mode not in {"none", "preview", "execute"}:
        raise HTTPException(status_code=400, detail="rollback_mode 必须是 none / preview / execute")
    if not req.selected_findings:
        raise HTTPException(status_code=400, detail="selected_findings 不能为空")

    ssh, ssh_error = _safe_get_remediation_ssh()
    ssh_connected = _is_ssh_connected_for_remediation(ssh)
    approval_tickets: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []

    for finding in req.selected_findings:
        ticket = _build_approval_ticket(req.task, finding)
        snapshot = _build_budget_snapshot(req.budget, finding, req.rollback_mode)
        rollback_preview = {
            "supported": bool(finding.rollback_commands),
            "commands": list(finding.rollback_commands),
        }
        result: Dict[str, Any] = {
            "finding_id": finding.finding_id,
            "title": finding.title,
            "approval_required": False,
            "approval_ticket": None,
            "expected_side_effects": list(finding.commands),
            "rollback_preview": rollback_preview,
            "rollback_results": [],
            "budget_snapshot": snapshot,
            "outputs": [],
            "error": None,
        }

        violation = _budget_violation(snapshot)
        if violation:
            result["execution_status"] = "blocked"
            result["error"] = violation
            results.append(result)
            continue

        if req.rollback_mode == "preview":
            result["execution_status"] = "rollback_preview"
            results.append(result)
            continue

        if req.dry_run:
            result["execution_status"] = "dry_run"
            result["approval_required"] = True
            result["approval_ticket"] = ticket
            approval_tickets.append(ticket)
            results.append(result)
            continue

        if not ssh_connected and req.rollback_mode == "none":
            result["execution_status"] = "failed"
            result["error"] = f"SSH 连接不可用: {ssh_error or '没有活动的 SSH 连接'}"
            results.append(result)
            continue

        if finding.commands and not _is_remediation_approved(req, finding):
            result["execution_status"] = "pending_approval"
            result["approval_required"] = True
            result["approval_ticket"] = ticket
            approval_tickets.append(ticket)
            results.append(result)
            continue

        if req.rollback_mode == "execute":
            if not ssh_connected:
                result["execution_status"] = "failed"
                result["error"] = f"SSH 连接不可用: {ssh_error or '没有活动的 SSH 连接'}"
                results.append(result)
                continue
            try:
                result["rollback_results"] = await _execute_ssh_commands(ssh, finding.rollback_commands)
                result["execution_status"] = "rollback_completed"
            except Exception as exc:
                result["execution_status"] = "failed"
                result["error"] = str(exc)
            results.append(result)
            continue

        if not ssh_connected:
            result["execution_status"] = "failed"
            result["error"] = f"SSH 连接不可用: {ssh_error or '没有活动的 SSH 连接'}"
            results.append(result)
            continue

        try:
            run_outputs = await _execute_ssh_commands(ssh, finding.commands)
            verify_outputs = await _execute_ssh_commands(ssh, finding.verify_commands)
            result["outputs"] = run_outputs + verify_outputs
            result["execution_status"] = "completed"
        except Exception as exc:
            result["execution_status"] = "failed"
            result["error"] = str(exc)
        results.append(result)

    statuses = [item["execution_status"] for item in results]
    if statuses and all(status == "dry_run" for status in statuses):
        overall_status = "dry_run"
    elif statuses and all(status == "rollback_preview" for status in statuses):
        overall_status = "rollback_preview"
    elif any(status == "blocked" for status in statuses):
        overall_status = "blocked"
    elif any(status == "pending_approval" for status in statuses):
        overall_status = "pending_approval"
    elif statuses and all(status == "rollback_completed" for status in statuses):
        overall_status = "rollback_completed"
    elif statuses and all(status == "completed" for status in statuses):
        overall_status = "all_completed"
    elif any(status == "failed" for status in statuses):
        overall_status = "failed"
    else:
        overall_status = "partially_completed"

    payload: Dict[str, Any] = {
        "task": req.task,
        "overall_status": overall_status,
        "results": results,
        "approval_tickets": approval_tickets,
        "budget": req.budget.model_dump(),
    }
    if ssh_error and overall_status == "failed":
        payload["error"] = f"SSH 连接不可用: {ssh_error}"
    elif any(item.get("error") for item in results) and overall_status == "failed":
        first_error = next(item["error"] for item in results if item.get("error"))
        payload["error"] = first_error
    return payload
@router.get("/ssh/connection-status")
async def ssh_get_connection_status():
    ssh = get_ssh_manager()
    status = await ssh.get_connection_status()
    return status.model_dump(mode="json") if status else None

@router.get("/ssh/connection-health")
async def ssh_get_connection_health():
    ssh = get_ssh_manager()
    return ssh.get_connection_health()
@router.post("/ssh/test-performance")
async def test_ssh_performance():
    ssh = get_ssh_manager()
    test_commands = [
        ("echo test", "基础响应测试"),
        ("pwd", "目录查询测试"),
        ("date", "系统时间测试"),
        ("whoami", "用户查询测试"),
    ]
    results = ["=== 直接命令执行性能测试 ==="]
    for cmd, desc in test_commands:
        start = time.time()
        try:
            await ssh.execute_command(cmd)
            duration = time.time() - start
            results.append(f"{desc}: {duration:.3f}s")
        except Exception as e:
            results.append(f"{desc}: 失败 - {e}")
    results.append("\n=== 性能分析建议 ===")
    results.append("如果直接命令执行很快，但交互式终端很慢，问题可能在于:")
    results.append("1. Shell初始化配置(.bashrc, .profile)")
    results.append("2. 复杂的命令提示符(PS1)")
    results.append("3. PTY配置问题")
    results.append("4. 环境变量处理")
    return {"result": "\n".join(results)}
@router.post("/ssh/diagnose-shell-performance")
async def diagnose_shell_performance():
    ssh = get_ssh_manager()
    results = ["=== Shell性能诊断 ==="]
    tests = [
        ("echo $SHELL", "Shell类型"),
        ("wc -l ~/.bashrc 2>/dev/null || echo 'no .bashrc'", ".bashrc行数"),
        ('echo "PS1长度: ${#PS1}"', "命令提示符"),
        ("true", "简单命令(true)"),
    ]
    for cmd, desc in tests:
        start = time.time()
        try:
            output = await ssh.execute_command(cmd)
            duration = time.time() - start
            results.append(f"{desc}: {output.output.strip()} (耗时: {duration:.3f}s)")
        except Exception as e:
            results.append(f"{desc}失败: {e}")
    return {"result": "\n".join(results)}
@router.get("/ssh/detect-system-type")
async def detect_system_type():
    ssh = get_ssh_manager()
    if not ssh.is_connected():
        raise HTTPException(status_code=400, detail="没有活动的 SSH 连接")
    os_release_cmd = "cat /etc/os-release 2>/dev/null || cat /etc/lsb-release 2>/dev/null || echo 'ID=generic'"
    os_release_output = await ssh.execute_dashboard_command(os_release_cmd)
    os_release_content = os_release_output.output
    pkg_mgr_cmd = "which apt 2>/dev/null && echo 'apt' || which yum 2>/dev/null && echo 'yum' || which dnf 2>/dev/null && echo 'dnf' || which pacman 2>/dev/null && echo 'pacman' || which zypper 2>/dev/null && echo 'zypper' || which apk 2>/dev/null && echo 'apk' || echo 'unknown'"
    pkg_mgr_output = await ssh.execute_dashboard_command(pkg_mgr_cmd)
    package_manager = pkg_mgr_output.output.strip().split("\n")[-1].strip()
    init_output = await ssh.execute_dashboard_command("ps -p 1 -o comm= 2>/dev/null")
    init_str = init_output.output.strip().lower()
    if "systemd" in init_str:
        init_system = "systemd"
    elif "init" in init_str:
        init_system = "sysvinit"
    elif "upstart" in init_str:
        init_system = "upstart"
    elif "openrc" in init_str:
        init_system = "openrc"
    else:
        init_system = "unknown"
    id_val = "generic"
    id_like = ""
    name = "Linux"
    version = ""
    pretty_name = "Generic Linux"
    for line in os_release_content.split("\n"):
        line = line.strip()
        if line.startswith("ID=") and not line.startswith("ID_LIKE="):
            id_val = line[3:].strip('"').strip("'").lower()
        elif line.startswith("ID_LIKE="):
            id_like = line[8:].strip('"').strip("'").lower()
        elif line.startswith("NAME="):
            name = line[5:].strip('"').strip("'")
        elif line.startswith("VERSION_ID="):
            version = line[11:].strip('"').strip("'")
        elif line.startswith("PRETTY_NAME="):
            pretty_name = line[12:].strip('"').strip("'")
    # 直接使用 /etc/os-release 中的 ID，适配所有 Linux 发行版
    system_type = id_val
    if id_val in ("opensuse", "opensuse-leap", "opensuse-tumbleweed"):
        system_type = "opensuse"
    elif id_like:
        if "ubuntu" in id_like:
            system_type = "ubuntu"
        elif "debian" in id_like:
            system_type = "debian"
        elif "rhel" in id_like or "fedora" in id_like:
            combined = f"{id_val} {id_like} {name} {pretty_name}".lower()
            if "centos" in combined:
                system_type = "centos"
            elif "fedora" in combined:
                system_type = "fedora"
            else:
                system_type = "rhel"
        elif "arch" in id_like:
            system_type = "arch"
        elif "suse" in id_like:
            system_type = "opensuse"
    return {
        "type": system_type,
        "name": name,
        "version": version,
        "prettyName": pretty_name,
        "packageManager": package_manager,
        "initSystem": init_system,
    }
@router.post("/sftp/list-files")
async def sftp_list_files(path: str):
    async def _go():
        ssh = get_ssh_manager()
        return await ssh.list_sftp_files(path)
    files = await _wrap_ssh_transport(_go)
    return [f.model_dump(mode="json") for f in files]
@router.post("/sftp/read-file")
async def sftp_read_file(path: str, max_bytes: Optional[int] = None):
    async def _go():
        ssh = get_ssh_manager()
        return await ssh.read_sftp_file(path)
    content = await _wrap_ssh_transport(_go)
    text = content.decode("utf-8", errors="replace")
    if max_bytes and len(text) > max_bytes:
        text = text[:max_bytes]
    return {"content": text}
@router.post("/sftp/write-file")
async def sftp_write_file(req: SftpWriteRequest):
    async def _go():
        ssh = get_ssh_manager()
        await ssh.write_sftp_file(req.path, req.content.encode("utf-8"))
    await _wrap_ssh_transport(_go)
    return {"success": True}
@router.post("/sftp/upload")
async def sftp_upload(req: SftpUploadRequest):
    async def _go():
        ssh = get_ssh_manager()
        await ssh.upload_file(req.local_path, req.remote_path)
    await _wrap_ssh_transport(_go)
    return {"success": True}
@router.post("/sftp/upload-direct")
async def sftp_upload_direct(
    file: UploadFile = File(...),
    remote_path: str = Form(...),
    upload_id: str = Form(...),
    file_size: int = Form(...),
):
    tmp_path = None
    try:
        filename = file.filename or "upload"
        suffix = os.path.splitext(filename)[1]
        total_bytes = max(int(file_size or 0), 0)
        _set_sftp_upload_progress(
            upload_id,
            stage="receiving",
            transferred_bytes=0,
            total_bytes=total_bytes,
        )
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            received_bytes = 0
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                tmp.write(chunk)
                received_bytes += len(chunk)
                _set_sftp_upload_progress(
                    upload_id,
                    stage="receiving",
                    transferred_bytes=received_bytes,
                    total_bytes=total_bytes,
                )
            tmp_path = tmp.name
        logger.info(f"上传文件: 本地={tmp_path}, 远程={remote_path}, 原始文件名={filename}")
        _set_sftp_upload_progress(
            upload_id,
            stage="transferring",
            transferred_bytes=0,
            total_bytes=total_bytes,
        )
        async def _go():
            ssh = get_ssh_manager()
            await ssh.upload_file(
                tmp_path,
                remote_path,
                progress_callback=lambda transferred, total: _set_sftp_upload_progress(
                    upload_id,
                    stage="transferring",
                    transferred_bytes=transferred,
                    total_bytes=total_bytes or total,
                ),
            )
        try:
            await _wrap_ssh_transport(_go)
        except HTTPException as e:
            detail = e.detail if isinstance(e.detail, str) else str(e.detail)
            _set_sftp_upload_progress(
                upload_id,
                stage="error",
                transferred_bytes=0,
                total_bytes=total_bytes,
                done=True,
                error=detail,
            )
            if "Permission denied" in detail:
                raise HTTPException(status_code=403, detail=f"远程服务器拒绝写入: {remote_path}，请检查目录权限") from e
            raise
        _set_sftp_upload_progress(
            upload_id,
            stage="completed",
            transferred_bytes=total_bytes,
            total_bytes=total_bytes,
            done=True,
            success=True,
        )
        return {"success": True, "upload_id": upload_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传文件失败: {e}", exc_info=True)
        _set_sftp_upload_progress(
            upload_id,
            stage="error",
            transferred_bytes=0,
            total_bytes=max(int(file_size or 0), 0),
            done=True,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"上传文件失败: {str(e)}") from e
    finally:
        try:
            file.file.close()
        except Exception:
            pass
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.get("/sftp/upload-progress")
async def sftp_upload_progress(upload_id: str):
    progress = _sftp_upload_progress.get(upload_id)
    if not progress:
        raise HTTPException(status_code=404, detail="未找到上传进度")
    return progress
@router.post("/sftp/download")
async def sftp_download(req: SftpDownloadRequest):
    async def _go():
        ssh = get_ssh_manager()
        await ssh.download_file(req.remote_path, req.local_path)
    await _wrap_ssh_transport(_go)
    return {"success": True}
@router.post("/sftp/create-directory")
async def sftp_create_directory(remote_path: str):
    async def _go():
        ssh = get_ssh_manager()
        await ssh.create_directory(remote_path)
    await _wrap_ssh_transport(_go)
    return {"success": True}
@router.post("/sftp/compress")
async def sftp_compress(req: SftpCompressRequest):
    async def _go():
        ssh = get_ssh_manager()
        await ssh.compress_file(req.source_path, req.target_path, req.format)
    await _wrap_ssh_transport(_go)
    return {"success": True}
@router.post("/sftp/extract")
async def sftp_extract(req: SftpExtractRequest):
    async def _go():
        ssh = get_ssh_manager()
        await ssh.extract_file(req.archive_path, req.target_dir)
    await _wrap_ssh_transport(_go)
    return {"success": True}
@router.post("/sftp/chmod")
async def sftp_chmod(req: SftpChmodRequest):
    async def _go():
        ssh = get_ssh_manager()
        await ssh.chmod_sftp(req.path, req.mode)
    await _wrap_ssh_transport(_go)
    return {"success": True}
@router.post("/sftp/get-file-details")
async def sftp_get_file_details(path: str):
    async def _go():
        ssh = get_ssh_manager()
        return await ssh.get_file_details(path)
    details = await _wrap_ssh_transport(_go)
    return details.model_dump(mode="json")
@router.post("/sftp/save-temp-file")
async def save_temp_file(req: SaveTempFileRequest):
    import base64
    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, req.file_name)
    data = base64.b64decode(req.data)
    with open(temp_path, "wb") as f:
        f.write(data)
    return {"path": temp_path}
@router.post("/file-analysis")
async def sftp_file_analysis_endpoint(req: FileAnalysisRequest):
    async def _go():
        ssh = get_ssh_manager()
        return await file_analysis.sftp_file_analysis(ssh, req.path, req.action)
    result = await _wrap_ssh_transport(_go)
    return result
@router.post("/file-analysis/independent")
async def sftp_file_analysis_independent_endpoint(req: FileAnalysisRequest):
    async def _go():
        ssh = get_ssh_manager()
        return await file_analysis.sftp_file_analysis_independent(ssh, req.path, req.action)
    result = await _wrap_ssh_transport(_go)
    return result
@router.get("/bash/environment-info")
async def get_bash_environment_info():
    ssh = get_ssh_manager()
    result = await ssh.get_bash_environment_info()
    return result.model_dump()
@router.post("/command/completion")
async def get_command_completion(input: str):
    ssh = get_ssh_manager()
    result = await ssh.get_command_completion(input)
    return result.model_dump()
@router.post("/detect/port-scan")
async def detect_port_scan():
    result = (await detection_manager.detect_port_scan(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/user-audit")
async def detect_user_audit():
    result = (await detection_manager.detect_user_audit(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/backdoor")
async def detect_backdoor():
    result = (await detection_manager.detect_backdoor(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/process-analysis")
async def detect_process_analysis():
    result = (
        await detection_manager.detect_process_analysis(get_ssh_manager())
    ).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/file-permission")
async def detect_file_permission():
    result = (
        await detection_manager.detect_file_permission(get_ssh_manager())
    ).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/ssh-audit")
async def detect_ssh_audit():
    result = (await detection_manager.detect_ssh_audit(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/log-analysis")
async def detect_log_analysis():
    result = (await detection_manager.detect_log_analysis(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/firewall-check")
async def detect_firewall_check():
    result = (
        await detection_manager.detect_firewall_check(get_ssh_manager())
    ).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "detection",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/cpu-test")
async def detect_cpu_test():
    result = (await detection_manager.detect_cpu_test(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "performance",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/memory-test")
async def detect_memory_test():
    result = (await detection_manager.detect_memory_test(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "performance",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/disk-test")
async def detect_disk_test():
    result = (await detection_manager.detect_disk_test(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "performance",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/network-test")
async def detect_network_test():
    result = (await detection_manager.detect_network_test(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "performance",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/password-policy")
async def detect_password_policy():
    result = (
        await detection_manager.detect_password_policy(get_ssh_manager())
    ).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "baseline",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/sudo-config")
async def detect_sudo_config():
    result = (await detection_manager.detect_sudo_config(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "baseline",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/pam-config")
async def detect_pam_config():
    result = (await detection_manager.detect_pam_config(get_ssh_manager())).model_dump()
    result["endpoint_metadata"] = {
        "type": "low-level",
        "category": "baseline",
        "recommended_usage": "仅供 Agent 内部调用或调试使用",
    }
    return result
@router.post("/detect/account-lockout")
async def detect_account_lockout():
    return (
        await detection_manager.detect_account_lockout(get_ssh_manager())
    ).model_dump()
@router.post("/detect/selinux-status")
async def detect_selinux_status():
    return (
        await detection_manager.detect_selinux_status(get_ssh_manager())
    ).model_dump()
@router.post("/detect/kernel-params")
async def detect_kernel_params():
    return (
        await detection_manager.detect_kernel_params(get_ssh_manager())
    ).model_dump()
@router.post("/detect/system-updates")
async def detect_system_updates():
    return (
        await detection_manager.detect_system_updates(get_ssh_manager())
    ).model_dump()
@router.post("/detect/unnecessary-services")
async def detect_unnecessary_services():
    return (
        await detection_manager.detect_unnecessary_services(get_ssh_manager())
    ).model_dump()
@router.post("/detect/auto-start-services")
async def detect_auto_start_services():
    return (
        await detection_manager.detect_auto_start_services(get_ssh_manager())
    ).model_dump()
@router.post("/detect/audit-config")
async def detect_audit_config():
    return (await detection_manager.detect_audit_config(get_ssh_manager())).model_dump()
@router.post("/detect/history-audit")
async def detect_history_audit():
    return (
        await detection_manager.detect_history_audit(get_ssh_manager())
    ).model_dump()
@router.post("/detect/ntp-config")
async def detect_ntp_config():
    return (await detection_manager.detect_ntp_config(get_ssh_manager())).model_dump()
@router.post("/detect/dns-config")
async def detect_dns_config():
    return (await detection_manager.detect_dns_config(get_ssh_manager())).model_dump()
@router.post("/ssh/terminal/create")
async def ssh_create_terminal_session(req: CreateTerminalSessionRequest):
    ssh = get_ssh_manager()
    try:
        result = await ssh.create_terminal_session(req.terminal_id, req.cols, req.rows)
        return {"terminal_id": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.post("/ssh/terminal/close")
async def ssh_close_terminal_session(terminal_id: str):
    ssh = get_ssh_manager()
    await ssh.close_terminal_session(terminal_id)
    return {"success": True}
@router.post("/ssh/terminal/close-all")
async def ssh_close_all_terminal_sessions():
    ssh = get_ssh_manager()
    await ssh.close_all_terminal_sessions()
    return {"success": True}
@router.post("/ssh/terminal/send-input")
async def ssh_send_input(req: SendTerminalInputRequest):
    ssh = get_ssh_manager()
    await ssh.send_terminal_input(req.terminal_id, req.data.encode("utf-8"))
    return {"success": True}
@router.post("/ssh/terminal/read-output")
async def ssh_read_terminal_output(terminal_id: str):
    ssh = get_ssh_manager()
    data = await ssh.read_terminal_output(terminal_id)
    return {"data": data.decode("utf-8", errors="replace")}
@router.post("/ssh/terminal/get-completion")
async def ssh_get_completion(input: str):
    ssh = get_ssh_manager()
    result = await ssh.get_command_completion(input)
    return result.model_dump()
@router.post("/log/read-system")
async def read_system_log(req: ReadSystemLogRequest):
    ssh = get_ssh_manager()
    result = await log_analysis.read_system_log(
        ssh, req.log_path, req.page, req.page_size, req.filter, req.date_filter, req.level_filter
    )
    return result.model_dump()
@router.post("/log/read-journalctl")
async def read_journalctl_log(req: ReadJournalctlLogRequest):
    ssh = get_ssh_manager()
    result = await log_analysis.read_journalctl_log(
        ssh, req.page, req.page_size, req.unit, req.filter, req.since, req.until, req.level_filter
    )
    return result.model_dump()
@router.get("/log/list-files")
async def list_log_files():
    ssh = get_ssh_manager()
    files = await log_analysis.list_log_files(ssh)
    return [f.model_dump() for f in files]
@router.post("/log/file-info")
async def get_log_file_info(log_path: str):
    ssh = get_ssh_manager()
    info = await log_analysis.get_log_file_info(ssh, log_path)
    return info.model_dump()
# ==================== 渗透测试 Agent (多任务) ====================
from app.services.pentest_agent.state import State
from app.services.pentest_agent.executor import Executor
from app.services.pentest_agent.llm_client import LLMClient, set_llm_client
from uuid import uuid4
from app.core.contracts import ActionLevel, AutonomyMode, PortRange, ScopeContract
from app.core.done_gate import DoneGate
from app.core.mission_control import MissionControl
from app.core.planner_contracts import ActionLimitController, AutonomyController
from app.core.scope_policy import ScopePolicy
from app.core.asset_graph import AssetGraph
from app.core.asset_normalizer import AssetInventoryImporter
from app.core.policy_templates import CoursePolicyError, CoursePolicyRegistry, CoursePolicyTemplate
from app.core.web_model import AuthSession, WebCrawlerPolicy, WebRuleEngine, WebSessionStore
from app.core.web_runtime import BrowserAutomationPlugin, BrowserTrace, ScopedWebCrawler, WebFetch
from app.core.report_export import ReportExporter, build_report_document
from app.core.report_contract import ReportCompletenessValidator, ReportSnapshot
from app.core.choice_reason import summarize_choice_reason

_pentest_tasks: dict[str, dict] = {}
"""所有渗透任务 {task_id: {target, state_file, start_time, task_obj, status}}"""

_SRC_PYTHON_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_PROJECT_ROOT_DIR = os.path.dirname(_SRC_PYTHON_DIR)
_PENTEST_STATE_DIR = os.path.join(_PROJECT_ROOT_DIR, "data", "pentest")
_course_policy_registry = CoursePolicyRegistry()
_pentest_scope_policy = ScopePolicy(course_policies=_course_policy_registry)
_web_sessions = WebSessionStore()

def _state_file(task_id: str) -> str:
    return os.path.join(_PENTEST_STATE_DIR, f"pentest_state_{task_id}.json")

def _extract_task_id_from_state_file(path: str) -> Optional[str]:
    name = os.path.basename(path)
    prefix = "pentest_state_"
    suffix = ".json"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    return name[len(prefix):-len(suffix)]

def _list_pentest_state_files() -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    search_dirs = [_PENTEST_STATE_DIR]

    for directory in search_dirs:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not name.startswith("pentest_state_") or not name.endswith(".json"):
                continue
            full_path = os.path.join(directory, name)
            if full_path in seen:
                continue
            seen.add(full_path)
            files.append(full_path)

    return sorted(files, reverse=True)

def _resolve_task_state_path(task_id: str) -> Optional[str]:
    tinfo = _pentest_tasks.get(task_id)
    if tinfo and tinfo.get("state_file"):
        state_path = tinfo["state_file"]
        if os.path.exists(state_path):
            return state_path

    state_path = _state_file(task_id)
    if os.path.exists(state_path):
        return state_path
    return None

def _load_task_state(task_id: str) -> Optional[State]:
    state_path = _resolve_task_state_path(task_id)
    if not state_path or not os.path.exists(state_path):
        return None
    return State(state_path, task_id=task_id)


def _public_action_view(action: dict[str, Any]) -> dict[str, Any]:
    """Expose observable action status while keeping internal model text private."""
    public = {
        key: value
        for key, value in action.items()
        if key not in {"full_stdout", "llm_decision"}
    }
    public["choice_reason"] = summarize_choice_reason(
        action.get("choice_reason") or action.get("purpose", ""),
        str(action.get("purpose", "")),
    )
    preview = str(action.get("result") or action.get("error") or "")
    preview = re.sub(
        r"(?i)(password|passwd|token|secret|api[_-]?key|authorization)(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        preview,
    )
    public["output_preview"] = preview[:2000]
    return public


def _build_report_check(state: State, task_id: str) -> tuple[dict[str, Any], Any]:
    report_data = dict(state.data)
    report_data["event_integrity"] = state.event_store.integrity_manifest()
    document = build_report_document(report_data, task_id=task_id)
    snapshot = ReportSnapshot.from_document(
        document,
        task_version=str(state.data.get("version", "state.v1")),
    )
    return document, ReportCompletenessValidator().validate(snapshot)

def _infer_task_status(task_id: str, state: Optional[State], tinfo: Optional[dict]) -> str:
    if tinfo:
        control = tinfo.get("control")
        if isinstance(control, MissionControl):
            control_status = control.status
            if control_status in {"paused", "cancelling", "cancelled", "completed", "failed"}:
                return control_status
        task = tinfo.get("task_obj")
        if tinfo.get("status") == "running" and task and not task.done():
            return "running"
        if tinfo.get("status"):
            return tinfo["status"]

    if state and state.data.get("phase") == "done":
        return "done"
    if state and state.data.get("actions_taken"):
        return "stopped"
    return "stopped"

def _build_history_item(task_id: str, tinfo: Optional[dict] = None) -> Optional[dict]:
    state = _load_task_state(task_id)
    state_path = _resolve_task_state_path(task_id)

    if not tinfo and not state_path:
        return None

    targets = state.data.get("targets", []) if state else []
    created_at = state.data.get("created_at") if state else None

    return {
        "task_id": task_id,
        "target": (tinfo or {}).get("target") or (targets[0] if targets else "未知目标"),
        "start_time": (tinfo or {}).get("start_time") or created_at or "",
        "status": _infer_task_status(task_id, state, tinfo),
        "phase": state.data.get("phase", "init") if state else "init",
        "findings_count": state.find_count if state else 0,
        "vuln_count": state.vuln_count if state else 0,
        "actions_count": len(state.data.get("actions_taken", [])) if state else 0,
    }

class PentestStartRequest(BaseModel):
    target: str = Field(..., description="目标 IP / 域名 / 网段")
    max_rounds: int = Field(30, ge=1, le=100, description="最大执行轮数")
    dry_run: bool = Field(False, description="不真正执行命令")
    execution_mode: Literal["parallel", "serial"] = Field("parallel", description="任务执行模式")
    skill_query: str = Field("", description="技能匹配关键词，可选；为空时由系统自动构造")
    skill_limit: int = Field(5, ge=1, le=10, description="每轮最多注入技能数量")
    api_key: str = Field("", description="LLM API Key")
    model: str = Field("gpt-4o-mini", description="LLM 模型")
    base_url: str = Field("https://api.openai.com/v1", description="LLM API 地址")
    provider: str = Field("openai", description="LLM 提供商: openai/deepseek/qwen/ollama")
    temperature: float = Field(0.3, ge=0, le=2, description="LLM 温度")
    llm_max_tokens: int = Field(1500, ge=128, le=8192, description="LLM 最大输出 token")
    llm_timeout_seconds: int = Field(120, ge=10, le=600, description="LLM 单次请求超时时间")
    llm_max_retries: int = Field(1, ge=0, le=10, description="LLM 请求最大重试次数")
    llm_retry_backoff_seconds: float = Field(1.2, ge=0.1, le=30.0, description="LLM 重试退避秒数")
    allowed_ports: list[int] = Field(default_factory=list, description="授权测试端口；为空时使用显式 1-65535 范围")
    allowed_protocols: list[str] = Field(default_factory=lambda: ["tcp"], min_length=1, max_length=16)
    max_duration_seconds: int | None = Field(None, ge=1, le=604800)
    max_commands: int = Field(1000, ge=1, le=100000)
    max_network_requests: int = Field(10000, ge=1, le=1000000)
    max_requests_per_second: float = Field(10.0, gt=0, le=10000)
    max_bruteforce_attempts: int = Field(100, ge=0, le=1000000)
    max_storage_bytes: int = Field(268435456, ge=0, le=1099511627776)
    max_concurrency: int | None = Field(None, ge=1, le=64)
    data_handling: Literal["ephemeral", "task_retained", "organization_retained"] = "ephemeral"
    policy_template_id: str = Field("", max_length=128)
    policy_template_version: str = Field("", max_length=64)
    authorization_basis: str = Field("local synthetic fixture", min_length=1, max_length=240, description="任务依据摘要")
    autonomy_mode: Literal["advisory", "supervised", "unattended"] = Field(
        "supervised", description="自治等级"
    )


class AutonomyModeRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    mode: Literal["advisory", "supervised", "unattended"]
    actor: str = Field("operator", min_length=1, max_length=160)
    reason: str = Field("operator requested autonomy change", min_length=1, max_length=500)


class ActionLimitRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    level: Literal["observe", "probe", "credential_test", "exploit", "session_verify", "post_verify"]
    actor: str = Field("operator", min_length=1, max_length=160)
    reason: str = Field("operator changed live action limit", min_length=1, max_length=500)


class KillSwitchRequest(BaseModel):
    enabled: bool = True
    actor: str = Field("operator", min_length=1, max_length=160)
    reason: str = Field("global mission stop requested", min_length=1, max_length=500)


class CoursePolicyPublishRequest(BaseModel):
    template: dict[str, Any] = Field(..., description="课程策略模板 JSON")
    actor: str = Field("course-admin", min_length=1, max_length=160)
    actor_role: str = Field("course_admin", min_length=1, max_length=80)


class CoursePolicyBindRequest(BaseModel):
    template_id: str = Field(..., min_length=3, max_length=128)
    version: str = Field(..., min_length=1, max_length=64)
    values: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field("student", min_length=1, max_length=160)
    actor_role: str = Field("student", min_length=1, max_length=80)


class PentestTokenUsageRequest(BaseModel):
    task_id: str = Field(..., description="渗透任务 ID")
    category: str = Field(..., description="token 分类，如 pentest_llm / report_ai")
    prompt_tokens: int = Field(0, ge=0, description="输入 token")
    completion_tokens: int = Field(0, ge=0, description="输出 token")
    total_tokens: int = Field(0, ge=0, description="总 token")
    model: str = Field("", description="模型名")
    provider: str = Field("", description="提供商")


class WebFixtureResponse(BaseModel):
    status_code: int = Field(200, ge=100, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    request_id: str = ""
    facts: dict[str, Any] = Field(default_factory=dict)


class WebCrawlRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    seeds: list[str] = Field(..., min_length=1, max_length=50)
    role: str = Field("anonymous", min_length=1, max_length=80)
    session_id: str = Field("", max_length=128)
    max_depth: int = Field(2, ge=0, le=8)
    max_content_bytes: int = Field(2_000_000, ge=1, le=20_000_000)
    max_requests_per_second: float = Field(2.0, gt=0, le=100)
    fixtures: dict[str, WebFixtureResponse] = Field(default_factory=dict)
    transport: Literal["fixture", "http"] = "fixture"


class BrowserTraceRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    browser_version: str = Field(..., min_length=1, max_length=128)
    trace_id: str = Field("", max_length=128)
    dom_snapshots: list[dict[str, str]] = Field(default_factory=list, max_length=200)
    network: list[dict[str, Any]] = Field(default_factory=list, max_length=2000)
    actions: list[dict[str, str]] = Field(default_factory=list, max_length=2000)
    replay: bool = False
    replay_browser_version: str = Field("", max_length=128)


class ReportExportRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    formats: list[Literal["md", "html", "json", "pdf", "docx"]] = Field(
        default_factory=lambda: ["md", "html", "json", "pdf", "docx"],
        min_length=1,
    )


class AssetInventoryImportRequest(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128)
    inventory: Any
    source: str = Field("inventory-api", min_length=1, max_length=160)
    ttl_seconds: int | None = Field(86400, ge=1, le=315360000)


class ModelSecretRequest(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=16384)
    ttl_seconds: int = Field(300, ge=30, le=3600)
    provider: str = Field("model", min_length=1, max_length=80)


@router.post("/agent/policy/templates/publish")
async def publish_course_policy(req: CoursePolicyPublishRequest):
    """Publish an immutable administrator-owned course policy version."""
    try:
        template = CoursePolicyTemplate.model_validate(req.template)
        published = _course_policy_registry.publish(
            template,
            actor=req.actor,
            actor_role=req.actor_role,
        )
    except (CoursePolicyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "template": published.model_dump(mode="json"),
        "template_hash": published.canonical_hash(),
    }


@router.get("/agent/policy/templates/{template_id}/{version}")
async def get_course_policy(template_id: str, version: str):
    try:
        template = _course_policy_registry.get(template_id, version)
    except CoursePolicyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "template": template.model_dump(mode="json"),
        "template_hash": template.canonical_hash(),
    }


@router.post("/agent/policy/templates/bind")
async def bind_course_policy(req: CoursePolicyBindRequest):
    """Create a student scope by narrowing a published course ceiling."""
    try:
        scope = _course_policy_registry.bind(
            req.template_id,
            req.version,
            req.values,
            actor=req.actor,
            actor_role=req.actor_role,
        )
        token = _pentest_scope_policy.issue_token(scope)
    except (CoursePolicyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "scope_contract": scope.model_dump(mode="json"),
        "scope_token": token,
        "template_hash": scope.policy_template_hash,
    }


@router.get("/agent/policy/templates/audit")
async def course_policy_audit():
    return {"events": _course_policy_registry.audit_events()}


@router.post("/agent/model-secret")
async def store_model_secret(req: ModelSecretRequest):
    """Turn a transient model credential into an opaque runtime reference."""
    ref = _model_secret_store.put(
        req.api_key,
        kind=f"{req.provider}-api-key",
        ttl_seconds=req.ttl_seconds,
    )
    return {
        "secret_ref": ref.ref,
        "kind": ref.kind,
        "fingerprint": ref.fingerprint,
        "expires_at": ref.expires_at,
    }


def _build_pentest_scope(req: PentestStartRequest) -> ScopeContract:
    target = req.target.strip()
    allowed_targets: list[str] = []
    allowed_cidrs: list[str] = []
    allowed_domains: list[str] = []
    if "/" in target:
        try:
            ipaddress.ip_network(target, strict=False)
            allowed_cidrs.append(target)
        except ValueError:
            allowed_domains.append(target)
    else:
        try:
            ipaddress.ip_address(target)
            allowed_targets.append(target)
        except ValueError:
            allowed_domains.append(target)
    ports = sorted(set(req.allowed_ports))
    port_ranges = [PortRange(start=1, end=65535)] if not ports else []
    duration_seconds = req.max_duration_seconds or max(60, req.llm_timeout_seconds * req.max_rounds)
    concurrency = req.max_concurrency or (1 if req.execution_mode == "serial" else 3)
    scope = ScopeContract(
        owner="local-user",
        allowed_targets=allowed_targets or ([target] if not allowed_cidrs and not allowed_domains else [target]),
        allowed_cidrs=allowed_cidrs,
        allowed_domains=allowed_domains,
        allowed_ports=ports,
        allowed_port_ranges=port_ranges,
        allowed_protocols=req.allowed_protocols,
        allowed_actions={
            ActionLevel.OBSERVE,
            ActionLevel.PROBE,
            ActionLevel.CREDENTIAL_TEST,
            ActionLevel.EXPLOIT,
            ActionLevel.SESSION_VERIFY,
            ActionLevel.POST_VERIFY,
        },
        forbidden_actions={ActionLevel.PROHIBITED},
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=duration_seconds),
        max_concurrency=concurrency,
        max_duration_seconds=duration_seconds,
        max_commands=req.max_commands,
        max_network_requests=req.max_network_requests,
        max_requests_per_second=req.max_requests_per_second,
        max_bruteforce_attempts=req.max_bruteforce_attempts,
        max_storage_bytes=req.max_storage_bytes,
        data_handling=req.data_handling,
        purpose=req.authorization_basis,
        autonomy_mode=AutonomyMode(req.autonomy_mode),
    )
    if req.policy_template_id:
        if not req.policy_template_version:
            raise CoursePolicyError("course policy template version is required")
        scope = _course_policy_registry.bind(
            req.policy_template_id,
            req.policy_template_version,
            scope.model_dump(),
            actor="local-user",
            actor_role="student",
        )
    return scope

@router.post("/agent/pentest/start")
async def pentest_start(req: PentestStartRequest):
    resolved_api_key = _resolve_model_api_key(req.api_key)
    task_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    state_path = _state_file(task_id)
    control = MissionControl(task_id)
    try:
        scope_contract = _build_pentest_scope(req)
    except CoursePolicyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    scope_token = _pentest_scope_policy.issue_token(scope_contract)

    initial_state = State(state_path, task_id=task_id)
    initial_state.data["task_id"] = task_id
    initial_state.data["targets"] = [req.target.strip()]
    initial_state.data["scope_contract"] = scope_contract.model_dump(mode="json")
    initial_state.data["autonomy_mode"] = scope_contract.autonomy_mode
    initial_state.data["autonomy_history"] = []
    initial_state.data["action_limit"] = "post_verify"
    initial_state.data["action_limit_history"] = []
    initial_state.data["scope_token_id"] = scope_token.split(".", 1)[0][:32]
    model_url = urlparse(req.base_url)
    model_origin = (
        f"{model_url.scheme}://{model_url.hostname}"
        + (f":{model_url.port}" if model_url.port else "")
        if model_url.scheme and model_url.hostname
        else "local-runtime"
    )
    runtime_snapshot = initial_state.data.setdefault("runtime_snapshot", {})
    runtime_snapshot["model"] = {
        "provider": req.provider,
        "model": req.model,
        "base_url_origin": model_origin,
        "temperature": req.temperature,
        "max_tokens": req.llm_max_tokens,
    }
    initial_state.event_store.append(
        initial_state.event_task_id,
        "task.created",
        {
            "task_id": task_id,
            "config": {
                "target": req.target.strip(),
                "targets": [req.target.strip()],
                "scope_id": scope_contract.scope_id,
                "mission_id": scope_contract.mission_id,
                "autonomy_mode": scope_contract.autonomy_mode,
                "max_rounds": req.max_rounds,
                "dry_run": req.dry_run,
                "execution_mode": req.execution_mode,
                "versions": {
                    "state": str(initial_state.data.get("version", "1.0")),
                    "event": "event.v1",
                    "policy": scope_contract.policy_version,
                },
            },
        },
        actor="task-api",
        idempotency_key=f"task.create:{task_id}",
    )
    initial_state.event_store.append(
        initial_state.event_task_id,
        "scope.created",
        {
            "scope_id": scope_contract.scope_id,
            "targets": scope_contract.allowed_targets or scope_contract.allowed_cidrs or scope_contract.allowed_domains,
            "port_count": len(scope_contract.allowed_ports) or 65535,
            "policy_version": scope_contract.policy_version,
        },
        actor="task-api",
        idempotency_key=f"scope.create:{scope_contract.scope_id}",
    )
    initial_state.data["event_count"] = initial_state.event_store.verify()["event_count"]
    initial_state.record_mission_control(
        control.snapshot(),
        previous_status=str(initial_state.data.get("mission_status", "")),
        actor="task-api",
    )
    initial_state.save()

    client = LLMClient(
        api_key=resolved_api_key,
        model=req.model,
        base_url=req.base_url,
        provider=req.provider,
        temperature=req.temperature,
        max_tokens=req.llm_max_tokens,
        timeout=req.llm_timeout_seconds,
        max_retries=req.llm_max_retries,
        retry_backoff=req.llm_retry_backoff_seconds,
    )
    if str(req.api_key).startswith("secret_"):
        _model_secret_store.delete(str(req.api_key))
    set_llm_client(client)

    autonomy_controller = AutonomyController(scope_contract.autonomy_mode)
    action_limit_controller = ActionLimitController("post_verify")
    _pentest_tasks[task_id] = {
        "target": req.target,
        "state_file": state_path,
        "start_time": str(datetime.now()),
        "status": "running",
        "task_obj": None,
        "control": control,
        "scope_contract": scope_contract.model_dump(mode="json"),
        "scope_token": scope_token,
        "autonomy": autonomy_controller,
        "action_limit": action_limit_controller,
    }

    loop = asyncio.new_event_loop()

    def llm_fn(system: str, user: str, on_chunk=None) -> str:
        if on_chunk is not None:
            return loop.run_until_complete(client.chat_stream(system, user, on_chunk=on_chunk))
        return loop.run_until_complete(client.chat(system, user))

    async def _run_agent():
        try:
            from app.services.pentest_agent.agent import run as agent_run

            def _blocking():
                try:
                    agent_run(
                        req.target,
                        llm_fn,
                        state_path,
                        req.max_rounds,
                        req.dry_run,
                        parallel_execution=(req.execution_mode == "parallel"),
                        skill_query=req.skill_query or None,
                        skill_limit=req.skill_limit,
                        scope_contract=scope_contract,
                        scope_token=scope_token,
                        scope_policy=_pentest_scope_policy,
                        task_id=task_id,
                        mission_control=control,
                        autonomy_controller=autonomy_controller,
                        action_limit_controller=action_limit_controller,
                    )
                finally:
                    loop.close()

            await asyncio.to_thread(_blocking)
            if control.is_cancel_requested:
                control.mark_cancelled(control.reason or "mission cancellation requested")
                _pentest_tasks[task_id]["status"] = "cancelled"
            else:
                control.mark_completed("mission run completed")
                _pentest_tasks[task_id]["status"] = "done"
        except asyncio.CancelledError:
            control.cancel("async task wrapper cancelled")
            _pentest_tasks[task_id]["status"] = "cancelling"
            raise
        except Exception as e:
            logger.error(f"Pentest task {task_id} failed: {str(e)}", exc_info=True)
            if control.is_cancel_requested:
                control.mark_cancelled(str(e) or "mission cancellation requested")
                _pentest_tasks[task_id]["status"] = "cancelled"
            else:
                control.mark_failed(str(e))
                _pentest_tasks[task_id]["status"] = "failed"
            _pentest_tasks[task_id]["error"] = str(e)

    task = asyncio.create_task(_run_agent())
    _pentest_tasks[task_id]["task_obj"] = task
    return {
        "success": True,
        "message": "渗透任务已启动",
        "target": req.target,
        "task_id": task_id,
        "scope_id": scope_contract.scope_id,
        "scope_expires_at": scope_contract.expires_at.isoformat(),
    }


@router.get("/agent/pentest/doctor")
async def pentest_doctor(refresh: bool = False):
    executor = Executor()
    return executor.doctor(refresh=refresh)

@router.get("/agent/pentest/status")
async def pentest_status(task_id: str):
    tinfo = _pentest_tasks.get(task_id)
    if not tinfo:
        raise HTTPException(status_code=404, detail="任务不存在")

    state = State(tinfo["state_file"])
    control = tinfo.get("control")
    control_snapshot = control.snapshot() if isinstance(control, MissionControl) else dict(
        state.data.get("mission_control") or {}
    )
    lifecycle_status = (
        control_snapshot.get("status")
        or tinfo.get("status")
        or _infer_task_status(task_id, state, tinfo)
    )
    task_obj = tinfo.get("task_obj")
    is_running = bool(
        lifecycle_status in {"running", "paused", "cancelling"}
        and task_obj
        and not task_obj.done()
    )
    actions = state.data["actions_taken"]
    slim_actions = []
    for a in actions[-10:]:
        slim_actions.append(_public_action_view(a))
    report_document, report_check = _build_report_check(state, task_id)
    evidence_records = [
        item for item in state.data.get("canonical_evidence", [])
        if isinstance(item, dict)
        and str(item.get("status", "")).strip().lower() not in DoneGate.TERMINAL
    ]
    target_records = [
        item for item in state.data.get("targets", []) if isinstance(item, dict)
    ]
    budget_exhausted = bool(
        state.data.get("budget_exhausted")
        or state.data.get("resource_budget_exhausted")
    )
    gate = DoneGate().evaluate(
        [item for item in state.data.get("attack_surfaces", []) if isinstance(item, dict)],
        budget_exhausted=budget_exhausted,
        report_complete=(
            state.data.get("phase") in {"reflection", "done"}
            and report_check.complete
        ),
        task_cancelled=lifecycle_status == "cancelled",
        targets=target_records,
        unresolved_evidence=evidence_records,
        sessions=[item for item in state.data.get("sessions", []) if isinstance(item, dict)],
        objective_required=bool(state.data.get("objective")),
        objective_completed=bool(state.data.get("objective_completed")),
    )
    try:
        event_consistency = state.event_consistency()
    except Exception as exc:
        event_consistency = {
            "schema_version": "state-consistency.v1",
            "consistent": False,
            "error": str(exc)[:500],
        }
    return {
        "running": is_running,
        "status": lifecycle_status,
        "mission_control": control_snapshot,
        "phase": state.data["phase"],
        "targets": state.data["targets"],
        "findings_count": state.find_count,
        "vuln_count": state.vuln_count,
        "cred_count": len(state.data["credentials"]),
        "actions_count": len(actions),
        "actions": slim_actions,
        "token_usage": state.data.get("token_usage", {}),
        "task_id": task_id,
        "error": tinfo.get("error"),
        "event_count": int(state.data.get("event_count", 0) or 0),
        "scope_id": (state.data.get("scope_contract") or {}).get("scope_id", ""),
        "autonomy_mode": state.data.get("autonomy_mode") or (state.data.get("scope_contract") or {}).get("autonomy_mode", "supervised"),
        "autonomy_history": state.data.get("autonomy_history", [])[-20:],
        "action_limit": state.data.get("action_limit", "post_verify"),
        "action_limit_history": state.data.get("action_limit_history", [])[-20:],
        "done_gate": gate.as_dict(),
        "report_completeness": report_check.as_dict(),
        "report_integrity_hash": report_document.get("integrity_hash", ""),
        "event_consistency": event_consistency,
    }

@router.get("/agent/pentest/logs")
async def pentest_logs(task_id: str):
    state = _load_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "phase": state.data["phase"],
        "actions_count": len(state.data["actions_taken"]),
        "actions": [_public_action_view(item) for item in state.data["actions_taken"]],
        "task_id": task_id,
    }

@router.post("/agent/pentest/stop")
async def pentest_stop(task_id: str):
    tinfo = _pentest_tasks.get(task_id)
    if not tinfo:
        return {"success": False, "message": "任务不存在"}
    control = tinfo.get("control")
    if isinstance(control, MissionControl):
        requested = control.cancel("user requested mission stop")
        if requested:
            tinfo["status"] = "cancelling"
            return {
                "success": True,
                "message": "已发送终止信号",
                "status": control.status,
                "mission_control": control.snapshot(),
            }
        if control.status in {"cancelling", "cancelled"}:
            return {"success": True, "message": "终止流程已在处理中", "status": control.status}
        return {"success": False, "message": "没有运行中的任务", "status": control.status}
    task = tinfo.get("task_obj")
    if task and not task.done():
        tinfo["status"] = "cancelling"
        return {"success": True, "message": "已发送终止信号", "status": "cancelling"}
    return {"success": False, "message": "没有运行中的任务"}


@router.post("/agent/pentest/pause")
async def pentest_pause(task_id: str):
    tinfo = _pentest_tasks.get(task_id)
    if not tinfo:
        return {"success": False, "message": "任务不存在"}
    control = tinfo.get("control")
    if not isinstance(control, MissionControl):
        return {"success": False, "message": "任务未接入生命周期控制"}
    changed = control.pause("user requested mission pause")
    if changed:
        tinfo["status"] = "paused"
    return {"success": changed, "status": control.status, "mission_control": control.snapshot()}


@router.post("/agent/pentest/resume")
async def pentest_resume(task_id: str):
    tinfo = _pentest_tasks.get(task_id)
    if not tinfo:
        return {"success": False, "message": "任务不存在"}
    control = tinfo.get("control")
    if not isinstance(control, MissionControl):
        return {"success": False, "message": "任务未接入生命周期控制"}
    changed = control.resume("user requested mission resume")
    if changed:
        tinfo["status"] = "running"
    return {"success": changed, "status": control.status, "mission_control": control.snapshot()}


@router.get("/agent/pentest/kill-switch")
async def pentest_kill_switch_status():
    return {
        "enabled": _pentest_scope_policy.emergency_stop_enabled(),
        "active_tasks": sorted(
            task_id
            for task_id, info in _pentest_tasks.items()
            if str(info.get("status", "")) in {"running", "paused", "cancelling"}
        ),
    }


@router.post("/agent/pentest/kill-switch")
async def pentest_set_kill_switch(req: KillSwitchRequest):
    """Apply the global execution ceiling and propagate cancellation to live missions."""
    _pentest_scope_policy.set_emergency_stop(req.enabled)
    affected: list[str] = []
    for task_id, info in list(_pentest_tasks.items()):
        control = info.get("control")
        if req.enabled and isinstance(control, MissionControl) and control.cancel(req.reason):
            info["status"] = "cancelling"
            affected.append(task_id)
        state = _load_task_state(task_id)
        if state is None:
            continue
        state.event_store.append(
            state.event_task_id,
            "system.kill_switch.changed",
            {
                "enabled": req.enabled,
                "actor": req.actor,
                "reason": req.reason,
                "mission_status": control.status if isinstance(control, MissionControl) else info.get("status", ""),
            },
            actor=req.actor,
            reason=req.reason,
            idempotency_key=f"kill-switch:{req.enabled}:{req.reason}:{task_id}",
        )
        state.data["global_kill_switch"] = {
            "enabled": req.enabled,
            "actor": req.actor,
            "reason": req.reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        state.data["event_count"] = state.event_store.verify()["event_count"]
        state.save()
    return {
        "success": True,
        "enabled": req.enabled,
        "affected_tasks": sorted(affected),
        "reason": req.reason,
    }


@router.post("/agent/pentest/autonomy")
async def pentest_set_autonomy(req: AutonomyModeRequest):
    """Change a task's autonomy level and persist the transition as an event."""
    tinfo = _pentest_tasks.get(req.task_id)
    state = _load_task_state(req.task_id)
    if not tinfo or not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    controller = tinfo.get("autonomy")
    if not isinstance(controller, AutonomyController):
        controller = AutonomyController(state.data.get("autonomy_mode", "supervised"))
        tinfo["autonomy"] = controller
    try:
        transition = controller.set_mode(req.mode, actor=req.actor, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="自治等级无效") from exc
    state.data["autonomy_mode"] = transition.current.value
    history = state.data.setdefault("autonomy_history", [])
    history.append({
        "previous": transition.previous.value,
        "current": transition.current.value,
        "actor": transition.actor,
        "reason": transition.reason,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    state.event_store.append(
        state.event_task_id,
        "autonomy.changed",
        {"previous": transition.previous.value, "current": transition.current.value, "actor": transition.actor},
        actor=transition.actor,
        previous_state=transition.previous.value,
        new_state=transition.current.value,
        reason=transition.reason,
        rule_version="autonomy.v1",
        idempotency_key=f"autonomy:{req.task_id}:{len(history)}:{transition.current.value}",
    )
    state.data["event_count"] = state.event_store.verify()["event_count"]
    state.save()
    return {
        "success": True,
        "task_id": req.task_id,
        "autonomy_mode": transition.current.value,
        "transition": history[-1],
    }


@router.post("/agent/pentest/action-limit")
async def pentest_set_action_limit(req: ActionLimitRequest):
    """Lower or raise the live action ceiling with an auditable transition."""
    tinfo = _pentest_tasks.get(req.task_id)
    state = _load_task_state(req.task_id)
    if not tinfo or not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    controller = tinfo.get("action_limit")
    if not isinstance(controller, ActionLimitController):
        controller = ActionLimitController(state.data.get("action_limit", "post_verify"))
        tinfo["action_limit"] = controller
    try:
        transition = controller.set_limit(req.level, actor=req.actor, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="动作上限无效") from exc
    state.data["action_limit"] = transition.current
    history = state.data.setdefault("action_limit_history", [])
    history.append({
        "previous": transition.previous,
        "current": transition.current,
        "actor": transition.actor,
        "reason": transition.reason,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    state.event_store.append(
        state.event_task_id,
        "action_limit.changed",
        {"previous": transition.previous, "current": transition.current, "actor": transition.actor},
        actor=transition.actor,
        previous_state=transition.previous,
        new_state=transition.current,
        reason=transition.reason,
        rule_version="action-limit.v1",
        idempotency_key=f"action-limit:{req.task_id}:{len(history)}:{transition.current}",
    )
    state.data["event_count"] = state.event_store.verify()["event_count"]
    state.save()
    return {"success": True, "task_id": req.task_id, "action_limit": transition.current, "transition": history[-1]}

@router.get("/agent/state")
async def pentest_get_state(task_id: str):
    state = _load_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    return state.data


@router.get("/agent/events")
async def pentest_get_events(task_id: str, after_sequence: int = 0, limit: int = 200):
    """Return a verified, contiguous event slice for the typed task store."""
    state = _load_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    if after_sequence < 0:
        raise HTTPException(status_code=400, detail="after_sequence 无效")
    limit = max(1, min(int(limit), 1000))
    try:
        all_events = state.event_store.stream(after_sequence=after_sequence, verify=True)
        selected = all_events[:limit]
        verification = state.event_store.verify()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"事件链校验失败: {exc}") from exc
    return {
        "task_id": task_id,
        "events": [event.model_dump(mode="json") for event in selected],
        "after_sequence": after_sequence,
        "next_sequence": selected[-1].sequence if selected else after_sequence,
        "has_more": len(all_events) > len(selected),
        "event_count": verification["event_count"],
        "last_hash": verification["last_hash"],
    }


@router.get("/agent/read-model")
async def pentest_get_read_model(task_id: str):
    """Rebuild and return the typed task view from the immutable event chain."""
    state = _load_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        read_model = state.replay_read_model()
        consistency = state.event_consistency()
        manifest = state.event_store.integrity_manifest()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"事件重放校验失败: {exc}") from exc
    return {
        "task_id": task_id,
        "read_model": read_model,
        "consistency": consistency,
        "event_manifest": manifest,
    }


@router.get("/agent/metrics")
async def pentest_get_metrics(task_id: str, group_by: str = ""):
    state = _load_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    dimensions = [item.strip() for item in group_by.split(",") if item.strip()] or None
    return {
        "task_id": task_id,
        "metrics": state.metrics_snapshot(group_by=dimensions),
    }


def _asset_node_is_in_scope(node: Any, scope: ScopeContract) -> bool:
    """Classify imported inventory without expanding the immutable task scope."""
    target = str(getattr(node, "target", "") or "").strip()
    if not target:
        return False
    if str(getattr(node, "kind", "")).lower() == "cidr":
        try:
            candidate = ipaddress.ip_network(target, strict=False)
        except ValueError:
            return False
        target_allowed = target.lower() in {
            str(value).strip().lower() for value in scope.allowed_targets
        }
        cidr_allowed = False
        for value in scope.allowed_cidrs:
            try:
                allowed = ipaddress.ip_network(value, strict=False)
                if candidate.version == allowed.version and candidate.subnet_of(allowed):
                    cidr_allowed = True
                    break
            except ValueError:
                continue
        if not (target_allowed or cidr_allowed):
            return False
    elif not ScopePolicy.target_in_scope(target, scope):
        return False
    return ScopePolicy.port_in_scope(getattr(node, "port", None), scope)


@router.post("/agent/assets/import")
async def agent_import_assets(req: AssetInventoryImportRequest):
    """Merge heterogeneous inventory into the task graph with provenance and scope labels."""
    state = _load_task_state(req.task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        existing = state.data.get("asset_graph")
        graph = (
            AssetGraph.model_validate(existing)
            if isinstance(existing, dict) and existing
            else AssetGraph.from_state(state.data)
        )
        result = AssetInventoryImporter(ttl_seconds=req.ttl_seconds).import_inventory(
            req.inventory,
            graph=graph,
            source=req.source,
        )
    except (TypeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scope: ScopeContract | None = None
    scope_payload = state.data.get("scope_contract")
    if isinstance(scope_payload, dict) and scope_payload:
        try:
            scope = ScopeContract.model_validate(scope_payload)
        except ValueError:
            scope = None

    imported_ids = set(result.imported_nodes)
    scope_counts = {"in_scope": 0, "out_of_scope": 0, "scope_unknown": 0}
    for index, node in enumerate(result.graph.nodes):
        if node.node_id not in imported_ids:
            continue
        if scope is None:
            scope_status = "SCOPE_UNKNOWN"
            scope_counts["scope_unknown"] += 1
        elif _asset_node_is_in_scope(node, scope):
            scope_status = "IN_SCOPE"
            scope_counts["in_scope"] += 1
        else:
            scope_status = "OUT_OF_SCOPE"
            scope_counts["out_of_scope"] += 1
        attributes = dict(node.attributes)
        attributes["scope_status"] = scope_status
        result.graph.nodes[index] = node.model_copy(update={"attributes": attributes})

    canonical_inventory = json.dumps(
        req.inventory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    request_hash = hashlib.sha256(
        f"{req.source}\n{req.ttl_seconds}\n{canonical_inventory}".encode("utf-8")
    ).hexdigest()
    import_id = f"asset_import_{request_hash[:24]}"
    imported_at = datetime.now(timezone.utc).isoformat()
    summary = result.as_dict()
    summary["graph"] = result.graph.model_dump(mode="json")
    import_record = {
        "schema_version": "asset-import-record.v1",
        "import_id": import_id,
        "source": req.source,
        "source_records": result.source_records,
        "imported_node_count": len(result.imported_nodes),
        "graph_node_count": len(result.graph.nodes),
        "graph_edge_count": len(result.graph.edges),
        "deduplicated_count": result.deduplicated_count,
        "rejected_count": len(result.rejected),
        "scope_counts": scope_counts,
        "request_hash": request_hash,
        "imported_at": imported_at,
    }
    imports = [
        item
        for item in state.data.setdefault("asset_imports", [])
        if isinstance(item, dict) and str(item.get("import_id", "")) != import_id
    ]
    imports.append(import_record)
    state.data["asset_imports"] = imports[-100:]
    state.data["asset_graph"] = summary["graph"]

    state.event_store.append(
        state.event_task_id,
        "asset.inventory.imported",
        import_record,
        actor="asset-importer",
        idempotency_key=f"asset-import:{import_id}",
    )
    nodes_by_id = {node.node_id: node for node in result.graph.nodes}
    for node_id in result.imported_nodes:
        node = nodes_by_id.get(node_id)
        if node is None:
            continue
        state.event_store.append(
            state.event_task_id,
            "asset.observed",
            {
                "asset_id": node.node_id,
                "canonical_id": node.canonical_id,
                "kind": node.kind,
                "target": node.target,
                "port": node.port,
                "status": node.status,
                "confidence": node.confidence,
                "scope_status": node.attributes.get("scope_status", "SCOPE_UNKNOWN"),
                "source_refs": node.source_refs,
                "import_id": import_id,
            },
            actor="asset-importer",
            idempotency_key=f"asset-import:{import_id}:{node.node_id}",
        )
    state.data["event_count"] = state.event_store.verify()["event_count"]
    state.save()
    return {
        "task_id": req.task_id,
        "import_id": import_id,
        "scope_counts": scope_counts,
        **summary,
    }


@router.post("/agent/web/crawl")
async def agent_web_crawl(req: WebCrawlRequest):
    """Run the scoped Web runtime against a fixture or explicitly selected HTTP transport."""
    state = _load_task_state(req.task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        scope = ScopeContract.model_validate(state.data.get("scope_contract") or {})
    except Exception as exc:
        raise HTTPException(status_code=409, detail="任务缺少有效 Scope Contract") from exc

    normalized_seeds: list[str] = []
    origins: set[str] = set()
    for seed in req.seeds:
        parts = __import__("urllib.parse", fromlist=["urlsplit"]).urlsplit(str(seed).strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise HTTPException(status_code=400, detail="Web seed 必须是 HTTP 或 HTTPS URL")
        host = parts.hostname
        if not ScopePolicy.target_in_scope(host, scope):
            raise HTTPException(status_code=403, detail=f"Web seed 超出任务范围: {host}")
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        if not ScopePolicy.port_in_scope(port, scope):
            raise HTTPException(status_code=403, detail=f"Web seed 端口超出任务范围: {port}")
        normalized = ScopedWebCrawler._normalize_url(str(seed))
        normalized_seeds.append(normalized)
        origins.add(f"{parts.scheme.lower()}://{parts.netloc.lower()}")

    fixture_map = {ScopedWebCrawler._normalize_url(key): value for key, value in req.fixtures.items()}
    session = _web_sessions.get(req.session_id) if req.session_id else None
    if session is None:
        session = AuthSession(req.session_id or f"web_{uuid4().hex}", req.role)
        _web_sessions.put(session)

    client: httpx.Client | None = None
    if req.transport == "http":
        client = httpx.Client(timeout=15.0, follow_redirects=False)

    def fetch(url: str, method: str) -> WebFetch:
        fixture = fixture_map.get(url)
        if req.transport == "fixture":
            if fixture is None:
                return WebFetch(url, 599, body="fixture missing", request_id="fixture-missing")
            return WebFetch(
                url,
                fixture.status_code,
                headers=dict(fixture.headers),
                body=fixture.body,
                request_id=fixture.request_id or f"fixture:{url}",
                facts=dict(fixture.facts),
            )
        assert client is not None
        response = client.request(method, url, headers=session.request_headers())
        return WebFetch(
            url,
            response.status_code,
            headers=dict(response.headers),
            body=response.text,
            request_id=f"http:{response.headers.get('x-request-id', '')}",
            facts={},
        )

    try:
        crawler = ScopedWebCrawler(
            WebCrawlerPolicy(
                tuple(sorted(origins)),
                max_depth=req.max_depth,
                max_requests_per_second=req.max_requests_per_second,
                max_content_bytes=req.max_content_bytes,
            ),
            fetch,
            session_store=_web_sessions,
        )
        crawl = crawler.crawl(normalized_seeds, role=req.role, session=session)
    finally:
        if client is not None:
            client.close()

    from dataclasses import asdict

    observation_payloads = [asdict(item) for item in crawl.observations]
    rule_engine = WebRuleEngine()
    web_finding_payloads: list[dict[str, Any]] = []
    for item in crawl.observations:
        facts = dict(item.facts or {})
        facts["evidence_refs"] = [f"web:{item.endpoint_id}:{item.body_hash}"]
        for finding in rule_engine.evaluate(facts):
            finding_payload = asdict(finding)
            finding_payload.update({
                "finding_id": "webfinding_" + __import__("hashlib").sha256(
                    f"{item.endpoint_id}:{finding.rule_id}:{item.body_hash}".encode("utf-8")
                ).hexdigest()[:20],
                "url": item.url,
                "endpoint_id": item.endpoint_id,
                "body_hash": item.body_hash,
                "role": item.role,
            })
            web_finding_payloads.append(finding_payload)
    def _web_json_default(value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"unsupported Web payload type: {type(value).__name__}")

    site_payloads = json.loads(json.dumps(crawl.sites, default=_web_json_default, ensure_ascii=False))
    state.data.setdefault("web_observations", []).extend(observation_payloads)
    state.data["web_observations"] = state.data["web_observations"][-5000:]
    state.data["web_sites"] = site_payloads
    state.data["web_blocked"] = list(crawl.blocked)[-2000:]
    existing_web_findings = state.data.setdefault("web_findings", [])
    by_id = {
        str(item.get("finding_id")): item
        for item in existing_web_findings
        if isinstance(item, dict) and item.get("finding_id")
    }
    for item in web_finding_payloads:
        by_id[str(item["finding_id"])] = item
    state.data["web_findings"] = list(by_id.values())[-2000:]
    state.data["web_sessions"] = _web_sessions.redacted()
    # Rebuild the graph from the normalized read models so Web findings and
    # classic service observations share one asset vocabulary.
    graph = AssetGraph.from_state(state.data)
    state.data["asset_graph"] = graph.model_dump(mode="json")
    for node in graph.nodes:
        state.event_store.append(
            state.event_task_id,
            "asset.observed",
            {
                "asset_id": node.node_id,
                "kind": node.kind,
                "label": node.label,
                "status": node.status,
                "confidence": node.confidence,
            },
            actor="asset-graph",
            idempotency_key=f"asset:web:{node.node_id}:{node.status}",
        )
    for item in crawl.observations:
        state.event_store.append(
            state.event_task_id,
            "web.observation",
            {
                "url": item.url,
                "depth": item.depth,
                "status_code": item.status_code,
                "body_hash": item.body_hash,
                "endpoint_id": item.endpoint_id,
                "role": item.role,
            },
            actor="web-runtime",
            idempotency_key=f"web:observation:{item.endpoint_id}:{item.body_hash}",
        )
    for item in crawl.blocked:
        state.event_store.append(
            state.event_task_id,
            "web.blocked",
            {"url": item.get("url", ""), "reason": item.get("reason", "")},
            actor="web-runtime",
            idempotency_key=f"web:blocked:{item.get('url', '')}:{item.get('reason', '')}",
        )
    for item in web_finding_payloads:
        state.event_store.append(
            state.event_task_id,
            "web.finding",
            {
                "finding_id": item.get("finding_id", ""),
                "rule_id": item.get("rule_id", ""),
                "category": item.get("category", ""),
                "status": item.get("status", ""),
                "reason": item.get("reason", ""),
                "url": item.get("url", ""),
                "endpoint_id": item.get("endpoint_id", ""),
                "evidence_refs": list(item.get("evidence_refs", [])),
            },
            actor="web-rule-engine",
            evidence_refs=list(item.get("evidence_refs", [])),
            idempotency_key=f"web:finding:{item.get('finding_id', '')}",
        )
    state.data["event_count"] = state.event_store.verify()["event_count"]
    state.save()
    return {
        "task_id": req.task_id,
        "session_id": session.session_id,
        "observations": observation_payloads,
        "sites": site_payloads,
        "blocked": crawl.blocked,
        "findings": web_finding_payloads,
        "request_count": crawl.request_count,
        "rate_delays": crawl.rate_delays,
    }


@router.post("/agent/web/browser/trace")
async def agent_web_browser_trace(req: BrowserTraceRequest):
    """Persist a redacted browser trace and optionally replay its actions."""
    state = _load_task_state(req.task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    trace = BrowserTrace(req.browser_version, trace_id=req.trace_id or f"trace_{uuid4().hex}")
    plugin = BrowserAutomationPlugin(req.browser_version, trace=trace)
    for item in req.dom_snapshots:
        plugin.record_dom(str(item.get("url", "")), str(item.get("dom", "")))
    for item in req.network:
        plugin.record_network(
            str(item.get("method", "GET")),
            str(item.get("url", "")),
            int(item.get("status_code", 0) or 0),
            str(item.get("request", "")),
            str(item.get("response", "")),
        )
    for item in req.actions:
        plugin.record_action(
            str(item.get("kind", "")),
            str(item.get("target", "")),
            str(item.get("value", "")),
        )
    replay_results: list[dict[str, Any]] = []
    if req.replay:
        try:
            replay_results = plugin.replay(
                lambda action: {"sequence": action.sequence, "kind": action.kind, "target": action.target},
                browser_version=req.replay_browser_version or req.browser_version,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    trace_payload = trace.as_dict(include_dom=True)
    state.data.setdefault("browser_traces", {})[trace.trace_id] = trace_payload
    state.event_store.append(
        state.event_task_id,
        "web.browser_trace",
        {
            "trace_id": trace.trace_id,
            "browser_version": trace.browser_version,
            "dom_count": len(trace.dom_snapshots),
            "network_count": len(trace.network),
            "action_count": len(trace.actions),
            "replayed": bool(req.replay),
        },
        actor="browser-plugin",
        idempotency_key=f"web:browser:{trace.trace_id}:{len(trace.actions)}",
    )
    state.data["event_count"] = state.event_store.verify()["event_count"]
    state.save()
    return {"task_id": req.task_id, "trace": trace_payload, "replay": replay_results}

@router.get("/agent/report")
async def pentest_get_report(task_id: str):
    state = _load_task_state(task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    report_path = state.generate_report()
    with open(report_path, "r", encoding="utf-8") as f:
        content = f.read()
    report_document, report_check = _build_report_check(state, task_id)
    return {
        "report": content,
        "view": state.build_report_view_model(),
        "document": report_document,
        "completeness": report_check.as_dict(),
        "phase": state.data["phase"],
        "task_id": task_id,
        "token_usage": state.data.get("token_usage", {}),
    }


@router.post("/agent/report/export")
async def pentest_export_report(req: ReportExportRequest):
    state = _load_task_state(req.task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")
    document, report_check = _build_report_check(state, req.task_id)
    export_dir = os.path.join(os.path.dirname(state.path) or ".", "report_exports", req.task_id)
    result = ReportExporter(document).export(export_dir, formats=tuple(req.formats))
    return {
        "task_id": req.task_id,
        "formats": list(req.formats),
        "integrity_hash": result["integrity_hash"],
        "files": {fmt: os.path.basename(path) for fmt, path in result["paths"].items()},
        "completeness": report_check.as_dict(),
    }


@router.post("/agent/token-usage")
async def pentest_record_token_usage(req: PentestTokenUsageRequest):
    state = _load_task_state(req.task_id)
    if not state:
        raise HTTPException(status_code=404, detail="任务不存在")

    usage = {
        "prompt_tokens": req.prompt_tokens,
        "completion_tokens": req.completion_tokens,
        "total_tokens": req.total_tokens,
    }
    recorded = state.record_token_usage(
        req.category,
        usage,
        model=req.model,
        provider=req.provider,
    )
    if not recorded:
        raise HTTPException(status_code=400, detail="token usage 无效")

    summary = (
        f"category={req.category} "
        f"prompt={req.prompt_tokens} "
        f"completion={req.completion_tokens} "
        f"total={req.total_tokens}"
    )
    if req.model:
        summary += f" model={req.model}"
    if req.provider:
        summary += f" provider={req.provider}"

    state.log_action(
        "_token_usage",
        req.category,
        result_summary=summary,
        llm_decision="记录本次 AI token 消耗统计。",
    )

    return {
        "success": True,
        "task_id": req.task_id,
        "category": req.category,
        "token_usage": state.data.get("token_usage", {}),
    }

@router.get("/agent/history")
async def pentest_history():
    """返回所有渗透任务历史列表"""
    items = []
    seen: set[str] = set()

    for state_path in _list_pentest_state_files():
        task_id = _extract_task_id_from_state_file(state_path)
        if not task_id or task_id in seen:
            continue
        item = _build_history_item(task_id, _pentest_tasks.get(task_id))
        if item:
            items.append(item)
            seen.add(task_id)

    for task_id, tinfo in sorted(_pentest_tasks.items(), reverse=True):
        if task_id in seen:
            continue
        item = _build_history_item(task_id, tinfo)
        if item:
            items.append(item)
            seen.add(task_id)

    items.sort(key=lambda item: item.get("start_time", ""), reverse=True)
    return {"history": items, "total": len(items)}

@router.delete("/agent/history/{task_id}")
async def pentest_delete_history(task_id: str):
    tinfo = _pentest_tasks.pop(task_id, None)
    candidate_paths = [_state_file(task_id)]

    if tinfo and tinfo.get("state_file"):
        candidate_paths.insert(0, tinfo["state_file"])

    deleted = False
    for state_path in dict.fromkeys(candidate_paths):
        try:
            os.remove(state_path)
            deleted = True
        except FileNotFoundError:
            continue

    report_candidates = [
        os.path.join(_PENTEST_STATE_DIR, f"pentest_report_{task_id}.html"),
        os.path.join(_PENTEST_STATE_DIR, f"pentest_report_{task_id}.md"),
    ]
    for report_path in dict.fromkeys(report_candidates):
        try:
            os.remove(report_path)
        except FileNotFoundError:
            continue

    if deleted or tinfo:
        return {"success": True, "message": "已删除"}
    return {"success": False, "message": "任务不存在"}

@router.get("/crypto/rsa-public-key")
async def get_rsa_key():
    return {"public_key": get_rsa_public_key()}
@router.get("/device/uuid")
async def get_device_uuid_endpoint():
    info = get_device_uuid()
    return info.model_dump()

# ==================== Skills 管理 ====================
_SKILLS_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "skills")
_KNOWLEDGE_BASE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "knowledge_base")

def _ensure_kb_dir():
    os.makedirs(_KNOWLEDGE_BASE_ROOT, exist_ok=True)

@router.get("/skills")
async def list_skills():
    """列出所有 skills（支持 json+md 共存，返回 mode 标识）"""
    from app.services.skill_engine import SkillLoader
    loader = SkillLoader(_SKILLS_ROOT)
    skills = loader.load_all()
    items = [s.to_api_dict() for s in skills]
    return {"items": items}

@router.delete("/skills/{filename}")
async def delete_skill(filename: str):
    """删除指定 skill（在所有子目录中查找）"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    for root, _dirs, files in os.walk(_SKILLS_ROOT):
        if filename in files:
            fpath = os.path.join(root, filename)
            os.remove(fpath)
            return {"success": True, "message": "已删除"}
    raise HTTPException(status_code=404, detail="文件不存在")

@router.post("/skills")
async def upload_skill(file: UploadFile = File(...)):
    """上传新 skill JSON 文件（默认存到 experimental）"""
    fname = file.filename or "unknown.json"
    if not fname.endswith(".json"):
        fname += ".json"
    if ".." in fname or "/" in fname or "\\" in fname:
        raise HTTPException(status_code=400, detail="无效的文件名")
    target_dir = os.path.join(_SKILLS_ROOT, "experimental")
    os.makedirs(target_dir, exist_ok=True)
    fpath = os.path.join(target_dir, fname)
    content = await file.read()
    try:
        json.loads(content.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无效的 JSON: {e}")
    with open(fpath, "wb") as f:
        f.write(content)
    return {"success": True, "message": "上传成功", "filename": fname}

# ==================== 本地知识库管理 ====================
@router.get("/knowledge-base")
async def list_knowledge_base():
    """列出本地知识库条目"""
    _ensure_kb_dir()
    result = []
    for fname in sorted(os.listdir(_KNOWLEDGE_BASE_ROOT)):
        fpath = os.path.join(_KNOWLEDGE_BASE_ROOT, fname)
        if os.path.isfile(fpath) and fname.endswith(".json"):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                result.append({
                    "name": data.get("name", fname),
                    "filename": fname,
                    "description": data.get("description", ""),
                    "source_path": data.get("source_path", ""),
                    "content_preview": json.dumps(data)[:200],
                })
            except Exception:
                result.append({
                    "name": fname,
                    "filename": fname,
                    "description": "",
                    "source_path": "",
                    "content_preview": "",
                })
    return {"items": result}

@router.delete("/knowledge-base/{filename}")
async def delete_knowledge_base(filename: str):
    """删除知识库条目"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    _ensure_kb_dir()
    fpath = os.path.join(_KNOWLEDGE_BASE_ROOT, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="文件不存在")
    os.remove(fpath)
    return {"success": True, "message": "已删除"}

class KnowledgeBaseCreateRequest(BaseModel):
    name: str
    description: str = ""
    content: str = ""


class KnowledgeBaseImportRequest(BaseModel):
    paths: List[str] = Field(default_factory=list)


def _safe_kb_filename(name: str) -> str:
    safe_name = "".join(c for c in str(name or "") if c.isalnum() or c in "-_ ").strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    return safe_name


def _read_local_text_file(path: str) -> str:
    try_encodings = ("utf-8", "utf-8-sig", "gb18030", "gbk")
    with open(path, "rb") as f:
        raw = f.read()
    for encoding in try_encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail=f"文件无法按文本读取: {os.path.basename(path)}")

@router.post("/knowledge-base")
async def create_knowledge_base(req: KnowledgeBaseCreateRequest):
    """创建知识库条目"""
    _ensure_kb_dir()
    safe_name = _safe_kb_filename(req.name)
    filename = f"{safe_name}.json"
    fpath = os.path.join(_KNOWLEDGE_BASE_ROOT, filename)
    data = {
        "name": req.name,
        "description": req.description,
        "content": req.content,
        "created_at": str(datetime.now()),
    }
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"success": True, "message": "创建成功", "filename": filename}


@router.post("/knowledge-base/import-local")
async def import_local_knowledge_base(req: KnowledgeBaseImportRequest):
    """从本机文件导入知识库条目"""
    _ensure_kb_dir()
    paths = [str(path or "").strip() for path in req.paths if str(path or "").strip()]
    if not paths:
        raise HTTPException(status_code=400, detail="请先选择要导入的本地文件")

    imported = []
    for path in paths:
        normalized = os.path.abspath(os.path.normpath(path))
        if not os.path.exists(normalized):
            raise HTTPException(status_code=404, detail=f"文件不存在: {path}")
        if not os.path.isfile(normalized):
            raise HTTPException(status_code=400, detail=f"仅支持导入文件: {path}")

        content = _read_local_text_file(normalized)
        base_name = os.path.splitext(os.path.basename(normalized))[0]
        safe_name = _safe_kb_filename(base_name)
        filename = f"{safe_name}.json"
        fpath = os.path.join(_KNOWLEDGE_BASE_ROOT, filename)
        suffix = 2
        while os.path.exists(fpath):
            filename = f"{safe_name}-{suffix}.json"
            fpath = os.path.join(_KNOWLEDGE_BASE_ROOT, filename)
            suffix += 1

        data = {
            "name": base_name,
            "description": f"导入自本地文件: {normalized}",
            "content": content,
            "source_path": normalized,
            "created_at": str(datetime.now()),
        }
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        imported.append({
            "name": base_name,
            "filename": filename,
            "source_path": normalized,
        })

    return {
        "success": True,
        "message": f"成功导入 {len(imported)} 个本地文件",
        "items": imported,
    }


@router.post("/knowledge-base/upload")
async def upload_knowledge_base_files(files: List[UploadFile] = File(...)):
    """从浏览器选择的本地文件上传并导入知识库"""
    _ensure_kb_dir()
    if not files:
        raise HTTPException(status_code=400, detail="请先选择要导入的本地文件")

    imported = []
    for upload in files:
        original_name = str(upload.filename or "").strip() or "untitled.txt"
        raw = await upload.read()

        content = None
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                content = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if content is None:
            raise HTTPException(status_code=400, detail=f"文件无法按文本读取: {original_name}")

        base_name = os.path.splitext(os.path.basename(original_name))[0]
        safe_name = _safe_kb_filename(base_name)
        filename = f"{safe_name}.json"
        fpath = os.path.join(_KNOWLEDGE_BASE_ROOT, filename)
        suffix = 2
        while os.path.exists(fpath):
            filename = f"{safe_name}-{suffix}.json"
            fpath = os.path.join(_KNOWLEDGE_BASE_ROOT, filename)
            suffix += 1

        data = {
            "name": base_name,
            "description": f"导入自本地文件: {original_name}",
            "content": content,
            "source_path": original_name,
            "created_at": str(datetime.now()),
        }
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        imported.append({
            "name": base_name,
            "filename": filename,
            "source_path": original_name,
        })

    return {
        "success": True,
        "message": f"成功导入 {len(imported)} 个本地文件",
        "items": imported,
    }
