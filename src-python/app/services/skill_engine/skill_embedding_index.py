"""SkillEmbeddingIndex — 用 FastEmbed 给所有 skill 建嵌入索引

存储：
    skills/.cache/embeddings/skills.npy        (N, 512) float32, mmap 加载
    skills/.cache/embeddings/skills_meta.json  [{name, path_hash, sha256}, ...]

构建策略：
- 首次启动：全量构建
- 增量：根据 (skill name, sha256(text)) 集合 diff 决定哪些条目需要重算

查询：
- 给定 query 文本，encode -> cosine 全量扫描 -> 返回 top_k

设计取舍：
- 不引入 FAISS：754 skills × 512 dim 完全够 numpy 直接算
- mmap：避免每次启动重读
- 索引版本号：在 meta 加 'embedding_model'，模型升级时自动重建
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from dataclasses import dataclass
from typing import Iterable, Optional

try:
    import numpy as np
    _NUMPY_OK = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_OK = False

from .encoder import get_encoder, DEFAULT_MODEL, EMBED_DIM
from .skill_loader import LoadedSkill

LOGGER = logging.getLogger(__name__)


@dataclass
class EmbeddingMatch:
    skill: LoadedSkill
    score: float  # cosine similarity, 0..1


def _skill_to_text(skill: LoadedSkill) -> str:
    """把 skill 转成用于 embedding 的文本（与 SkillIndex 的 tfidf 文档构成对齐）"""
    parts = [skill.name or "", skill.description or "", " ".join(skill.tags or [])]
    if skill.domain:
        parts.append(skill.domain)
    if skill.subdomain:
        parts.append(skill.subdomain)
    if skill.cve:
        parts.append(skill.cve)
    if skill.md_data:
        sections = skill.md_data.sections
        for attr in ("principle", "detection_fingerprint", "generalization"):
            v = getattr(sections, attr, "") or ""
            if v:
                parts.append(v[:500])
    text = " ".join(p for p in parts if p)
    return text[:4096]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


class SkillEmbeddingIndex:
    """对所有 skill 的 embedding 索引"""

    def __init__(
        self,
        skills: list[LoadedSkill],
        cache_dir: str,
        model_name: str = DEFAULT_MODEL,
    ):
        self.skills = skills
        self.cache_dir = cache_dir
        self.model_name = model_name
        self.encoder = get_encoder(model_name)
        self._matrix = None  # np.ndarray (N, dim) or None
        self._meta: list[dict] = []  # [{"name", "sha256"}, ...]
        self._skill_lookup: dict[str, LoadedSkill] = {}
        self._lock = threading.RLock()
        self._built = False

    # ----- 路径 -----
    @property
    def _npy_path(self) -> str:
        return os.path.join(self.cache_dir, "skills.npy")

    @property
    def _meta_path(self) -> str:
        return os.path.join(self.cache_dir, "skills_meta.json")

    # ----- 构建 -----
    def build(self, force_rebuild: bool = False) -> bool:
        """构建/更新索引。返回是否成功（含降级）"""
        if not _NUMPY_OK:
            LOGGER.warning("numpy 不可用，跳过 embedding 索引")
            return False
        if not self.encoder.available:
            LOGGER.warning("FastEmbed 不可用，跳过 embedding 索引")
            return False

        with self._lock:
            os.makedirs(self.cache_dir, exist_ok=True)
            self._build_skill_lookup()

            # 构建当前 skill 集合的 (name -> sha256) 映射
            current_meta: list[dict] = []
            for skill in self.skills:
                text = _skill_to_text(skill)
                if not text:
                    continue
                current_meta.append({"name": skill.name, "sha256": _sha256(text)})

            # 尝试加载现有缓存
            cached_meta: list[dict] = []
            cached_matrix = None
            cached_model = None
            if (not force_rebuild
                    and os.path.isfile(self._npy_path)
                    and os.path.isfile(self._meta_path)):
                try:
                    with open(self._meta_path, "r", encoding="utf-8") as f:
                        meta_payload = json.load(f)
                    cached_meta = meta_payload.get("entries", [])
                    cached_model = meta_payload.get("model")
                    cached_matrix = np.load(self._npy_path, mmap_mode="r")
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("加载 embedding 缓存失败，将重建: %s", exc)
                    cached_meta = []
                    cached_matrix = None

            # 缓存命中条件：模型一致 + 条目集合一致
            if (cached_matrix is not None
                    and cached_model == self.model_name
                    and len(cached_meta) == len(current_meta)
                    and all(c["name"] == m["name"] and c["sha256"] == m["sha256"]
                            for c, m in zip(cached_meta, current_meta))):
                self._matrix = np.asarray(cached_matrix, dtype=np.float32)
                self._meta = cached_meta
                self._built = True
                LOGGER.info("embedding 索引缓存命中: %d 条", len(self._meta))
                return True

            # 增量更新：复用未变的条目，仅 encode 变化部分
            old_lookup: dict[str, tuple[int, str]] = {}
            for idx, entry in enumerate(cached_meta):
                old_lookup[entry["name"]] = (idx, entry["sha256"])

            need_encode_indices: list[int] = []
            need_encode_texts: list[str] = []
            for new_idx, entry in enumerate(current_meta):
                old = old_lookup.get(entry["name"])
                if old is None or old[1] != entry["sha256"]:
                    skill = self._skill_lookup.get(entry["name"])
                    if skill:
                        need_encode_indices.append(new_idx)
                        need_encode_texts.append(_skill_to_text(skill))

            # 调用编码器
            new_matrix = np.zeros((len(current_meta), EMBED_DIM), dtype=np.float32)
            # 复用旧向量
            if cached_matrix is not None:
                for new_idx, entry in enumerate(current_meta):
                    old = old_lookup.get(entry["name"])
                    if old is not None and old[1] == entry["sha256"]:
                        try:
                            new_matrix[new_idx] = cached_matrix[old[0]]
                        except (IndexError, ValueError):
                            need_encode_indices.append(new_idx)
                            skill = self._skill_lookup.get(entry["name"])
                            if skill:
                                need_encode_texts.append(_skill_to_text(skill))

            if need_encode_texts:
                LOGGER.info("embedding 增量编码 %d / %d 条", len(need_encode_texts), len(current_meta))
                vecs = self.encoder.encode_batch(need_encode_texts)
                if vecs is None:
                    LOGGER.warning("embedding 编码失败，索引不可用")
                    return False
                for idx, vec in zip(need_encode_indices, vecs):
                    arr = np.asarray(vec, dtype=np.float32)
                    norm = np.linalg.norm(arr) or 1.0
                    new_matrix[idx] = arr / norm

            # 全部正规化（旧向量已经是归一化的，新的也归一化过；冗余处理无害）
            norms = np.linalg.norm(new_matrix, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1.0, norms)
            new_matrix = new_matrix / norms

            self._matrix = new_matrix.astype(np.float32)
            self._meta = current_meta
            self._built = True

            # 保存
            try:
                np.save(self._npy_path, self._matrix)
                with open(self._meta_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {"model": self.model_name, "dim": EMBED_DIM, "entries": current_meta},
                        f,
                        ensure_ascii=False,
                    )
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("保存 embedding 缓存失败: %s", exc)

            return True

    def _build_skill_lookup(self) -> None:
        self._skill_lookup = {s.name: s for s in self.skills if s.name}

    # ----- 查询 -----
    def search(self, query: str, top_k: int = 20, min_score: float = 0.3) -> list[EmbeddingMatch]:
        if not self._built:
            return []
        if self._matrix is None or not self._meta:
            return []
        if not self.encoder.available:
            return []
        try:
            vec = self.encoder.encode_one(query)
        except Exception:
            return []
        if vec is None:
            return []
        q = np.asarray(vec, dtype=np.float32)
        q_norm = np.linalg.norm(q) or 1.0
        q = q / q_norm
        scores = self._matrix @ q  # (N,)
        # top_k
        top = np.argsort(-scores)[: top_k]
        out: list[EmbeddingMatch] = []
        for idx in top:
            score = float(scores[idx])
            if score < min_score:
                continue
            entry = self._meta[idx]
            skill = self._skill_lookup.get(entry["name"])
            if skill is None:
                continue
            out.append(EmbeddingMatch(skill=skill, score=score))
        return out

    @property
    def available(self) -> bool:
        return self._built and self._matrix is not None


__all__ = ["SkillEmbeddingIndex", "EmbeddingMatch"]
