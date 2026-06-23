"""
LifecycleManager — 自动生成 skill 的生命周期状态机

状态流转：
    draft ──promote──► active ──retire──► deprecated
      │                  ▲
      │ negative-fb      │ used_successfully
      ▼                  │
   rejected ◄────────────┘ manual override

状态持久化在 `skills/learned/.lifecycle.json`，结构：

    {
      "exploit-vsftpd-234-backdoor": {
        "status": "draft",
        "created_at": "2026-06-24T10:00:00",
        "promoted_at": null,
        "deprecated_at": null,
        "used_count": 0,
        "successful_uses": 0,
        "last_used": null,
        "current_path": "skills/learned/draft/exploit-vsftpd-234-backdoor.md"
      }
    }

自动晋升规则：
- successful_uses >= 2 AND 距 created_at > 1 天 → 移到 active/
- created_at 距今 > 30 天 AND used_count == 0 → 移到 deprecated/
- 主循环每次成功用了一个 learned skill → record_use(skill_name, success=True)

降级失败时 graceful（只是不晋升，不影响主流程）。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

LOGGER = logging.getLogger(__name__)

# ----- 常量 -----

LIFECYCLE_FILENAME = ".lifecycle.json"
DRAFT_DIRNAME = "draft"
ACTIVE_DIRNAME = "active"
DEPRECATED_DIRNAME = "deprecated"

PROMOTE_MIN_SUCCESSFUL_USES = 2
PROMOTE_MIN_AGE_HOURS = 24
DEPRECATE_AGE_DAYS = 30
DEPRECATE_MIN_UNUSED = True  # 仅淘汰从未被使用的


@dataclass
class SkillLifecycleEntry:
    status: str  # draft | active | deprecated | rejected
    created_at: str
    promoted_at: Optional[str] = None
    deprecated_at: Optional[str] = None
    used_count: int = 0
    successful_uses: int = 0
    last_used: Optional[str] = None
    current_path: Optional[str] = None
    notes: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "SkillLifecycleEntry":
        return cls(
            status=str(raw.get("status", "draft")),
            created_at=str(raw.get("created_at", datetime.now(timezone.utc).isoformat())),
            promoted_at=raw.get("promoted_at"),
            deprecated_at=raw.get("deprecated_at"),
            used_count=int(raw.get("used_count", 0) or 0),
            successful_uses=int(raw.get("successful_uses", 0) or 0),
            last_used=raw.get("last_used"),
            current_path=raw.get("current_path"),
            notes=raw.get("notes"),
        )


class LifecycleManager:
    """管理 skills/learned/ 下的 draft/active/deprecated 三态"""

    def __init__(self, skills_root: str):
        self.skills_root = skills_root
        self.learned_root = os.path.join(skills_root, "learned")
        self.draft_dir = os.path.join(self.learned_root, DRAFT_DIRNAME)
        self.active_dir = os.path.join(self.learned_root, ACTIVE_DIRNAME)
        self.deprecated_dir = os.path.join(self.learned_root, DEPRECATED_DIRNAME)
        self.lifecycle_path = os.path.join(self.learned_root, LIFECYCLE_FILENAME)
        self._lock = threading.RLock()
        self._cache: Optional[dict[str, SkillLifecycleEntry]] = None

    # ----- 初始化 -----

    def ensure_dirs(self) -> None:
        for d in (self.learned_root, self.draft_dir, self.active_dir, self.deprecated_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as exc:
                LOGGER.warning("LifecycleManager: 无法创建目录 %s: %s", d, exc)

    # ----- 注册新 skill -----

    def register_draft(self, skill_name: str, file_path: str, notes: str = "") -> SkillLifecycleEntry:
        """生成新 skill 后登记为 draft"""
        with self._lock:
            data = self._load()
            now = datetime.now(timezone.utc).isoformat()
            existing = data.get(skill_name)
            if existing:
                # 已存在：仅更新 path / notes，不重置统计
                existing.current_path = file_path
                if notes:
                    existing.notes = notes
                self._save(data)
                return existing
            entry = SkillLifecycleEntry(
                status="draft",
                created_at=now,
                current_path=file_path,
                notes=notes or None,
            )
            data[skill_name] = entry
            self._save(data)
            return entry

    # ----- 使用反馈 -----

    def record_use(self, skill_name: str, success: bool = False) -> None:
        """主循环每次实际用上某个 learned skill 时回写"""
        with self._lock:
            data = self._load()
            entry = data.get(skill_name)
            if not entry:
                return
            entry.used_count += 1
            if success:
                entry.successful_uses += 1
            entry.last_used = datetime.now(timezone.utc).isoformat()
            self._save(data)

    # ----- 自动维护 -----

    def auto_maintenance(self) -> dict:
        """根据规则自动晋升/淘汰，返回操作摘要"""
        with self._lock:
            data = self._load()
            promoted: list[str] = []
            deprecated: list[str] = []
            now = datetime.now(timezone.utc)

            for name, entry in list(data.items()):
                if entry.status == "draft":
                    if self._should_promote(entry, now):
                        moved = self._move_file(entry, self.active_dir)
                        if moved:
                            entry.status = "active"
                            entry.promoted_at = now.isoformat()
                            entry.current_path = moved
                            promoted.append(name)
                elif entry.status == "active":
                    if self._should_deprecate(entry, now):
                        moved = self._move_file(entry, self.deprecated_dir)
                        if moved:
                            entry.status = "deprecated"
                            entry.deprecated_at = now.isoformat()
                            entry.current_path = moved
                            deprecated.append(name)

            self._save(data)
            return {"promoted": promoted, "deprecated": deprecated}

    def _should_promote(self, entry: SkillLifecycleEntry, now: datetime) -> bool:
        if entry.successful_uses < PROMOTE_MIN_SUCCESSFUL_USES:
            return False
        try:
            created = datetime.fromisoformat(entry.created_at)
        except ValueError:
            return False
        return (now - created) >= timedelta(hours=PROMOTE_MIN_AGE_HOURS)

    def _should_deprecate(self, entry: SkillLifecycleEntry, now: datetime) -> bool:
        if DEPRECATE_MIN_UNUSED and entry.used_count > 0:
            return False
        try:
            created = datetime.fromisoformat(entry.created_at)
        except ValueError:
            return False
        return (now - created) >= timedelta(days=DEPRECATE_AGE_DAYS)

    def _move_file(self, entry: SkillLifecycleEntry, dest_dir: str) -> Optional[str]:
        src = entry.current_path
        if not src or not os.path.isfile(src):
            return None
        try:
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(src))
            if os.path.abspath(src) == os.path.abspath(dest):
                return src
            shutil.move(src, dest)
            return dest
        except OSError as exc:
            LOGGER.warning("LifecycleManager: 移动文件失败 %s -> %s: %s", src, dest_dir, exc)
            return None

    # ----- 持久化 -----

    def _load(self) -> dict[str, SkillLifecycleEntry]:
        if self._cache is not None:
            return self._cache
        if not os.path.isfile(self.lifecycle_path):
            self._cache = {}
            return self._cache
        try:
            with open(self.lifecycle_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("LifecycleManager: 读取状态文件失败 %s: %s", self.lifecycle_path, exc)
            raw = {}
        cache: dict[str, SkillLifecycleEntry] = {}
        for k, v in (raw or {}).items():
            if isinstance(v, dict):
                cache[k] = SkillLifecycleEntry.from_dict(v)
        self._cache = cache
        return cache

    def _save(self, data: dict[str, SkillLifecycleEntry]) -> None:
        self._cache = data
        try:
            os.makedirs(os.path.dirname(self.lifecycle_path), exist_ok=True)
            payload = {name: asdict(entry) for name, entry in data.items()}
            with open(self.lifecycle_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            LOGGER.warning("LifecycleManager: 写入状态文件失败 %s: %s", self.lifecycle_path, exc)

    # ----- 查询 -----

    def get_status(self, skill_name: str) -> Optional[str]:
        data = self._load()
        entry = data.get(skill_name)
        return entry.status if entry else None

    def list_by_status(self, status: str) -> list[str]:
        data = self._load()
        return [name for name, e in data.items() if e.status == status]


__all__ = ["LifecycleManager", "SkillLifecycleEntry"]
