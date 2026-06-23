"""
SkillLoader — 统一加载器

发现 skills/ 目录下的两类资源：
  - skill.json (规则引擎，声明式步骤调度)
  - SKILL.md  (AI调度，知识文档供LLM上下文)

合并策略：
  - 同目录下 json + md 共存 → mode="hybrid"
  - 仅 json → mode="pipeline"
  - 仅 md  → mode="knowledge"

加载结果中：
  - json 内容提供 steps/parameters/depends_on (硬控)
  - md 内容提供 when_to_use/prerequisites/workflow/key_concepts (AI上下文)
  - hybrid 模式下 json 的 knowledge_file 字段可显式指向 SKILL.md
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .skill_md_parser import SkillMdParser, ParsedSkillMd


@dataclass
class LoadedSkill:
    name: str
    description: str
    mode: str  # "pipeline" | "knowledge" | "hybrid"
    category: str = ""
    status: str = "active"
    source: str = ""

    json_data: Optional[dict[str, Any]] = None
    md_data: Optional[ParsedSkillMd] = None

    dir_path: str = ""
    json_path: str = ""
    md_path: str = ""

    steps: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    domain: str = ""
    subdomain: str = ""
    nist_csf: list[str] = field(default_factory=list)

    knowledge_file: str = ""

    cve: str = ""          # 关联 CVE 编号（如 CVE-2011-2523）
    severity: str = ""     # 严重程度（critical / high / medium / low）

    def to_api_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "mode": self.mode,
            "category": self.category,
            "status": self.status,
            "source": self.source,
            "tags": self.tags,
            "domain": self.domain,
            "subdomain": self.subdomain,
            "dir_path": self.dir_path,
        }
        if self.mode in ("pipeline", "hybrid"):
            result["has_pipeline"] = True
            result["steps_count"] = len(self.steps)
        else:
            result["has_pipeline"] = False
            result["steps_count"] = 0

        if self.mode in ("knowledge", "hybrid"):
            result["has_knowledge"] = True
            if self.md_data:
                result["knowledge_sections"] = list(self.md_data.sections.other.keys())
                known = []
                if self.md_data.sections.when_to_use:
                    known.append("when_to_use")
                if self.md_data.sections.prerequisites:
                    known.append("prerequisites")
                if self.md_data.sections.workflow:
                    known.append("workflow")
                if self.md_data.sections.key_concepts:
                    known.append("key_concepts")
                result["knowledge_sections"] = known + list(self.md_data.sections.other.keys())
        else:
            result["has_knowledge"] = False
            result["knowledge_sections"] = []

        return result


class SkillLoader:
    """统一加载 skills/ 目录"""

    def __init__(self, skills_root: str):
        self.skills_root = skills_root

    def load_all(self) -> list[LoadedSkill]:
        skills: list[LoadedSkill] = []
        if not os.path.isdir(self.skills_root):
            return skills

        for category_dir in sorted(os.listdir(self.skills_root)):
            cat_path = os.path.join(self.skills_root, category_dir)
            if not os.path.isdir(cat_path):
                continue
            if category_dir.startswith("."):
                continue

            for entry in sorted(os.listdir(cat_path)):
                entry_path = os.path.join(cat_path, entry)
                skill = self._load_entry(entry_path, category_dir)
                if skill:
                    if isinstance(skill, list):
                        skills.extend(skill)
                    else:
                        skills.append(skill)

        return skills

    def _load_entry(self, entry_path: str, category: str) -> Optional[LoadedSkill | list[LoadedSkill]]:
        if os.path.isdir(entry_path):
            return self._load_skill_dir(entry_path, category)

        if os.path.isfile(entry_path) and entry_path.endswith(".json"):
            return self._load_json_file(entry_path, category)

        if os.path.isfile(entry_path) and entry_path.endswith(".md"):
            return self._load_md_file(entry_path, category)

        return None

    def _load_skill_dir(self, dir_path: str, category: str) -> list[LoadedSkill]:
        """加载目录下的所有 .md 和 .json 文件为独立 skill"""
        skills: list[LoadedSkill] = []
        json_path = ""
        md_files: list[str] = []

        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            if fname == "SKILL.md" and os.path.isfile(fpath):
                md_files.insert(0, fpath)  # SKILL.md 优先
            elif fname.endswith(".md") and os.path.isfile(fpath):
                md_files.append(fpath)
            elif fname.endswith(".json") and os.path.isfile(fpath):
                json_path = fpath

        # 如果目录下有 SKILL.md，按传统方式加载为单个 skill
        if md_files and os.path.basename(md_files[0]) == "SKILL.md":
            json_data = None
            md_data = None
            if json_path:
                json_data = self._read_json(json_path)
            md_data = SkillMdParser.parse_file(md_files[0])
            if json_data and md_data:
                mode = "hybrid"
            elif json_data:
                mode = "pipeline"
            else:
                mode = "knowledge"
            skill = self._merge(json_data, md_data, mode, dir_path, json_path, md_files[0], category)
            skills.append(skill)
            # 剩余 .md 文件作为独立 skill
            for md_path in md_files[1:]:
                s = self._load_md_file(md_path, category)
                if s:
                    skills.append(s)
        else:
            # 没有 SKILL.md，每个 .md 文件都是独立 skill
            for md_path in md_files:
                s = self._load_md_file(md_path, category)
                if s:
                    skills.append(s)

        return skills

    def _load_json_file(self, json_path: str, category: str) -> LoadedSkill:
        json_data = self._read_json(json_path)
        if not json_data:
            return None

        dir_path = os.path.dirname(json_path)
        knowledge_file = json_data.get("knowledge_file", "")
        md_path = ""
        md_data = None

        if knowledge_file:
            candidate = os.path.join(dir_path, knowledge_file)
            if os.path.isfile(candidate):
                md_path = candidate
                md_data = SkillMdParser.parse_file(candidate)

        if md_data:
            mode = "hybrid"
        else:
            mode = "pipeline"

        return self._merge(json_data, md_data, mode, dir_path, json_path, md_path, category)

    def _load_md_file(self, md_path: str, category: str) -> LoadedSkill:
        md_data = SkillMdParser.parse_file(md_path)
        dir_path = os.path.dirname(md_path)
        return self._merge(None, md_data, "knowledge", dir_path, "", md_path, category)

    @staticmethod
    def _merge(
        json_data: Optional[dict],
        md_data: Optional[ParsedSkillMd],
        mode: str,
        dir_path: str,
        json_path: str,
        md_path: str,
        category: str,
    ) -> LoadedSkill:
        name = ""
        description = ""
        status = "active"
        source = category
        steps = []
        parameters = []
        tags = []
        domain = ""
        subdomain = ""
        nist_csf = []
        knowledge_file = ""

        if json_data:
            name = json_data.get("name", "")
            description = json_data.get("description", "")
            status = json_data.get("status", "active")
            source = json_data.get("source", category)
            steps = json_data.get("steps", [])
            parameters = json_data.get("parameters", [])
            tags = json_data.get("tags", [])
            knowledge_file = json_data.get("knowledge_file", "")

        if md_data:
            if not name:
                name = md_data.meta.name
            if not description:
                description = md_data.meta.description
            if not domain:
                domain = md_data.meta.domain
            if not subdomain:
                subdomain = md_data.meta.subdomain
            if md_data.meta.tags:
                for t in md_data.meta.tags:
                    if t not in tags:
                        tags.append(t)
            if md_data.meta.nist_csf:
                nist_csf = md_data.meta.nist_csf

        # 从 frontmatter extra 提取 cve / severity（新模板字段）
        cve = ""
        severity = ""
        if md_data and md_data.meta.extra:
            cve = str(md_data.meta.extra.get("cve", "") or "")
            severity = str(md_data.meta.extra.get("severity", "") or "")

        return LoadedSkill(
            name=name or os.path.basename(dir_path),
            description=description,
            mode=mode,
            category=json_data.get("category", category) if json_data else category,
            status=status,
            source=source,
            json_data=json_data,
            md_data=md_data,
            dir_path=dir_path,
            json_path=json_path,
            md_path=md_path,
            steps=steps,
            parameters=parameters,
            tags=tags,
            domain=domain,
            subdomain=subdomain,
            nist_csf=nist_csf,
            knowledge_file=knowledge_file,
            cve=cve,
            severity=severity,
        )

    @staticmethod
    def _read_json(path: str) -> Optional[dict]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
