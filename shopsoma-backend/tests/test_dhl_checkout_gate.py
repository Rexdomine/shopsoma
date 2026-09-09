"""DHL checkout bridge rollout safety contracts."""

import uuid

from app.api.v1.orders import _domestic_checkout_is_enforced
from app.core.config import settings


def test_domestic_checkout_gate_is_inert_in_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DHL_ENVIRONMENT", "production")

    assert not _domestic_checkout_is_enforced(
        customer_id=uuid.uuid4(), country="Nigeria", currency="NGN"
    )


def test_production_application_cannot_use_sandbox_default(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "DHL_ENVIRONMENT", "sandbox")

    assert not _domestic_checkout_is_enforced(
        customer_id=uuid.uuid4(), country="Nigeria", currency="NGN"
    )


def test_domestic_checkout_gate_can_target_sandbox_cohort(monkeypatch) -> None:
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "DHL_ENVIRONMENT", "sandbox")

    assert _domestic_checkout_is_enforced(
        customer_id=uuid.uuid4(), country="Nigeria", currency="NGN"
    )