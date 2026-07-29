"""Public security contracts for identity, policy, secrets, and audit."""

from rath.security.audit import (
    AuditEvent,
    AuditKind,
    AuditSink,
    InMemoryAuditSink,
    StructuredAuditSink,
)
from rath.security.context import (
    Principal,
    PrincipalKind,
    Provenance,
    SecurityContext,
    TrustLevel,
)
from rath.security.policy import (
    Action,
    ApprovalRequiredError,
    AuthorizationError,
    DenyAllPolicy,
    LocalTrustedPolicy,
    PolicyConstraints,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyEvaluationError,
    ResourceRef,
    authorize,
)
from rath.security.secrets import ResolvedSecret, SecretRef, SecretResolver

__all__ = [
    "Action",
    "ApprovalRequiredError",
    "AuditEvent",
    "AuditKind",
    "AuditSink",
    "AuthorizationError",
    "authorize",
    "DenyAllPolicy",
    "InMemoryAuditSink",
    "LocalTrustedPolicy",
    "PolicyConstraints",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyEngine",
    "PolicyEvaluationError",
    "Principal",
    "PrincipalKind",
    "Provenance",
    "ResolvedSecret",
    "ResourceRef",
    "SecretRef",
    "SecretResolver",
    "SecurityContext",
    "StructuredAuditSink",
    "TrustLevel",
]
