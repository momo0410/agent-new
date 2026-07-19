"""Typed control-plane primitives for SDIT.

The legacy agent remains available through its existing adapters.  New code
should use these contracts for scope, actions, events, evidence and sessions
so that UI, reports and execution share the same vocabulary.
"""

from .asset_graph import AssetEdge, AssetGraph, AssetNode
from .asset_normalizer import AssetImportResult, AssetInventoryImporter, AssetNormalizer, NormalizedObservation
from .benchmark_worker import BenchmarkWorkerError, HiddenBenchmarkWorker, SubprocessBenchmarkExecutor
from .contracts import (
    ActionEnvelope,
    ActionLevel,
    AutonomyMode,
    EventEnvelope,
    EvidenceRecord,
    EvidenceStatus,
    FindingRecord,
    PolicyDecisionKind,
    ScopeContract,
)
from .choice_reason import summarize_choice_reason
from .done_gate import DoneGate, DoneGateResult
from .evaluation import ModelReplacementGate
from .event_store import EventStore, EventStoreCorruption
from .evidence_bridge import BridgeResult, EvidenceBridge
from .failure_recovery import FailureClassifier, FailureRecoveryEngine, FailureType, RecoveryPlanner
from .intelligence import (
    IntelligenceCandidate,
    IntelligenceCatalog,
    IntelligenceParser,
    IntelligenceRecord,
    IntelligenceScorer,
    IntelligenceSource,
)
from .judges import JudgeRegistry
from .local_auth import LocalSessionAuth
from .metrics import DIMENSIONS, MetricsAggregator, RuntimeHealthMonitor
from .mission_control import MissionControl
from .model_gateway import DLPScanner, ModelGateway, ModelRoute, ModelRouter, StructuredOutputError
from .observation import Observation, ObservationRecord, ObservationStore
from .planner_contracts import (
    ActionLimitController,
    AutonomyController,
    CandidateAction,
    CandidateScorer,
    PlanGraph,
    PlanValidationResult,
    PlanValidator,
    StagnationDetector,
)
from .plugin_contract import PluginManifest, PluginRegistry
from .policy_templates import CoursePolicyError, CoursePolicyRegistry, CoursePolicyTemplate
from .process_supervisor import ProcessLimits, ProcessResult, ProcessSupervisor
from .resource_budget import BudgetExceeded, BudgetLimits, BudgetManager
from .sandbox import GeneratedCodeSandbox, SandboxPolicy, SandboxResult, environment_fingerprint
from .scope_policy import PolicyDecision, ScopePolicy, ScopeTokenError
from .session_manager import SessionManager, SessionVerification
from .skill_contract import SkillKnowledgeFilter, SkillKnowledgeRecord
from .web_model import AuthSession, WebCrawlerPolicy, WebEndpoint, WebRuleEngine, WebSessionStore, WebSite
from .web_runtime import (
    BrowserAction,
    BrowserAutomationPlugin,
    BrowserNetworkRecord,
    BrowserTrace,
    ScopedWebCrawler,
    WebCrawlResult,
    WebFetch,
    WebRoleComparator,
)

__all__ = [
    "ActionEnvelope",
    "summarize_choice_reason",
    "ActionLevel",
    "AssetEdge",
    "AssetGraph",
    "AssetNode",
    "AssetNormalizer",
    "NormalizedObservation",
    "AssetImportResult",
    "AssetInventoryImporter",
    "BenchmarkWorkerError",
    "HiddenBenchmarkWorker",
    "SubprocessBenchmarkExecutor",
    "DoneGate",
    "DoneGateResult",
    "EvidenceRecord",
    "EvidenceStatus",
    "EventEnvelope",
    "EventStore",
    "EventStoreCorruption",
    "BridgeResult",
    "EvidenceBridge",
    "FailureClassifier",
    "FailureRecoveryEngine",
    "FailureType",
    "RecoveryPlanner",
    "FindingRecord",
    "AutonomyMode",
    "PolicyDecisionKind",
    "PolicyDecision",
    "LocalSessionAuth",
    "MissionControl",
    "DLPScanner",
    "ModelGateway",
    "ModelRoute",
    "ModelRouter",
    "StructuredOutputError",
    "Observation",
    "ObservationRecord",
    "ObservationStore",
    "DIMENSIONS",
    "MetricsAggregator",
    "RuntimeHealthMonitor",
    "IntelligenceSource",
    "IntelligenceRecord",
    "IntelligenceCandidate",
    "IntelligenceParser",
    "IntelligenceScorer",
    "IntelligenceCatalog",
    "ModelReplacementGate",
    "ScopeContract",
    "ScopePolicy",
    "ScopeTokenError",
    "GeneratedCodeSandbox",
    "SandboxPolicy",
    "SandboxResult",
    "environment_fingerprint",
    "SessionManager",
    "SessionVerification",
    "SkillKnowledgeFilter",
    "SkillKnowledgeRecord",
    "WebCrawlerPolicy",
    "WebEndpoint",
    "WebSite",
    "AuthSession",
    "WebSessionStore",
    "WebRuleEngine",
    "WebFetch",
    "WebCrawlResult",
    "ScopedWebCrawler",
    "WebRoleComparator",
    "BrowserAction",
    "BrowserNetworkRecord",
    "BrowserTrace",
    "BrowserAutomationPlugin",
    "JudgeRegistry",
    "CandidateAction",
    "ActionLimitController",
    "CandidateScorer",
    "AutonomyController",
    "PlanGraph",
    "PlanValidator",
    "PlanValidationResult",
    "StagnationDetector",
    "PluginManifest",
    "PluginRegistry",
    "BudgetLimits",
    "BudgetManager",
    "BudgetExceeded",
    "ProcessLimits",
    "ProcessResult",
    "ProcessSupervisor",
    "CoursePolicyRegistry",
    "CoursePolicyTemplate",
    "CoursePolicyError",
]
