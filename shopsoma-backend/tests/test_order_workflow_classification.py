"""Milestone 2 explicit order workflow classification contracts."""

import pytest


def test_missing_bridge_records_never_classifies_legacy_order() -> None:
    from app.services.orders.workflow_classification import (
        ClassificationEvidence,
        classify_historical_order,
    )

    candidate = classify_historical_order(
        order_id="00000000-0000-0000-0000-000000000001",
        evidence=ClassificationEvidence(),
    )
    assert candidate.cohort == "legacy_ambiguous_quarantined"
    assert candidate.evidence_kind == "migration_ambiguity_quarantine"


def test_positive_release_evidence_classifies_legacy_order() -> None:
    from app.services.orders.workflow_classification import (
        ClassificationEvidence,
        classify_historical_order,
    )

    candidate = classify_historical_order(
        order_id="00000000-0000-0000-0000-000000000001",
        evidence=ClassificationEvidence(
            compatibility_release_id="release-1",
            deployment_identity="deploy-1",
        ),
    )
    assert candidate.cohort == "legacy_pre_bridge"
    assert candidate.policy_version == "legacy_pre_bridge_v1"
    assert candidate.access_mode == "authenticated"


def test_changed_candidate_aborts_but_exact_rerun_is_idempotent() -> None:
    from app.services.orders.workflow_classification import (
        ClassificationConflict,
        ClassificationEvidence,
        classify_historical_order,
        reconcile_candidate,
    )

    quarantine = classify_historical_order("order-1", ClassificationEvidence())
    assert reconcile_candidate(quarantine, quarantine) == quarantine
    legacy = classify_historical_order(
        "order-1",
        ClassificationEvidence("release-1", "deploy-1"),
    )
    with pytest.raises(ClassificationConflict):
        reconcile_candidate(quarantine, legacy)


def test_false_default_configuration_assigns_no_enforced_cohort(monkeypatch) -> None:
    monkeypatch.delenv("DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", raising=False)
    monkeypatch.delenv("DOMESTIC_CHECKOUT_COHORT_ALLOWLIST", raising=False)
    monkeypatch.delenv("DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", raising=False)
    from app.core.config import Settings

    settings = Settings()
    assert settings.DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED is False
    assert settings.DOMESTIC_CHECKOUT_COHORT_ALLOWLIST == ""
    assert settings.DOMESTIC_CHECKOUT_COHORT_PERCENTAGE == 0
    assert settings.domestic_checkout_cohort_ids == frozenset()
