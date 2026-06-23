import base64
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.models.types import SSHConnection
from app.services.settings import get_app_data_dir
class SSHConnectionManager:
    def __init__(self):
        self.app_data_dir = get_app_data_dir()
        self.connections_file = self.app_data_dir / "ssh_connections.json"
        self.backups_dir = self.app_data_dir / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.encryption_key = self._get_or_create_encryption_key()
    def _get_or_create_encryption_key(self) -> bytes:
        key_file = self.app_data_dir / "encryption.key"
        if key_file.exists():
            key_data = key_file.read_bytes()
            if len(key_data) != 32:
                raise ValueError("加密密钥长度错误")
            print("加载现有加密密钥")
            return key_data
        else:
            key = AESGCM.generate_key(bit_length=256)
            key_file.write_bytes(key)
            print("生成新的加密密钥")
            return key
    def load_connections(self) -> List[SSHConnection]:
        if not self.connections_file.exists():
            print("SSH连接配置文件不存在，返回空列表")
            return []
        try:
            content = self.connections_file.read_text(encoding="utf-8")
            raw_list = json.loads(content)
            connections = [SSHConnection.model_validate(c) for c in raw_list]
        except Exception as e:
            print(f"解析SSH配置文件失败: {e}")
            return []
        migrated_count = 0
        for conn in connections:
            if not conn.accounts and conn.username:
                conn.migrate_legacy_account()
                migrated_count += 1
        if migrated_count > 0:
            print(f"自动迁移了 {migrated_count} 个旧账号数据到多账号模式")
            try:
                self.save_connections(connections)
            except Exception as e:
                print(f"保存迁移后的数据失败: {e}")
        return connections
    def save_connections(self, connections: List[SSHConnection]) -> None:
        self.connections_file.parent.mkdir(parents=True, exist_ok=True)
        data = [c.model_dump(mode="json") for c in connections]
        content = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        self.connections_file.write_text(content, encoding="utf-8")
        print(f"成功保存 {len(connections)} 个SSH连接配置")
    def encrypt_password(self, password: str) -> str:
        aesgcm = AESGCM(self.encryption_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, password.encode("utf-8"), None)
        encrypted_data = nonce + ciphertext
        return base64.b64encode(encrypted_data).decode("utf-8")
    def decrypt_password(self, encrypted_password: str) -> str:
        aesgcm = AESGCM(self.encryption_key)
        encrypted_data = base64.b64decode(encrypted_password)
        if len(encrypted_data) < 12:
            raise ValueError("加密数据格式错误")
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    def create_backup(self) -> str:
        if not self.connections_file.exists():
            raise FileNotFoundError("SSH配置文件不存在")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"ssh_connections_backup_{timestamp}.json"
        backup_path = self.backups_dir / backup_filename
        shutil.copy2(self.connections_file, backup_path)
        print(f"创建SSH配置备份: {backup_filename}")
        return backup_filename
    def restore_from_backup(self, backup_filename: str) -> None:
        backup_path = self.backups_dir / backup_filename
        if not backup_path.exists():
            raise FileNotFoundError("备份文件不存在")
        shutil.copy2(backup_path, self.connections_file)
        print(f"从备份恢复SSH配置: {backup_filename}")
    def cleanup_old_backups(self, keep_count: int = 5) -> int:
        if not self.backups_dir.exists():
            return 0
        backup_files = sorted(
            [f for f in self.backups_dir.iterdir()
             if f.name.startswith("ssh_connections_backup_") and f.is_file()],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        deleted_count = 0
        for backup_file in backup_files[keep_count:]:
            try:
                backup_file.unlink()
                deleted_count += 1
            except Exception as e:
                print(f"删除旧备份失败: {backup_file}: {e}")
        if deleted_count > 0:
            print(f"清理了 {deleted_count} 个旧备份文件")
        return deleted_count
    def validate_config(self) -> bool:
        if not self.connections_file.exists():
            return True
        try:
            self.load_connections()
            print("SSH配置文件验证通过")
            return True
        except Exception as e:
            print(f"SSH配置文件验证失败: {e}")
            return False