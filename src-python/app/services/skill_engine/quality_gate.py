"""
SkillQualityGate — 自动生成 skill 的质量门控

对 SkillGenerator 输出的 SKILL.md 文件执行 4 道独立检查：
    1. _check_frontmatter   — YAML frontmatter 必填字段完整
    2. _check_v2_sections   — 五段式章节覆盖（Principle / Detection Fingerprint /
                              Workflow / Failure Modes / Generalization）
    3. _check_duplicate     — 与已有 active skill 字符串相似度去重 (P0 字符串版本，
                              P1 升级到 embedding)
    4. _check_grounding     — CVE / payload 必须能在 state evidence 中找到
                              (P0 暂仅打印警告，不强制；P2 启用)

任一检查失败即拒绝。被拒 skill 不落盘，原因写入 rejected_reasons 字典供
ReflectionReport 引用（P2 阶段）。

设计原则：
- 故障安全 — 检查内部异常时记录警告但默认放行，避免门控本身阻塞流程
- 零依赖 — P0 不引入 fastembed；用 difflib.SequenceMatcher 做字符串相似度
- 可配置 — 阈值通过构造参数注入，便于单测调参
"""
from __future__ import annotations

import difflib
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

# ----- 常量 -----

REQUIRED_FRONTMATTER_KEYS = ("name", "description", "domain", "subdomain", "version")
V2_REQUIRED_SECTIONS = (
    "Principle",
    "Detection Fingerprint",
    "Workflow",
    "Failure Modes",
    "Generalization",
)

# 字符串相似度阈值：description 余弦风格相似度 > 此值视为重复
DEFAULT_DEDUPE_THRESHOLD = 0.85
# 不强制的灰度阈值
GROUNDING_WARN_THRESHOLD = 0.5


@dataclass
class GateResult:
    """单文件门控结果"""
    path: str
    accepted: bool
    rejected_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class GateSummary:
    """整批门控摘要"""
    accepted: list[str] = field(default_factory=list)
    rejected: list[GateResult] = field(default_factory=list)
    warned: list[GateResult] = field(default_factory=list)

    @property
    def stats(self) -> dict:
        return {
            "accepted": len(self.accepted),
            "rejected": len(self.rejected),
            "warned": len(self.warned),
        }


# ----- 工具函数 -----

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter（简单版，避免引入 pyyaml 依赖）"""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_block = parts[1]
    body = parts[2]
    meta: dict = {}
    for line in fm_block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip("'\"")
    return meta, body


def _extract_sections(body: str) -> set[str]:
    """从 Markdown body 抽取 ## 二级标题集合"""
    sections = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            title = stripped[3:].strip()
            sections.add(title)
    return sections


def _extract_cves(text: str) -> set[str]:
    return set(re.findall(r"CVE-\d{4}-\d{4,7}", text, flags=re.IGNORECASE))


def _normalize_text(text: str) -> str:
    """为相似度比较归一化文本"""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


# ----- 主类 -----

class SkillQualityGate:
    """对自动生成的 SKILL.md 做质量门控

    用法：
        gate = SkillQualityGate(existing_skills_iter=lambda: loader.load_all(),
                                state_evidence=state.build_evidence_index())
        summary = gate.filter([path1, path2, ...])
        for accepted_path in summary.accepted:
            ...   # 已通过
    """

    def __init__(
        self,
        existing_skills_provider: Optional[callable] = None,
        state_evidence: Optional[dict] = None,
        dedupe_threshold: float = DEFAULT_DEDUPE_THRESHOLD,
        enforce_grounding: bool = False,
    ):
        """
        Args:
            existing_skills_provider: 调用返回 list[LoadedSkill] 的工厂；用于去重比对
            state_evidence: 形如 {"cves": {...}, "payloads": {...}, "services": {...}}
            dedupe_threshold: description 相似度阈值
            enforce_grounding: True 时找不到证据直接拒；False 时仅警告（P0 默认 False）
        """
        self._existing_provider = existing_skills_provider
        self._state_evidence = state_evidence or {}
        self._dedupe_threshold = dedupe_threshold
        self._enforce_grounding = enforce_grounding
        self._existing_descriptions: Optional[list[tuple[str, str]]] = None  # [(name, desc), ...]

    # ----- 公共 API -----

    def filter(self, skill_paths: Iterable[str]) -> GateSummary:
        summary = GateSummary()
        for path in skill_paths:
            result = self.check(path)
            if result.accepted:
                summary.accepted.append(path)
                if result.warnings:
                    summary.warned.append(result)
            else:
                summary.rejected.append(result)
        return summary

    def check(self, path: str) -> GateResult:
        result = GateResult(path=path, accepted=False)
        text = _read_text(path)
        if not text:
            result.rejected_reasons.append("文件为空或无法读取")
            return result

        meta, body = _split_frontmatter(text)

        if not self._check_frontmatter(meta):
            missing = [k for k in REQUIRED_FRONTMATTER_KEYS if k not in meta]
            result.rejected_reasons.append(f"frontmatter 缺字段: {','.join(missing)}")
        if not self._check_v2_sections(body):
            present = _extract_sections(body)
            missing_sec = [s for s in V2_REQUIRED_SECTIONS if s not in present]
            result.rejected_reasons.append(f"五段式章节缺失: {','.join(missing_sec)}")

        dup_name, dup_score = self._check_duplicate(meta, body, exclude_path=path)
        if dup_name and dup_score >= self._dedupe_threshold:
            result.rejected_reasons.append(
                f"与已有 skill '{dup_name}' 语义重复 (similarity={dup_score:.2f})"
            )

        grounding_ok, grounding_msg = self._check_grounding(body)
        if not grounding_ok:
            if self._enforce_grounding:
                result.rejected_reasons.append(f"grounding 失败: {grounding_msg}")
            else:
                result.warnings.append(f"grounding 警告: {grounding_msg}")

        if not result.rejected_reasons:
            result.accepted = True
        return result

    # ----- 4 道独立检查 -----

    @staticmethod
    def _check_frontmatter(meta: dict) -> bool:
        for k in REQUIRED_FRONTMATTER_KEYS:
            v = str(meta.get(k, "") or "").strip()
            if not v:
                return False
        return True

    @staticmethod
    def _check_v2_sections(body: str) -> bool:
        present = _extract_sections(body)
        return all(sec in present for sec in V2_REQUIRED_SECTIONS)

    def _check_duplicate(
        self, meta: dict, body: str, exclude_path: Optional[str] = None
    ) -> tuple[Optional[str], float]:
        """返回 (相似 skill 名, 相似度)。无现有 skill 时返回 (None, 0)。"""
        try:
            if self._existing_descriptions is None:
                self._existing_descriptions = self._collect_existing_descriptions(exclude_path)
        except Exception:
            self._existing_descriptions = []
            return None, 0.0

        cand_text = _normalize_text(meta.get("description", "") + " " + body[:500])
        if not cand_text or len(cand_text) < 20:
            return None, 0.0

        best_name: Optional[str] = None
        best_score = 0.0
        for name, existing_text in self._existing_descriptions:
            if not existing_text:
                continue
            score = difflib.SequenceMatcher(None, cand_text, existing_text).ratio()
            if score > best_score:
                best_score = score
                best_name = name
        return best_name, best_score

    def _check_grounding(self, body: str) -> tuple[bool, str]:
        """检查 SKILL.md 中引用的 CVE 是否在 state 证据中出现过"""
        cves_in_skill = _extract_cves(body)
        if not cves_in_skill:
            return True, ""
        evidence_cves = set(c.upper() for c in self._state_evidence.get("cves", set()))
        if not evidence_cves:
            return False, f"skill 引用 {len(cves_in_skill)} 个 CVE 但 state 无任何 CVE 证据"
        cves_norm = set(c.upper() for c in cves_in_skill)
        unfounded = cves_norm - evidence_cves
        if unfounded:
            return False, f"未在 state 中找到证据的 CVE: {','.join(sorted(unfounded))[:200]}"
        return True, ""

    # ----- 内部辅助 -----

    def _collect_existing_descriptions(self, exclude_path: Optional[str]) -> list[tuple[str, str]]:
        """从 existing_skills_provider 收集 (name, normalized_text) 列表"""
        out: list[tuple[str, str]] = []
        if not self._existing_provider:
            return out
        try:
            existing = self._existing_provider()
        except Exception:
            return out
        for skill in existing or []:
            try:
                skill_path = getattr(skill, "md_path", "") or getattr(skill, "json_path", "")
                if exclude_path and skill_path and os.path.abspath(skill_path) == os.path.abspath(exclude_path):
                    continue
                name = getattr(skill, "name", "") or ""
                desc = getattr(skill, "description", "") or ""
                md_data = getattr(skill, "md_data", None)
                body_snippet = ""
                if md_data and getattr(md_data, "sections", None):
                    try:
                        body_snippet = " ".join(
                            (sec.body or "")[:200] for sec in md_data.sections[:3]
                        )
                    except Exception:
                        body_snippet = ""
                normalized = _normalize_text(desc + " " + body_snippet)
                if normalized:
                    out.append((name, normalized))
            except Exception:
                continue
        return out


__all__ = [
    "SkillQualityGate",
    "GateResult",
    "GateSummary",
    "REQUIRED_FRONTMATTER_KEYS",
    "V2_REQUIRED_SECTIONS",
]
