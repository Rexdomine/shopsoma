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


def test_runbook_limits_vendor_transition_authority() -> None:
    text = _normalized(_runbook())
    assert "vendor may only acknowledge, start preparing, or mark ready" in text
    assert "only shopsoma operations or the server sla policy may place a block" in text
    assert "only shopsoma operations may resolve blocked to preparing or ready" in text
    assert (
        "vendor may acknowledge, prepare, declare readiness, or report a block"
        not in text
    )
    assert (
        re.search(r"vendor may[^.]{0,100}(?:report|place|set)[^.]{0,40}block", text)
        is None
    )


def test_runbook_defines_numbered_delivery_phases_and_ordered_activation() -> None:
    text = _normalized(_runbook())
    phases = (
        "1. phase 2a — contracts, persistence, payment, hub operations, mock adapter, and ui; no live provider calls",
        "2. phase 2b — restricted sandbox connectivity and evidence; no production traffic or customer payment",
        "3. phase 2c — shadow, non-payment quote uat only",
        "4. phase 3 — booking, labels, shopsoma-hub collection handoff, and recovery",
        "5. phase 4 — carrier tracking and operational exceptions",
        "6. phase 5 — controlled payment-bearing customer pilot",
        "7. phase 6 — broader production activation",
    )
    positions = [text.index(phase) for phase in phases]
    assert positions == sorted(positions)

    activation_steps = (
        "1. keep every gate false",
        "2. enable the internal workflow with a fake provider",
        "3. establish restricted sandbox connectivity",
        "4. enable provider calls only for the restricted sandbox cohort",
        "5. run shadow quotes",
        "6. keep domestic checkout false",
        "7. phase 5 is the first customer canary",
    )
    positions = [text.index(step) for step in activation_steps]
    assert positions == sorted(positions)


def test_runbook_defines_reverse_order_rollback() -> None:
    text = _normalized(_runbook())
    rollback_steps = (
        "1. disable new domestic checkout first",
        "2. disable the provider-call gate second",
        "3. preserve workflow, reads, and operations for in-flight v2 orders",
        "4. never route v2 orders into legacy unsafe creation",
        "5. reconcile provider-side objects",
        "6. only then pause the workflow when no in-flight order depends on it",
    )
    positions = [text.index(step) for step in rollback_steps]
    assert positions == sorted(positions)


def test_runbook_records_event_replay_package_and_return_contracts() -> None:
    text = _normalized(_runbook())
    for phrase in (
        "external events are unique by `(source, event_id)`",
        "return the matching durably persisted transition result",
        "audited package version, composition, and active seal",
        "shopsoma hub command",
        "verified dhl return evidence",
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


def test_runbook_distinguishes_code_gates_from_sandbox_operational_control() -> None:
    text = _normalized(_runbook())

    assert "capability evaluator does not distinguish sandbox from production" in text
    assert "sandbox isolation is an external deployment/secret-policy control" in text
    assert "phase 2b adds the sandbox-only provider factory" in text
