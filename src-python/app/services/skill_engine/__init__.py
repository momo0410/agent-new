from .skill_md_parser import SkillMdParser
from .skill_loader import SkillLoader, LoadedSkill
from .skill_matcher import SkillMatcher
from .skill_generator import SkillGenerator
from .quality_gate import SkillQualityGate, GateResult, GateSummary
from .lifecycle_manager import LifecycleManager, SkillLifecycleEntry
from .failure_skill_generator import FailureSkillGenerator
from .encoder import get_encoder, DEFAULT_MODEL as DEFAULT_EMBEDDING_MODEL

# Embedding 索引可选
try:
    from .skill_embedding_index import SkillEmbeddingIndex, EmbeddingMatch
    _EMBEDDING_EXPORTS = ["SkillEmbeddingIndex", "EmbeddingMatch"]
except ImportError:
    SkillEmbeddingIndex = None  # type: ignore
    EmbeddingMatch = None  # type: ignore
    _EMBEDDING_EXPORTS = []

__all__ = [
    "SkillMdParser",
    "SkillLoader",
    "LoadedSkill",
    "SkillMatcher",
    "SkillGenerator",
    "SkillQualityGate",
    "GateResult",
    "GateSummary",
    "LifecycleManager",
    "SkillLifecycleEntry",
    "FailureSkillGenerator",
    "get_encoder",
    "DEFAULT_EMBEDDING_MODEL",
] + _EMBEDDING_EXPORTS
