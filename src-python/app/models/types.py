from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid
class SSHAccountCredential(BaseModel):
    username: str
    auth_type: str = "password"
    encrypted_password: Optional[str] = None
    key_path: Optional[str] = None
    key_passphrase: Optional[str] = None
    certificate_path: Optional[str] = None
    is_default: bool = True
    description: Optional[str] = None
class SSHConnection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "新连接"
    host: str = "localhost"
    port: int = 22
    username: str = "root"
    auth_type: str = "password"
    encrypted_password: Optional[str] = None
    key_path: Optional[str] = None
    key_passphrase: Optional[str] = None
    certificate_path: Optional[str] = None
    accounts: List[SSHAccountCredential] = Field(default_factory=list)
    active_account: Optional[str] = None
    is_connected: bool = False
    last_connected: Optional[datetime] = None
    tags: Optional[List[str]] = None
    def migrate_legacy_account(self):
        if not self.accounts and self.username:
            account = SSHAccountCredential(
                username=self.username,
                auth_type=self.auth_type,
                encrypted_password=self.encrypted_password,
                key_path=self.key_path,
                key_passphrase=self.key_passphrase,
                certificate_path=self.certificate_path,
                is_default=True,
                description="默认账号（从旧数据迁移）",
            )
            self.accounts.append(account)
            self.active_account = self.username
    def get_default_account(self) -> Optional[SSHAccountCredential]:
        for a in self.accounts:
            if a.is_default:
                return a
        return None
    def get_active_account(self) -> Optional[SSHAccountCredential]:
        if self.active_account:
            for a in self.accounts:
                if a.username == self.active_account:
                    return a
        return self.get_default_account()
    def set_active_account(self, username: str) -> bool:
        for a in self.accounts:
            if a.username == username:
                self.active_account = username
                return True
        return False
class SSHCommand(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "新命令"
    command: str = "echo 'Hello World'"
    description: str = "示例命令"
    category: str = "其他"
    favorite: bool = False
class AppNotification(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    message: str = ""
    notification_type: str = "info"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    read: bool = False
class TerminalSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    connection_id: str = ""
    created: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
class FileTransferTask(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_path: str = ""
    destination_path: str = ""
    transfer_type: str = "upload"
    status: str = "pending"
    progress: float = 0.0
    file_size: int = 0
    transferred_size: int = 0
    created: datetime = Field(default_factory=datetime.utcnow)
    completed: Optional[datetime] = None
    error_message: Optional[str] = None
class SystemMonitorData(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    network_in: int = 0
    network_out: int = 0
    load_average: List[float] = Field(default_factory=list)
    process_count: int = 0
class LogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: str = "info"
    source: str = ""
    message: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
class ApiResponse(BaseModel):
    success: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    @classmethod
    def ok(cls, data: Any = None) -> "ApiResponse":
        return cls(success=True, data=data)
    @classmethod
    def err(cls, error: str) -> "ApiResponse":
        return cls(success=False, error=error)
class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20
    sort_by: Optional[str] = None
    sort_order: Optional[str] = "asc"
class PaginatedResponse(BaseModel):
    items: List[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0
    @classmethod
    def create(
        cls, items: list, total: int, page: int, page_size: int
    ) -> "PaginatedResponse":
        import math
        total_pages = math.ceil(total / page_size) if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
class SearchFilter(BaseModel):
    query: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    tags: Optional[List[str]] = None
class AppEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    source: str = ""
    data: Any = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
class BashEnvironmentInfo(BaseModel):
    bash_version: str = ""
    shell_type: str = "bash"
    ps1: str = ""
    pwd: str = ""
    home: str = ""
    user: str = ""
    hostname: str = ""
    path: str = ""
class CommandCompletion(BaseModel):
    completions: List[str] = Field(default_factory=list)
    prefix: str = ""
class TerminalOutput(BaseModel):
    command: str = ""
    output: str = ""
    exit_code: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    @classmethod
    def create(
        cls, command: str, output: str, exit_code: Optional[int] = None
    ) -> "TerminalOutput":
        return cls(command=command, output=output, exit_code=exit_code)
class SftpFileInfo(BaseModel):
    name: str = ""
    path: str = ""
    file_type: str = "file"
    is_dir: bool = False
    size: int = 0
    modified: Optional[str] = None
    permissions: Optional[str] = None
class SftpFileDetails(BaseModel):
    name: str = ""
    path: str = ""
    file_type: str = "file"
    size: int = 0
    permissions: str = ""
    owner: Optional[str] = None
    group: Optional[str] = None
    created: Optional[str] = None
    modified: Optional[str] = None
    accessed: Optional[str] = None
class SSHConnectionStatus(BaseModel):
    connected: bool = False
    host: str = ""
    port: int = 22
    username: str = ""
    last_activity: datetime = Field(default_factory=datetime.utcnow)
class ConnectionInfo(BaseModel):
    host: str = ""
    port: int = 22
    username: str = ""
    auth_method: str = ""
class PortScanResult(BaseModel):
    open_ports: List[Dict[str, Any]] = Field(default_factory=list)
    total_open: int = 0
    risk_level: str = "low"
    details: str = ""
class UserAuditResult(BaseModel):
    users: List[Dict[str, Any]] = Field(default_factory=list)
    risk_users: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class BackdoorScanResult(BaseModel):
    suspicious_files: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class ProcessAnalysisResult(BaseModel):
    processes: List[Dict[str, Any]] = Field(default_factory=list)
    suspicious_processes: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class FilePermissionResult(BaseModel):
    risky_files: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class SSHAuditResult(BaseModel):
    config_issues: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class LogAnalysisResult(BaseModel):
    entries: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class FirewallCheckResult(BaseModel):
    status: str = ""
    rules: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class CpuTestResult(BaseModel):
    cpu_info: str = ""
    cpu_usage: float = 0.0
    details: str = ""
class MemoryTestResult(BaseModel):
    total: str = ""
    used: str = ""
    free: str = ""
    usage_percent: float = 0.0
    details: str = ""
class DiskTestResult(BaseModel):
    disks: List[Dict[str, Any]] = Field(default_factory=list)
    details: str = ""
class NetworkTestResult(BaseModel):
    interfaces: List[Dict[str, Any]] = Field(default_factory=list)
    connections: List[Dict[str, Any]] = Field(default_factory=list)
    details: str = ""
class GenericDetectionResult(BaseModel):
    title: str = ""
    status: str = "info"
    items: List[Dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
    suggestions: List[str] = Field(default_factory=list)
class LogAnalysisEntry(BaseModel):
    line: str = ""
    level: str = "info"
    highlighted: bool = False
    timestamp: Optional[str] = None
class LogAnalysisOutput(BaseModel):
    total_count: int = 0
    highlighted_count: int = 0
    entries: List[LogAnalysisEntry] = Field(default_factory=list)
    file_info: Optional[Dict[str, Any]] = None
class LogFileInfo(BaseModel):
    path: str = ""
    name: str = ""
    size: int = 0
    modified: str = ""
    readable: bool = True
class FileAnalysisResult(BaseModel):
    path: str = ""
    file_type: str = ""
    size: int = 0
    permissions: str = ""
    owner: str = ""
    group: str = ""
    hash_md5: Optional[str] = None
    hash_sha1: Optional[str] = None
    hash_sha256: Optional[str] = None
    modified: Optional[str] = None
    created: Optional[str] = None
    accessed: Optional[str] = None
    is_suid: bool = False
    is_sgid: bool = False
    is_world_writable: bool = False
    is_hidden: bool = False
    risk_indicators: List[str] = Field(default_factory=list)
    risk_level: str = "low"
    details: str = ""
class DeviceInfo(BaseModel):
    device_uuid: str = ""
    device_type: str = ""
    device_name: str = ""