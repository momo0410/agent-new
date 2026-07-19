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

import hashlib
import json
import logging
import os
import shutil
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

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

LIFECYCLE_STATES = {"draft", "evaluating", "canary", "active", "deprecated", "quarantined", "rejected"}


@dataclass
class SkillLifecycleEntry:
    status: str  # draft | active | deprecated | rejected
    created_at: str
    promoted_at: str | None = None
    deprecated_at: str | None = None
    used_count: int = 0
    successful_uses: int = 0
    last_used: str | None = None
    current_path: str | None = None
    notes: str | None = None
    skill_id: str = ""
    version: str = "0.0.0"
    origin: str = "manual"
    evaluation_id: str | None = None
    evaluation_passed: bool = False
    canary_percent: int = 0
    rollback_target: str | None = None
    audit_revision: int = 0

    @classmethod
    def from_dict(cls, raw: dict) -> SkillLifecycleEntry:
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
            skill_id=str(raw.get("skill_id", "")),
            version=str(raw.get("version", "0.0.0")),
            origin=str(raw.get("origin", "manual")),
            evaluation_id=raw.get("evaluation_id"),
            evaluation_passed=bool(raw.get("evaluation_passed", False)),
            canary_percent=int(raw.get("canary_percent", 0) or 0),
            rollback_target=raw.get("rollback_target"),
            audit_revision=int(raw.get("audit_revision", 0) or 0),
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
        self._cache: dict[str, SkillLifecycleEntry] | None = None

    # ----- 初始化 -----

    def ensure_dirs(self) -> None:
        for d in (self.learned_root, self.draft_dir, self.active_dir, self.deprecated_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError as exc:
                LOGGER.warning("LifecycleManager: 无法创建目录 %s: %s", d, exc)

    # ----- 注册新 skill -----

    def register_draft(self, skill_name: str, file_path: str, notes: str = "", *, origin: str = "manual", version: str = "0.0.0") -> SkillLifecycleEntry:
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
                existing.origin = origin or existing.origin
                existing.version = version or existing.version
                self._save(data)
                return existing
            entry = SkillLifecycleEntry(
                status="draft",
                created_at=now,
                current_path=file_path,
                notes=notes or None,
                skill_id=f"skill_{hashlib.sha256(skill_name.encode()).hexdigest()[:20]}",
                version=version,
                origin=origin,
            )
            data[skill_name] = entry
            self._save(data)
            return entry

    def register_generated_draft(self, skill_name: str, file_path: str, *, version: str = "0.1.0", notes: str = "") -> SkillLifecycleEntry:
        """Register generated knowledge with an evaluation requirement."""
        return self.register_draft(skill_name, file_path, notes, origin="generated", version=version)

    def begin_evaluation(self, skill_name: str, *, evaluation_id: str) -> SkillLifecycleEntry:
        with self._lock:
            data = self._load()
            entry = data.get(skill_name)
            if entry is None:
                raise KeyError(skill_name)
            if entry.status not in {"draft", "evaluating"}:
                raise ValueError(f"skill is not evaluable in state {entry.status}")
            entry.status = "evaluating"
            entry.evaluation_id = evaluation_id
            entry.audit_revision += 1
            self._save(data)
            return entry

    def record_evaluation(self, skill_name: str, *, evaluation_id: str, passed: bool, metrics: dict[str, float] | None = None) -> SkillLifecycleEntry:
        with self._lock:
            data = self._load()
            entry = data.get(skill_name)
            if entry is None:
                raise KeyError(skill_name)
            if entry.evaluation_id and entry.evaluation_id != evaluation_id:
                raise ValueError("evaluation id mismatch")
            entry.evaluation_id = evaluation_id
            entry.evaluation_passed = bool(passed)
            entry.notes = json.dumps({"evaluation": metrics or {}}, ensure_ascii=False, sort_keys=True)
            entry.status = "canary" if passed else "quarantined"
            entry.canary_percent = 5 if passed else 0
            entry.audit_revision += 1
            self._save(data)
            return entry

    def promote_canary(self, skill_name: str, *, percent: int = 100, reviewer: str = "") -> SkillLifecycleEntry:
        with self._lock:
            data = self._load()
            entry = data.get(skill_name)
            if entry is None:
                raise KeyError(skill_name)
            if entry.status != "canary" or not entry.evaluation_passed:
                raise ValueError("skill must pass evaluation before canary promotion")
            entry.canary_percent = max(1, min(100, int(percent)))
            if entry.canary_percent >= 100:
                entry.status = "active"
                entry.promoted_at = datetime.now(timezone.utc).isoformat()
            entry.notes = f"reviewer={reviewer}" if reviewer else entry.notes
            entry.audit_revision += 1
            self._save(data)
            return entry

    def promote_evaluated(
        self,
        skill_name: str,
        *,
        manifest: Any,
        evaluation: Any,
        content: str,
        knowledge_records: list[Any] | None = None,
        reviewer: str = "",
        percent: int = 5,
    ) -> SkillLifecycleEntry:
        """Run the canonical promotion gate before entering canary/active."""
        from app.core.skill_contract import SkillPromotionGate

        passed, reasons = SkillPromotionGate().check(
            manifest,
            evaluation,
            content=content,
            knowledge_records=knowledge_records,
        )
        if not passed:
            with self._lock:
                data = self._load()
                entry = data.get(skill_name)
                if entry is None:
                    raise KeyError(skill_name)
                entry.status = "quarantined"
                entry.evaluation_passed = False
                entry.notes = "; ".join(reasons)[:1000]
                entry.audit_revision += 1
                self._save(data)
                return entry
        with self._lock:
            data = self._load()
            entry = data.get(skill_name)
            if entry is None:
                raise KeyError(skill_name)
            entry.evaluation_id = evaluation.evaluation_id
            entry.evaluation_passed = True
            entry.status = "canary"
            entry.canary_percent = max(1, min(100, int(percent)))
            entry.notes = f"reviewer={reviewer}; gate=passed"[:1000]
            entry.audit_revision += 1
            if entry.canary_percent >= 100:
                entry.status = "active"
                entry.promoted_at = datetime.now(timezone.utc).isoformat()
            self._save(data)
            return entry

    def rollback(self, skill_name: str, *, reason: str) -> SkillLifecycleEntry:
        with self._lock:
            data = self._load()
            entry = data.get(skill_name)
            if entry is None:
                raise KeyError(skill_name)
            entry.rollback_target = entry.status
            entry.status = "quarantined"
            entry.canary_percent = 0
            entry.notes = f"rollback: {reason}"[:500]
            entry.audit_revision += 1
            self._save(data)
            return entry

    def quarantine(self, skill_name: str, *, reason: str) -> SkillLifecycleEntry:
        return self.rollback(skill_name, reason=reason)

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
                    # Preserve the original maintenance behavior for manually
                    # registered legacy entries. Generated entries must pass
                    # the explicit evaluation/canary flow above.
                    legacy_eligible = entry.origin == "manual" and not entry.evaluation_id
                    if legacy_eligible and self._should_promote(entry, now):
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

    def _move_file(self, entry: SkillLifecycleEntry, dest_dir: str) -> str | None:
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
            with open(self.lifecycle_path, encoding="utf-8") as f:
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

    def get_status(self, skill_name: str) -> str | None:
        data = self._load()
        entry = data.get(skill_name)
        return entry.status if entry else None

    def list_by_status(self, status: str) -> list[str]:
        data = self._load()
        return [name for name, e in data.items() if e.status == status]


__all__ = ["LifecycleManager", "SkillLifecycleEntry"]

