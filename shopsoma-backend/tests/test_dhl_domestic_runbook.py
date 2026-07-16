import re
from pathlib import Path


def _runbook_path() -> Path:
    test_file = Path(__file__).resolve()
    for parent in test_file.parents:
        candidate = parent / "docs" / "integrations" / "dhl.md"
        if candidate.is_file():
            return candidate
    raise AssertionError("could not locate docs/integrations/dhl.md from the test tree")


def _runbook() -> str:
    return _runbook_path().read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def test_runbook_has_authoritative_operational_sections() -> None:
    headings = {
        match.group(1).strip().lower()
        for match in re.finditer(r"^#{2,3}\s+(.+?)\s*$", _runbook(), re.MULTILINE)
    }
    required = {
        "authoritative topology and responsibility",
        "data ownership matrix",
        "state and actor authority",
        "feature gates, rollout, and rollback",
        "sandbox setup, secrets, and evidence",
        "official dhl facts and domestic stop gate",
        "customer milestones",
        "sandbox acceptance matrix",
        "stop and rollback triggers",
        "evidence privacy and retention",
        "superseded instructions",
    }
    assert required <= headings


def test_runbook_enforces_hub_only_dhl_topology() -> None:
    text = _normalized(_runbook())
    assert (
        "vendor -> independent inbound -> shopsoma hub -> dhl last mile -> nigerian customer"
        in text
    )
    assert "receives, reconciles, qcs, packs, measures, and seals" in text
    assert (
        "dhl never receives a vendor-origin quote, pickup, shipment, or handoff" in text
    )
    assert "independent inbound leg" in text
    assert "dhl outbound quote" in text


def test_runbook_records_timing_authority_and_safe_rollout_contract() -> None:
    text = _normalized(_runbook())
    for phrase in (
        "30-minute quote and payment-initialization window",
        "t0+45",
        "atomic stock reacquisition",
        "idempotent void or refund",
        "no prepayment stock decrement",
        "no prepayment vendor work",
        "verified dhl handoff",
        "dhl_domestic_workflow_enabled",
        "dhl_domestic_quote_enforcement_enabled",
        "dhl_domestic_provider_calls_enabled",
        "separate domestic checkout gate",
        "in-flight orders remain operable",
        "never rewrites v2 orders into an unsafe legacy flow",
    ):
        assert phrase in text


def test_runbook_uses_official_sources_and_fails_closed_on_domestic_assumptions() -> (
    None
):
    text = _normalized(_runbook())
    for value in (
        "https://developer.dhl.com/api-reference/dhl-express-mydhl-api",
        "https://express.api.dhl.com/mydhlapi/test",
        "https://express.api.dhl.com/mydhlapi",
        "500 calls/day",
        "basic auth",
        "dhl express customer account",
        "unverified assumptions",
        "written dhl/account confirmation or sandbox evidence",
        "production is prohibited in phase 2a and phase 2b",
    ):
        assert value in text
    assert "product n is confirmed" not in text
    assert "product n remains unverified" in text


def test_runbook_defines_honest_milestones_and_private_evidence() -> None:
    text = _normalized(_runbook())
    for milestone in (
        "payment confirmed",
        "vendor preparing",
        "moving to shopsoma",
        "received by shopsoma",
        "quality check",
        "packed / ready",
        "dhl collected",
        "in transit",
        "out for delivery",
        "delivered",
        "exception",
    ):
        assert milestone in text
    for phrase in (
        "slowest non-cancelled cohort",
        "partial receipt",
        "private object storage",
        "short-lived signed urls",
        "retention is subject to legal approval",
        "append-only corrections",
        "no public evidence",
        "no real customer or payment canary",
    ):
        assert phrase in text


def test_runbook_does_not_reactivate_superseded_vendor_origin_work() -> None:
    text = _normalized(_runbook())
    assert "vendor-site mobile qc and direct dhl pickup are superseded" in text
    forbidden_active_instructions = (
        r"dhl (?:must|should|will) pick up (?:directly )?from (?:the )?vendor",
        r"schedule (?:a )?dhl pickup (?:at|from) (?:the )?vendor",
        r"perform mobile qc at (?:the )?vendor",
        r"create (?:a )?dhl shipment from (?:the )?vendor origin",
    )
    for pattern in forbidden_active_instructions:
        assert re.search(pattern, text) is None, pattern
