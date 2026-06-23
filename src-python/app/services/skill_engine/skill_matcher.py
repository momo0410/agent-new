"""
Skill 匹配器 — 根据用户请求/上下文匹配相关 skill

匹配策略（P1: 混合检索）：
1. 服务指纹直配：SERVICE_SKILL_MAP 命中给极强 boost
2. 规则评分：tags / name / description / domain / keyword→domain
3. TF-IDF 检索：本地 TF-IDF + 余弦相似度
4. Embedding 检索：FastEmbed bge-small-zh 语义检索
5. RRF（Reciprocal Rank Fusion）融合 2/3/4 的排名，加上 1 的强约束 boost

返回匹配的 skill 列表，供 Agent 注入 SKILL.md 内容到 LLM prompt
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

from .skill_loader import LoadedSkill, SkillLoader
from .skill_index import SkillIndex, VectorMatch

# Embedding 索引可选；导入失败时只走 TF-IDF
try:
    from .skill_embedding_index import SkillEmbeddingIndex, EmbeddingMatch
    _EMBEDDING_AVAILABLE = True
except ImportError:
    SkillEmbeddingIndex = None  # type: ignore
    EmbeddingMatch = None  # type: ignore
    _EMBEDDING_AVAILABLE = False


@dataclass
class SkillMatch:
    skill: LoadedSkill
    score: float
    match_reason: str


class SkillMatcher:
    """根据请求匹配相关 skill"""

    # 服务指纹 → skill name 直接映射（当检测到这些服务时优先匹配对应 skill）
    SERVICE_SKILL_MAP: dict[str, str] = {
        "vsftpd": "exploit-vsftpd-backdoor",
        "samba": "exploit-samba-usermap",
        "smbd": "exploit-samba-usermap",
        "unrealircd": "exploit-unrealircd-backdoor",
        "distccd": "exploit-distcc-command-exec",
        "distcc": "exploit-distcc-command-exec",
        "java-rmi": "exploit-java-rmi",
        "rmiregistry": "exploit-java-rmi",
        "bindshell": "exploit-generic-bindshell",
        "backdoor": "exploit-generic-bindshell",
        "postgresql": "exploit-postgres-weak-creds",
        "postgres": "exploit-postgres-weak-creds",
        "tomcat": "exploit-tomcat-default-creds",
        "mysql": "exploit-mysql-weak-creds",
        "vnc": "exploit-vnc-noauth",
        "nfs": "exploit-nfs-privesc",
        "php": "exploit-php-cgi",
        "openssh": "exploit-ssh-bruteforce",
        "ssh": "exploit-ssh-bruteforce",
        "telnet": "exploit-telnet-bruteforce",
        "proftpd": "exploit-proftpd-modcopy",
        "drb": "exploit-druby-rce",
        "ruby": "exploit-druby-rce",
        "rlogin": "exploit-rlogin-rsh",
        "ircd": "exploit-irc-backdoor",
        "irc": "exploit-irc-backdoor",
        "nfsd": "exploit-nfs-privesc",
        "mountd": "exploit-nfs-privesc",
        "rsh": "exploit-rlogin-rsh",
        "rexec": "exploit-rlogin-rsh",
        "apache": "exploit-apache-http",
        "httpd": "exploit-apache-http",
    }

    # 预定义关键词 → domain/subdomain 映射
    KEYWORD_DOMAIN_MAP = {
        # 渗透测试相关
        "pentest": "penetration-testing",
        "渗透": "penetration-testing",
        "nmap": "penetration-testing",
        "exploit": "penetration-testing",
        "漏洞利用": "penetration-testing",
        # 取证相关
        "forensics": "digital-forensics",
        "取证": "digital-forensics",
        "disk image": "digital-forensics",
        "内存": "digital-forensics",
        "volatility": "digital-forensics",
        # 恶意软件
        "malware": "malware-analysis",
        "恶意": "malware-analysis",
        "virus": "malware-analysis",
        "apt": "malware-analysis",
        # 威胁情报
        "threat": "threat-intelligence",
        "威胁": "threat-intelligence",
        "ioc": "threat-intelligence",
        "ttp": "threat-intelligence",
        # 云安全
        "cloud": "cloud-security",
        "aws": "cloud-security",
        "azure": "cloud-security",
        "kubernetes": "container-security",
        "docker": "container-security",
        # Web安全
        "web": "web-application-security",
        "sql": "web-application-security",
        "xss": "web-application-security",
        "sqlmap": "web-application-security",
        # 网络安全
        "network": "network-security",
        "pcap": "network-security",
        "流量": "network-security",
        "dns": "network-security",
    }

    def __init__(self, loader: SkillLoader):
        self.loader = loader
        self._skills_cache: Optional[list[LoadedSkill]] = None
        self._vector_index: Optional[SkillIndex] = None
        self._embedding_index = None  # type: Optional[SkillEmbeddingIndex]
        self._hybrid_enabled = True  # P1: 默认启用混合检索

    def _get_skills(self) -> list[LoadedSkill]:
        if self._skills_cache is None:
            self._skills_cache = self.loader.load_all()
        return self._skills_cache

    def _get_vector_index(self) -> SkillIndex:
        """延迟构建 TF-IDF 向量索引（首次调用时构建）。"""
        if self._vector_index is None:
            skills = self._get_skills()
            self._vector_index = SkillIndex(skills)
            self._vector_index.build()
        return self._vector_index

    def _get_embedding_index(self):
        """延迟构建 embedding 索引；失败/不可用时返回 None"""
        if not _EMBEDDING_AVAILABLE:
            return None
        if self._embedding_index is None:
            try:
                skills = self._get_skills()
                cache_dir = os.path.join(self.loader.skills_root, ".cache", "embeddings")
                index = SkillEmbeddingIndex(skills, cache_dir=cache_dir)
                if index.build():
                    self._embedding_index = index
                else:
                    self._embedding_index = False  # 标记构建失败，避免反复尝试
            except Exception:
                self._embedding_index = False
        return self._embedding_index if self._embedding_index else None

    def match(
        self,
        query: str,
        limit: int = 5,
        domain: Optional[str] = None,
        subdomain: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[SkillMatch]:
        """
        根据查询匹配 skill

        Args:
            query: 用户请求文本
            limit: 返回最多几个
            domain: 限定领域
            subdomain: 限定子领域
            tags: 限定标签

        Returns:
            匹配结果列表，按分数降序
        """
        skills = self._get_skills()
        query_lower = query.lower()
        query_words = set(re.findall(r"\w+", query_lower))

        # 服务指纹直匹配：检查 query 中是否包含已知服务名
        service_boost: dict[str, float] = {}  # skill_name -> boost score
        for service_key, skill_name in self.SERVICE_SKILL_MAP.items():
            if service_key in query_lower:
                service_boost[skill_name] = max(service_boost.get(skill_name, 0), 15.0)

        candidates: list[SkillMatch] = []

        for skill in skills:
            score = 0.0
            reasons = []

            # 服务指纹直匹配加分
            if skill.name in service_boost:
                score += service_boost[skill.name]
                reasons.append(f"service-skill match: {skill.name}")

            if domain and skill.domain != domain:
                continue
            if subdomain and skill.subdomain != subdomain:
                continue
            if tags:
                if not any(t in skill.tags for t in tags):
                    continue

            name_lower = skill.name.lower()
            desc_lower = skill.description.lower()

            if query_lower in name_lower:
                score += 10.0
                reasons.append(f"name match: {query_lower}")

            if query_lower in desc_lower:
                score += 5.0
                reasons.append(f"desc match: {query_lower}")

            for word in query_words:
                if word in name_lower:
                    score += 3.0
                    reasons.append(f"word in name: {word}")
                if word in desc_lower:
                    score += 1.0
                    reasons.append(f"word in desc: {word}")

            for tag in skill.tags:
                if not isinstance(tag, str):
                    continue
                tag_lower = tag.lower()
                if tag_lower in query_lower:
                    score += 4.0
                    reasons.append(f"tag match: {tag}")
                for word in query_words:
                    if word == tag_lower:
                        score += 5.0
                        reasons.append(f"tag exact: {tag}")

            for kw, mapped_domain in self.KEYWORD_DOMAIN_MAP.items():
                if kw in query_lower and skill.subdomain == mapped_domain:
                    score += 6.0
                    reasons.append(f"keyword→domain: {kw}→{mapped_domain}")

            if skill.domain and skill.domain in query_lower:
                score += 4.0
                reasons.append(f"domain match: {skill.domain}")
            if skill.subdomain and skill.subdomain in query_lower:
                score += 5.0
                reasons.append(f"subdomain match: {skill.subdomain}")

            if score > 0:
                candidates.append(SkillMatch(
                    skill=skill,
                    score=score,
                    match_reason="; ".join(reasons[:3]),
                ))

        candidates.sort(key=lambda x: -x.score)

        # ── P1: 混合检索（RRF 融合 TF-IDF + Embedding）──
        if self._hybrid_enabled:
            try:
                candidates = self._fuse_with_hybrid_search(
                    query=query,
                    rule_candidates=candidates,
                    service_boost=service_boost,
                    limit=limit,
                    domain=domain,
                    subdomain=subdomain,
                    tags=tags,
                )
            except Exception as exc:  # noqa: BLE001
                # 故障安全：任何失败回退到原 TF-IDF 兜底
                import logging
                logging.getLogger(__name__).warning(
                    "hybrid 检索失败，回退 TF-IDF 兜底: %s", exc
                )
                if len(candidates) < limit:
                    try:
                        index = self._get_vector_index()
                        vector_results = index.search_with_fallback(
                            query, limit=limit, vector_threshold=0.6
                        )
                        seen_skills = {id(c.skill) for c in candidates}
                        for vr in vector_results:
                            if id(vr.skill) in seen_skills:
                                continue
                            normalized_score = vr.score * 20.0
                            if normalized_score < 1.0:
                                continue
                            candidates.append(SkillMatch(
                                skill=vr.skill,
                                score=normalized_score,
                                match_reason=vr.match_reason,
                            ))
                            seen_skills.add(id(vr.skill))
                        candidates.sort(key=lambda x: -x.score)
                    except Exception:
                        pass

        return candidates[:limit]

    # ----- P1: RRF 混合检索辅助 -----

    def _fuse_with_hybrid_search(
        self,
        query: str,
        rule_candidates: list["SkillMatch"],
        service_boost: dict[str, float],
        limit: int,
        domain: Optional[str],
        subdomain: Optional[str],
        tags: Optional[list[str]],
    ) -> list["SkillMatch"]:
        """用 RRF 融合规则评分 + TF-IDF + Embedding 三路检索

        Reciprocal Rank Fusion: score(d) = sum(1/(K+rank_i)), K=60 (业界常用)
        在 RRF 分数之上叠加 SERVICE_SKILL_MAP 强约束 boost。
        """
        K = 60
        TOP_K_PER_SOURCE = 20

        # 1. 规则评分排名
        rule_ranks: dict[str, int] = {}
        for rank, m in enumerate(rule_candidates):
            rule_ranks.setdefault(m.skill.name, rank)

        skill_by_name = {s.name: s for s in self._get_skills()}

        # 2. TF-IDF 排名
        tfidf_ranks: dict[str, int] = {}
        try:
            tfidf_index = self._get_vector_index()
            tfidf_results = tfidf_index.search_with_fallback(
                query, limit=TOP_K_PER_SOURCE, vector_threshold=0.3
            )
            for rank, vr in enumerate(tfidf_results):
                tfidf_ranks.setdefault(vr.skill.name, rank)
        except Exception:
            pass

        # 3. Embedding 排名
        emb_ranks: dict[str, int] = {}
        emb_index = self._get_embedding_index()
        if emb_index is not None:
            try:
                emb_results = emb_index.search(query, top_k=TOP_K_PER_SOURCE, min_score=0.25)
                for rank, em in enumerate(emb_results):
                    emb_ranks.setdefault(em.skill.name, rank)
            except Exception:
                pass

        # 4. RRF 融合分数
        all_names = set(rule_ranks) | set(tfidf_ranks) | set(emb_ranks)
        rrf_scores: dict[str, float] = {}
        sources: dict[str, list[str]] = {}
        for name in all_names:
            score = 0.0
            srcs = []
            if name in rule_ranks:
                score += 1.0 / (K + rule_ranks[name])
                srcs.append(f"rule#{rule_ranks[name]+1}")
            if name in tfidf_ranks:
                score += 1.0 / (K + tfidf_ranks[name])
                srcs.append(f"tfidf#{tfidf_ranks[name]+1}")
            if name in emb_ranks:
                score += 1.0 / (K + emb_ranks[name])
                srcs.append(f"emb#{emb_ranks[name]+1}")
            rrf_scores[name] = score
            sources[name] = srcs

        # 5. service_boost 强约束（在 RRF 之上加显著权重）
        for skill_name, boost in service_boost.items():
            rrf_scores[skill_name] = rrf_scores.get(skill_name, 0.0) + 0.5

        # 6. 应用过滤器（domain / subdomain / tags），保证与规则路一致
        filtered: list[tuple[str, float]] = []
        for name, rrf in rrf_scores.items():
            skill = skill_by_name.get(name)
            if not skill:
                continue
            if domain and skill.domain != domain:
                continue
            if subdomain and skill.subdomain != subdomain:
                continue
            if tags and not any(t in (skill.tags or []) for t in tags):
                continue
            filtered.append((name, rrf))

        if not filtered:
            # 全部被过滤；回退到原 rule_candidates
            return rule_candidates

        # 7. 排序、归一化到 0-20 分（与现有量纲一致）
        filtered.sort(key=lambda x: -x[1])
        top = filtered[: max(limit * 2, limit)]
        max_score = top[0][1] if top else 1.0

        # 保留原 rule_candidates 中的 reason 信息（便于调试）
        rule_reason_by_name = {m.skill.name: m.match_reason for m in rule_candidates}

        merged: list[SkillMatch] = []
        for name, rrf in top:
            skill = skill_by_name.get(name)
            if not skill:
                continue
            normalized = 20.0 * rrf / max_score if max_score > 0 else 0.0
            reason_parts = sources.get(name, [])
            if name in service_boost:
                reason_parts.append("service-skill match")
            base_reason = rule_reason_by_name.get(name, "")
            full_reason = ", ".join(reason_parts) + (f"; {base_reason}" if base_reason else "")
            merged.append(SkillMatch(
                skill=skill,
                score=normalized,
                match_reason=full_reason[:200],
            ))
        return merged

    def get_skill_by_name(self, name: str) -> Optional[LoadedSkill]:
        """精确匹配名称"""
        for skill in self._get_skills():
            if skill.name == name:
                return skill
        return None

    def format_knowledge_for_prompt(
        self,
        matches: list[SkillMatch],
        include_sections: Optional[list[str]] = None,
        phase: str = "planning",
    ) -> str:
        """
        将匹配的 skill 知识格式化为可注入 LLM prompt 的文本

        Args:
            matches: 匹配结果
            include_sections: 要包含的节，默认自动分层
            phase: 当前阶段
                "planning"  — 规划阶段: 注入原理+检测指纹+迁移规则（教学为主）
                "execution" — 执行阶段: 注入 workflow + failure_modes
                "recovery"  — 失败恢复: 重点注入 failure_modes（回退策略）

        Returns:
            格式化的知识文本
        """
        if not matches:
            return ""

        # ── 反过拟合开场白：让模型把 skill 当参考而非命令 ─────────────
        preamble = [
            "## 可用技能知识（参考用，非强制脚本）",
            "",
            "**重要提示**：以下技能知识是基于历史经验整理的**参考方案**，"
            "并非必须照搬的固定命令序列。请遵循以下使用原则：",
            "",
            "- **先理解再行动**：重点看 *Principle*（原理）和 *Detection Fingerprint*"
            "（指纹），先判断是否真的适用于当前目标",
            "- **可以调整**：若当前情况与 skill 描述不完全匹配，请基于 *Principle* 推演新方案，"
            "在响应中说明你为什么偏离 skill 提供的 workflow",
            "- **可以跳过**：若指纹不符（例如版本不对、端口不开），请明确说明跳过此 skill 的原因，"
            "不要硬套",
            "- **重点参考迁移规则**：*Generalization* 章节提供同类漏洞的通用方法论，"
            "对当前目标的指导价值往往大于具体的 *Workflow*",
            "- **失败时查 Failure Modes**：一次尝试失败不等于此 skill 不适用，先查表再决定回退",
            "",
            "在执行任何 skill 中的命令前，请在你的规划中给出一段简短的适用性判断："
            "（1）当前目标与 skill 指纹的匹配度；（2）是否需要按 Principle 调整 workflow；"
            "（3）首要尝试方法与备选方法。",
            "",
            "---",
            "",
        ]
        lines = list(preamble)

        # ── 按阶段自动选择注入优先级 ─────────────────────────
        planning_first = ["principle", "detection_fingerprint", "generalization",
                          "when_to_use", "key_concepts", "prerequisites"]
        execution_first = ["workflow", "detection_fingerprint", "failure_modes",
                           "key_concepts", "principle"]

        if include_sections:
            section_order = include_sections
        elif phase == "recovery":
            section_order = ["failure_modes", "workflow", "detection_fingerprint",
                             "key_concepts"]
        elif phase == "execution":
            section_order = execution_first
        else:
            section_order = planning_first

        for i, match in enumerate(matches, 1):
            skill = match.skill
            lines.append(f"### 技能 {i}: {skill.name}")
            lines.append(f"描述: {skill.description}")
            lines.append(f"领域: {skill.domain}/{skill.subdomain}")
            if skill.cve:
                lines.append(f"CVE: {skill.cve}")
            lines.append(f"匹配分数: {match.score:.1f}")
            lines.append("")

            if skill.md_data:
                sections = skill.md_data.sections
                injected = set()
                max_chars_per_skill = 3000
                used = 0

                for section_key in section_order:
                    if used >= max_chars_per_skill:
                        break

                    section_value = getattr(sections, section_key, None)
                    if not section_value or not section_value.strip():
                        continue

                    section_label = {
                        "principle": "▸ 漏洞原理（理解为什么）",
                        "detection_fingerprint": "▸ 检测指纹（何时触发此 skill）",
                        "failure_modes": "▸ 失败回退（这一步不行怎么办）",
                        "generalization": "▸ 迁移规则（今后遇到同类题怎么做）",
                        "when_to_use": "▸ 何时使用",
                        "prerequisites": "▸ 前提条件",
                        "workflow": "▸ 工作流程（按此执行）",
                        "key_concepts": "▸ 关键信息速查",
                        "tools_and_systems": "▸ 所需工具",
                        "common_scenarios": "▸ 常见场景",
                        "output_format": "▸ 输出格式",
                    }.get(section_key, f"▸ {section_key}")

                    if section_key in ("workflow", "failure_modes", "principle", "generalization"):
                        limit = 2000
                    else:
                        limit = 600

                    text = section_value[:limit]
                    lines.append(f"**{section_label}:**")
                    lines.append(text)
                    lines.append("")
                    used += len(text)
                    injected.add(section_key)

                # 其他自定义 section 兜底注入（空间剩余时）
                if sections.other and used < max_chars_per_skill:
                    for section_name, section_content in sections.other.items():
                        if section_content and len(section_content.strip()) > 10:
                            if section_name not in injected:
                                remaining = max_chars_per_skill - used
                                if remaining < 100:
                                    break
                                lines.append(f"**{section_name}:**")
                                lines.append(section_content[:remaining])
                                lines.append("")
                                used += len(section_content[:remaining])

            lines.append("---")
            lines.append("")

        return "\n".join(lines)
