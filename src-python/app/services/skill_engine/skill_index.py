"""Skill 向量索引 — 基于 TF-IDF 的轻量级语义检索。

不依赖外部 embedding API，使用 TF-IDF + cosine similarity 实现。
同一查询词在单次渗透中只检索一次（去重由调用方负责）。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from .skill_loader import LoadedSkill


@dataclass
class VectorMatch:
    """向量检索结果。"""
    skill: LoadedSkill
    score: float  # cosine similarity (0-1)
    match_reason: str


class SkillIndex:
    """基于 TF-IDF 的 skill 向量索引。

    使用流程:
    1. 构造: index = SkillIndex(skills)
    2. 检索: results = index.search("apache 2.4.49 exploit", limit=5, threshold=0.6)
    """

    def __init__(self, skills: list[LoadedSkill]):
        self._skills = skills
        self._documents: list[list[str]] = []  # 每个 skill 的 token 列表
        self._idf: dict[str, float] = {}  # IDF 值
        self._tfidf_vectors: list[dict[str, float]] = []  # 每个 skill 的 TF-IDF 向量
        self._built = False

    def _tokenize(self, text: str) -> list[str]:
        """分词：英文按词，中文按字，转小写。"""
        if not text:
            return []
        tokens = []
        # 英文单词
        for word in re.findall(r'[a-zA-Z0-9_-]+', text.lower()):
            if len(word) >= 2:
                tokens.append(word)
        # 中文字符（逐字）
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                tokens.append(ch)
        return tokens

    def _build_document_text(self, skill: LoadedSkill) -> str:
        """从 skill 构建用于索引的文档文本。"""
        parts = [skill.name, skill.description]
        if skill.tags:
            parts.extend(skill.tags)
        if skill.domain:
            parts.append(skill.domain)
        if skill.subdomain:
            parts.append(skill.subdomain)
        if skill.cve:
            parts.append(skill.cve)
        # 从 md_data 提取关键 section
        if skill.md_data and skill.md_data.sections:
            sections = skill.md_data.sections
            if sections.principle:
                parts.append(sections.principle[:500])
            if sections.detection_fingerprint:
                parts.append(sections.detection_fingerprint[:300])
            if sections.generalization:
                parts.append(sections.generalization[:300])
        return " ".join(parts)

    def build(self):
        """构建 TF-IDF 索引。"""
        if self._built:
            return

        # 1. 构建文档
        for skill in self._skills:
            text = self._build_document_text(skill)
            tokens = self._tokenize(text)
            self._documents.append(tokens)

        # 2. 计算 IDF
        doc_count = len(self._documents)
        if doc_count == 0:
            self._built = True
            return

        df: dict[str, int] = {}  # 文档频率
        for tokens in self._documents:
            unique_tokens = set(tokens)
            for token in unique_tokens:
                df[token] = df.get(token, 0) + 1

        for token, freq in df.items():
            self._idf[token] = math.log((doc_count + 1) / (freq + 1)) + 1  # smoothed IDF

        # 3. 计算每个文档的 TF-IDF 向量
        for tokens in self._documents:
            tf = Counter(tokens)
            total = len(tokens) if tokens else 1
            vector = {}
            for token, count in tf.items():
                tfidf = (count / total) * self._idf.get(token, 1.0)
                vector[token] = tfidf
            self._tfidf_vectors.append(vector)

        self._built = True

    def _cosine_similarity(self, vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
        """计算两个稀疏向量的余弦相似度。"""
        if not vec_a or not vec_b:
            return 0.0

        # 内积
        dot_product = 0.0
        for token, weight in vec_a.items():
            if token in vec_b:
                dot_product += weight * vec_b[token]

        if dot_product == 0:
            return 0.0

        # 模长
        norm_a = math.sqrt(sum(w * w for w in vec_a.values()))
        norm_b = math.sqrt(sum(w * w for w in vec_b.values()))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    def _query_to_vector(self, query: str) -> dict[str, float]:
        """将查询文本转换为 TF-IDF 向量。"""
        tokens = self._tokenize(query)
        tf = Counter(tokens)
        total = len(tokens) if tokens else 1
        vector = {}
        for token, count in tf.items():
            tfidf = (count / total) * self._idf.get(token, 1.0)
            vector[token] = tfidf
        return vector

    def search(
        self,
        query: str,
        limit: int = 5,
        threshold: float = 0.0,
    ) -> list[VectorMatch]:
        """语义检索 skill。

        Args:
            query: 查询文本
            limit: 返回最多几个结果
            threshold: 最低相似度阈值 (0-1)

        Returns:
            匹配结果列表，按相似度降序
        """
        if not self._built:
            self.build()

        if not self._skills or not query.strip():
            return []

        query_vec = self._query_to_vector(query)
        if not query_vec:
            return []

        results: list[VectorMatch] = []
        for idx, doc_vec in enumerate(self._tfidf_vectors):
            sim = self._cosine_similarity(query_vec, doc_vec)
            if sim >= threshold:
                results.append(VectorMatch(
                    skill=self._skills[idx],
                    score=sim,
                    match_reason=f"vector_cosine={sim:.3f}",
                ))

        results.sort(key=lambda x: -x.score)
        return results[:limit]

    def search_with_fallback(
        self,
        query: str,
        limit: int = 5,
        vector_threshold: float = 0.6,
    ) -> list[VectorMatch]:
        """带兜底的检索：先按阈值检索，结果不足时降低阈值。"""
        results = self.search(query, limit=limit, threshold=vector_threshold)
        if len(results) >= limit:
            return results

        # 降低阈值兜底
        fallback = self.search(query, limit=limit, threshold=0.3)
        # 合并去重
        seen = {id(r.skill) for r in results}
        for r in fallback:
            if id(r.skill) not in seen:
                results.append(r)
                seen.add(id(r.skill))
            if len(results) >= limit:
                break

        return results
