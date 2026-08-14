"""Deterministic, positive historical order workflow classification."""

from dataclasses import dataclass
import hashlib


class ClassificationConflict(RuntimeError):
    """An immutable prior classification differs from the rerun candidate."""


@dataclass(frozen=True)
class ClassificationEvidence:
    compatibility_release_id: str | None = None
    deployment_identity: str | None = None
    bridge_evidence_reference: str | None = None


@dataclass(frozen=True)
class ClassificationCandidate:
    order_id: str
    cohort: str
    policy_version: str
    access_mode: str
    evidence_kind: str
    evidence_reference: str
    notes_hash: str


def classify_historical_order(
    order_id: str, evidence: ClassificationEvidence
) -> ClassificationCandidate:
    """Classify from positive evidence; ambiguity is explicitly quarantined."""

    positive_reference = evidence.bridge_evidence_reference
    if (
        not positive_reference
        and evidence.compatibility_release_id
        and evidence.deployment_identity
    ):
        positive_reference = (
            f"{evidence.compatibility_release_id}:{evidence.deployment_identity}"
        )
    if positive_reference:
        values = (
            "legacy_pre_bridge",
            "legacy_pre_bridge_v1",
            "authenticated",
            "positive_release_or_bridge_evidence",
            positive_reference,
        )
    else:
        values = (
            "legacy_ambiguous_quarantined",
            "legacy_quarantine_v1",
            "legacy_quarantined",
            "migration_ambiguity_quarantine",
            "historical-evidence-unresolved",
        )
    notes_hash = hashlib.sha256("|".join((str(order_id), *values)).encode()).hexdigest()
    return ClassificationCandidate(str(order_id), *values, notes_hash)


def reconcile_candidate(
    existing: ClassificationCandidate, candidate: ClassificationCandidate
) -> ClassificationCandidate:
    """Permit exact replay and abort any changed immutable candidate."""

    if existing != candidate:
        raise ClassificationConflict("changed workflow classification candidate")
    return existing
