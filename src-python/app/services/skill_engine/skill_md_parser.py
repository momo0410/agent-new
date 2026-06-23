"""
SKILL.md 解析器 — 提取 YAML frontmatter 元数据 + Markdown 正文结构

支持 Anthropic Cybersecurity Skills 格式:
    ---
    name: xxx
    description: xxx
    domain: xxx
    subdomain: xxx
    tags: [...]
    version: '1.0'
    nist_csf: [...]
    ---
    # Title
    ## When to Use
    ## Prerequisites
    ## Workflow
    ## Key Concepts
    ## Output Format
"""

import re
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class SkillMdMeta:
    name: str = ""
    description: str = ""
    domain: str = ""
    subdomain: str = ""
    tags: list[str] = field(default_factory=list)
    version: str = "1.0"
    author: str = ""
    license: str = ""
    nist_csf: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SkillMdSections:
    when_to_use: str = ""
    prerequisites: str = ""
    workflow: str = ""
    key_concepts: str = ""
    tools_and_systems: str = ""
    common_scenarios: str = ""
    output_format: str = ""
    # ── 教学型 skill 新增章节 ───────────────────────────
    principle: str = ""           # 漏洞原理（CVE 成因、内部机制）
    detection_fingerprint: str = ""  # 检测指纹（何时该触发此 skill）
    failure_modes: str = ""       # 失败回退（什么失败了、下一步做什么）
    generalization: str = ""      # 迁移规则（遇到同类漏洞怎么做）
    other: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedSkillMd:
    meta: SkillMdMeta
    sections: SkillMdSections
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)
    raw_body: str = ""


_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL
)

_SECTION_HEADER_RE = re.compile(
    r"^##\s+(.+)$", re.MULTILINE
)

_KNOWN_SECTIONS = {
    "when to use": "when_to_use",
    "when to apply": "when_to_use",
    "prerequisites": "prerequisites",
    "workflow": "workflow",
    "exploitation steps (execute these commands)": "workflow",
    "exploitation steps": "workflow",
    "key concepts": "key_concepts",
    "tools & systems": "tools_and_systems",
    "tools and systems": "tools_and_systems",
    "common scenarios": "common_scenarios",
    "output format": "output_format",
    "verification": "output_format",
    "summary": "key_concepts",
    # ── 教学型 skill 新增章节别名（中英文） ───────────────
    "principle": "principle",
    "原理": "principle",
    "漏洞原理": "principle",
    "vulnerability principle": "principle",
    "detection fingerprint": "detection_fingerprint",
    "fingerprint": "detection_fingerprint",
    "检测指纹": "detection_fingerprint",
    "trigger": "detection_fingerprint",
    "trigger condition": "detection_fingerprint",
    "failure modes": "failure_modes",
    "failure mode": "failure_modes",
    "fallback": "failure_modes",
    "失败回退": "failure_modes",
    "失败处理": "failure_modes",
    "generalization": "generalization",
    "generalize": "generalization",
    "migration": "generalization",
    "迁移规则": "generalization",
    "举一反三": "generalization",
    "类似漏洞": "generalization",
}


class SkillMdParser:
    """解析 SKILL.md 文件，提取 frontmatter 元数据和正文各节"""

    @staticmethod
    def parse(content: str) -> ParsedSkillMd:
        frontmatter_dict: dict[str, Any] = {}
        body = content

        m = _FRONTMATTER_RE.match(content)
        if m:
            raw_yaml = m.group(1)
            try:
                frontmatter_dict = yaml.safe_load(raw_yaml) or {}
            except yaml.YAMLError:
                frontmatter_dict = {}
            body = content[m.end():]

        meta = SkillMdParser._build_meta(frontmatter_dict)
        sections = SkillMdParser._parse_sections(body)

        return ParsedSkillMd(
            meta=meta,
            sections=sections,
            raw_frontmatter=frontmatter_dict,
            raw_body=body,
        )

    @staticmethod
    def parse_file(filepath: str) -> ParsedSkillMd:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return SkillMdParser.parse(content)

    @staticmethod
    def _build_meta(fm: dict[str, Any]) -> SkillMdMeta:
        tags = fm.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",")]

        nist = fm.get("nist_csf", [])
        if isinstance(nist, str):
            nist = [n.strip() for n in nist.split(",")]

        known_keys = {
            "name", "description", "domain", "subdomain",
            "tags", "version", "author", "license", "nist_csf",
        }
        extra = {k: v for k, v in fm.items() if k not in known_keys}

        return SkillMdMeta(
            name=fm.get("name", ""),
            description=fm.get("description", ""),
            domain=fm.get("domain", ""),
            subdomain=fm.get("subdomain", ""),
            tags=tags,
            version=str(fm.get("version", "1.0")),
            author=fm.get("author", ""),
            license=fm.get("license", ""),
            nist_csf=nist,
            extra=extra,
        )

    @staticmethod
    def _parse_sections(body: str) -> SkillMdSections:
        sections = SkillMdSections()
        headers = list(_SECTION_HEADER_RE.finditer(body))

        if not headers:
            sections.other["body"] = body.strip()
            return sections

        for i, match in enumerate(headers):
            title = match.group(1).strip().lower()
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(body)
            content = body[start:end].strip()

            field_name = _KNOWN_SECTIONS.get(title)
            if field_name:
                setattr(sections, field_name, content)
            else:
                sections.other[title] = content

        return sections
