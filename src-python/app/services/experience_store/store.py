"""ExperienceStore — P3 自进化 Agent 闭环：经验复用

设计目的：
    把每次渗透的 "环境指纹 + 成功路径 + 失败教训" 沉淀为可向量化检索的
    ExperienceEntry，下次遇到相似目标时在 recon 阶段直接注入历史经验。

存储布局：
    skills/.experience/<YYYY>/<MM>/<id>.json   # 单条经验
    skills/.experience/.cache/experience.npy   # (N, 512) float32 mmap
    skills/.experience/.cache/experience_meta.json
        {"model": "bge-small-zh-v1.5", "entries": [{id, path, fingerprint_hash, ts}, ...]}

检索接口（在 recon -> 下一阶段跃迁后调用）：
    store = ExperienceStore(skills_root)
    fingerprint = state.build_target_fingerprint()
    hits = store.query_similar_env(fingerprint, top_k=3, min_score=0.5)
    if hits:
        state.attach_history_context(store.render_for_prompt(hits))
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

LOGGER = logging.getLogger(__name__)

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_OK = False


# ============ 数据结构 ============

@dataclass
class ExperienceEntry:
    """一条渗透经验"""
    id: str
    timestamp: str
    target_fingerprint: dict           # {os, services, versions, open_ports}
    fingerprint_hash: str
    outcome: str                       # compromised / vulnerabilities-found / no-progress
    duration_rounds: int
    successful_paths: list[dict] = field(default_factory=list)
    failed_attempts: list[dict] = field(default_factory=list)
    skills_used: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    notes: str = ""

    def to_text(self) -> str:
        """转成用于 embedding 的扁平文本"""
        fp = self.target_fingerprint or {}
        parts = [
            f"OS: {fp.get('os', '')}",
            f"services: {', '.join(fp.get('services', []))}",
            f"versions: {', '.join(fp.get('versions', []))}",
            f"open_ports: {', '.join(str(p) for p in fp.get('open_ports', []))}",
            f"outcome: {self.outcome}",
            f"successful_paths: {len(self.successful_paths)}",
        ]
        for path in self.successful_paths[:3]:
            parts.append(
                f"  - {path.get('surface', '')} via {path.get('tool', '')}"
            )
        if self.recommendations:
            parts.append("recommendations: " + " | ".join(self.recommendations[:3]))
        return "\n".join(parts)[:2048]

    @classmethod
    def from_dict(cls, raw: dict) -> "ExperienceEntry":
        return cls(
            id=str(raw.get("id", uuid.uuid4().hex)),
            timestamp=str(raw.get("timestamp", "")),
            target_fingerprint=raw.get("target_fingerprint", {}) or {},
            fingerprint_hash=str(raw.get("fingerprint_hash", "")),
            outcome=str(raw.get("outcome", "no-progress")),
            duration_rounds=int(raw.get("duration_rounds", 0) or 0),
            successful_paths=list(raw.get("successful_paths", []) or []),
            failed_attempts=list(raw.get("failed_attempts", []) or []),
            skills_used=list(raw.get("skills_used", []) or []),
            recommendations=list(raw.get("recommendations", []) or []),
            notes=str(raw.get("notes", "")),
        )


def _fingerprint_text(fp: dict) -> str:
    """构造稳定字符串用于 hash"""
    if not fp:
        return ""
    parts = [
        f"os:{fp.get('os', '')}",
        "svc:" + ",".join(sorted(fp.get("services", []))),
        "ver:" + ",".join(sorted(fp.get("versions", []))),
        "ports:" + ",".join(sorted(str(p) for p in fp.get("open_ports", []))),
    ]
    return "|".join(parts)


def _hash_fingerprint(fp: dict) -> str:
    return hashlib.sha256(_fingerprint_text(fp).encode("utf-8")).hexdigest()[:16]


# ============ 主类 ============

class ExperienceStore:
    """经验库：写入 + 向量检索"""

    def __init__(self, skills_root: str):
        self.skills_root = skills_root
        self.root = os.path.join(skills_root, ".experience")
        self.cache_dir = os.path.join(self.root, ".cache")
        self._meta: list[dict] = []  # [{id, path, fingerprint_hash, ts}, ...]
        self._matrix = None  # np.ndarray or None
        self._encoder = None
        self._lock = threading.RLock()
        self._loaded = False

    # ----- 路径 -----
    @property
    def _meta_path(self) -> str:
        return os.path.join(self.cache_dir, "experience_meta.json")

    @property
    def _npy_path(self) -> str:
        return os.path.join(self.cache_dir, "experience.npy")

    # ----- 编码器 -----
    def _get_encoder(self):
        if self._encoder is None:
            try:
                from app.services.skill_engine.encoder import get_encoder
                self._encoder = get_encoder()
            except Exception as exc:
                LOGGER.warning("ExperienceStore 编码器加载失败: %s", exc)
                self._encoder = False
        return self._encoder if self._encoder else None

    # ----- 加载 -----
    def _ensure_loaded(self):
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            os.makedirs(self.root, exist_ok=True)
            os.makedirs(self.cache_dir, exist_ok=True)
            if os.path.isfile(self._meta_path):
                try:
                    with open(self._meta_path, "r", encoding="utf-8") as f:
                        payload = json.load(f)
                    self._meta = payload.get("entries", [])
                    if _NUMPY_OK and os.path.isfile(self._npy_path):
                        try:
                            self._matrix = np.load(self._npy_path, mmap_mode="r")
                        except Exception:
                            self._matrix = None
                except Exception as exc:
                    LOGGER.warning("ExperienceStore 加载缓存失败: %s", exc)
                    self._meta = []
                    self._matrix = None
            self._loaded = True

    # ----- 写入 -----
    def add(
        self,
        target_fingerprint: dict,
        outcome: str,
        successful_paths: Optional[list[dict]] = None,
        failed_attempts: Optional[list[dict]] = None,
        skills_used: Optional[list[str]] = None,
        recommendations: Optional[list[str]] = None,
        duration_rounds: int = 0,
        notes: str = "",
    ) -> ExperienceEntry:
        """记录一次渗透经验"""
        self._ensure_loaded()

        fp_hash = _hash_fingerprint(target_fingerprint)
        entry = ExperienceEntry(
            id=uuid.uuid4().hex[:16],
            timestamp=datetime.now(timezone.utc).isoformat(),
            target_fingerprint=target_fingerprint or {},
            fingerprint_hash=fp_hash,
            outcome=outcome or "no-progress",
            duration_rounds=int(duration_rounds or 0),
            successful_paths=list(successful_paths or []),
            failed_attempts=list(failed_attempts or []),
            skills_used=list(skills_used or []),
            recommendations=list(recommendations or []),
            notes=notes,
        )

        # 检查指纹去重：相同 fp_hash 时合并 / 覆盖
        existing_meta = next(
            (m for m in self._meta if m.get("fingerprint_hash") == fp_hash),
            None,
        )

        # 落盘 JSON
        ts = datetime.now(timezone.utc)
        out_dir = os.path.join(self.root, f"{ts.year:04d}", f"{ts.month:02d}")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{entry.id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(entry), f, ensure_ascii=False, indent=2)
        except OSError as exc:
            LOGGER.warning("ExperienceStore 写入失败 %s: %s", path, exc)
            return entry

        # 计算 embedding
        embedding = None
        encoder = self._get_encoder()
        if encoder is not None and _NUMPY_OK:
            try:
                vec = encoder.encode_one(entry.to_text())
                if vec is not None:
                    arr = np.asarray(vec, dtype=np.float32)
                    norm = float(np.linalg.norm(arr)) or 1.0
                    embedding = (arr / norm).astype(np.float32)
            except Exception as exc:
                LOGGER.warning("ExperienceStore 编码失败: %s", exc)

        # 更新元数据 + 矩阵
        with self._lock:
            new_meta_entry = {
                "id": entry.id,
                "path": path,
                "fingerprint_hash": fp_hash,
                "ts": entry.timestamp,
            }

            if existing_meta is not None:
                # 替换旧条目
                idx = self._meta.index(existing_meta)
                self._meta[idx] = new_meta_entry
                if embedding is not None and self._matrix is not None:
                    try:
                        m = np.asarray(self._matrix, dtype=np.float32).copy()
                        if idx < m.shape[0]:
                            m[idx] = embedding
                            self._matrix = m
                    except Exception:
                        pass
            else:
                self._meta.append(new_meta_entry)
                if embedding is not None:
                    if self._matrix is None or not _NUMPY_OK:
                        self._matrix = embedding.reshape(1, -1)
                    else:
                        try:
                            self._matrix = np.vstack(
                                [np.asarray(self._matrix, dtype=np.float32), embedding.reshape(1, -1)]
                            )
                        except Exception:
                            self._matrix = embedding.reshape(1, -1)

            self._persist_cache()

        return entry

    # ----- 检索 -----
    def query_similar_env(
        self,
        target_fingerprint: dict,
        top_k: int = 3,
        min_score: float = 0.5,
    ) -> list[tuple[ExperienceEntry, float]]:
        """根据当前目标指纹检索历史相似环境"""
        self._ensure_loaded()
        if not self._meta:
            return []

        # 1. 完全匹配 fingerprint_hash：最高分
        fp_hash = _hash_fingerprint(target_fingerprint)
        exact = [m for m in self._meta if m.get("fingerprint_hash") == fp_hash]

        results: list[tuple[ExperienceEntry, float]] = []
        for m in exact[:top_k]:
            entry = self._load_entry(m["path"])
            if entry:
                results.append((entry, 1.0))
        if len(results) >= top_k:
            return results

        # 2. embedding 检索补充
        encoder = self._get_encoder()
        if encoder is None or self._matrix is None or not _NUMPY_OK:
            return results

        # 构造 query text
        query_text = _fingerprint_text(target_fingerprint)
        if not query_text:
            return results
        try:
            qvec = encoder.encode_one(query_text)
            if qvec is None:
                return results
            q = np.asarray(qvec, dtype=np.float32)
            q = q / (np.linalg.norm(q) or 1.0)
            scores = np.asarray(self._matrix, dtype=np.float32) @ q
            order = np.argsort(-scores)
            seen_ids = {r[0].id for r in results}
            for idx in order:
                score = float(scores[idx])
                if score < min_score:
                    break
                if idx >= len(self._meta):
                    continue
                m = self._meta[idx]
                if m.get("id") in seen_ids:
                    continue
                entry = self._load_entry(m["path"])
                if entry:
                    results.append((entry, score))
                    if len(results) >= top_k:
                        break
        except Exception as exc:
            LOGGER.warning("ExperienceStore 查询失败: %s", exc)
        return results

    def render_for_prompt(
        self,
        hits: list[tuple[ExperienceEntry, float]],
        budget_chars: int = 1500,
    ) -> str:
        """格式化为 LLM 可注入的简洁摘要"""
        if not hits:
            return ""
        lines = ["## 历史相似环境经验"]
        used = len(lines[0])
        for entry, score in hits:
            block = self._render_entry(entry, score)
            if used + len(block) > budget_chars:
                break
            lines.append(block)
            used += len(block)
        return "\n".join(lines)

    @staticmethod
    def _render_entry(entry: ExperienceEntry, score: float) -> str:
        fp = entry.target_fingerprint or {}
        first_path = entry.successful_paths[0] if entry.successful_paths else None
        path_summary = (
            f"成功路径: {first_path.get('surface','')} via {first_path.get('tool','')}"
            if first_path else "无成功路径"
        )
        recs = "; ".join(entry.recommendations[:2]) if entry.recommendations else ""
        return (
            f"- [{entry.timestamp[:10]} sim={score:.2f}] "
            f"目标 {fp.get('os','?')} svc={','.join(fp.get('services', [])[:5])} "
            f"-> outcome={entry.outcome} (rounds={entry.duration_rounds}). "
            f"{path_summary}. "
            + (f"建议: {recs}" if recs else "")
        )

    # ----- 内部 -----
    def _load_entry(self, path: str) -> Optional[ExperienceEntry]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return ExperienceEntry.from_dict(json.load(f))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("ExperienceStore 加载 entry 失败 %s: %s", path, exc)
            return None

    def _persist_cache(self) -> None:
        try:
            with open(self._meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"model": "bge-small-zh-v1.5", "entries": self._meta},
                    f,
                    ensure_ascii=False,
                )
            if _NUMPY_OK and self._matrix is not None:
                np.save(self._npy_path, np.asarray(self._matrix, dtype=np.float32))
        except Exception as exc:
            LOGGER.warning("ExperienceStore 缓存写入失败: %s", exc)

    # ----- 管理接口（CLI 用）-----
    def list_entries(self) -> list[dict]:
        self._ensure_loaded()
        return list(self._meta)

    def delete_entry(self, entry_id: str) -> bool:
        self._ensure_loaded()
        for i, m in enumerate(list(self._meta)):
            if m.get("id") == entry_id:
                try:
                    if m.get("path") and os.path.isfile(m["path"]):
                        os.remove(m["path"])
                except OSError:
                    pass
                self._meta.pop(i)
                if _NUMPY_OK and self._matrix is not None:
                    try:
                        m_arr = np.asarray(self._matrix, dtype=np.float32)
                        if i < m_arr.shape[0]:
                            self._matrix = np.delete(m_arr, i, axis=0)
                    except Exception:
                        pass
                self._persist_cache()
                return True
        return False


__all__ = ["ExperienceStore", "ExperienceEntry"]
