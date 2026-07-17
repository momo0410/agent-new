"""Typed control-plane primitives for SDIT.

The legacy agent remains available through its existing adapters.  New code
should use these contracts for scope, actions, events, evidence and sessions
so that UI, reports and execution share the same vocabulary.
"""

from .asset_graph import AssetEdge, AssetGraph, AssetNode
from .contracts import (
    ActionEnvelope,
    ActionLevel,
    EventEnvelope,
    EvidenceRecord,
    EvidenceStatus,
    FindingRecord,
    ScopeContract,
)
from .done_gate import DoneGate, DoneGateResult
from .event_store import EventStore, EventStoreCorruption
from .local_auth import LocalSessionAuth
from .scope_policy import PolicyDecision, ScopePolicy, ScopeTokenError
from .session_manager import SessionManager, SessionVerification

__all__ = [
    "ActionEnvelope",
    "ActionLevel",
    "AssetEdge",
    "AssetGraph",
    "AssetNode",
    "DoneGate",
    "DoneGateResult",
    "EvidenceRecord",
    "EvidenceStatus",
    "EventEnvelope",
    "EventStore",
    "EventStoreCorruption",
    "FindingRecord",
    "PolicyDecision",
    "LocalSessionAuth",
    "ScopeContract",
    "ScopePolicy",
    "ScopeTokenError",
    "SessionManager",
    "SessionVerification",
]
