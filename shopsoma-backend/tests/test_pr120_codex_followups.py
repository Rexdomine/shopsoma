from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sys

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).parents[1]
DEPLOY_PATH = ROOT / "run_checkout_prerequisite_deploy.py"
PAYMENTS_PATH = ROOT / "app" / "api" / "v1" / "payments.py"
RESERVATIONS_PATH = ROOT / "app" / "services" / "checkout" / "reservations.py"
ESTIMATES_PATH = ROOT / "app" / "services" / "checkout" / "estimates.py"
BRIDGE_PATH = ROOT / "app" / "services" / "payments" / "fulfilment_bridge.py"


def _load_module(path: Path, name: str):
    spec = spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_database_revision_includes_handles_multiple_heads(monkeypatch):
    module = _load_module(DEPLOY_PATH, "checkout_prerequisite_deploy_followup")

    class FakeResult:
        def scalars(self):
            return self

        def all(self):
            return ["head_a", "head_b"]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _query):
            return FakeResult()

    class FakeEngine:
        def connect(self):
            return FakeConnection()

    class FakeRevision:
        def __init__(self, revision: str, *down: str):
            self.revision = revision
            self._normalized_down_revisions = down

    revisions = {
        "head_a": FakeRevision("head_a", "prepare"),
        "head_b": FakeRevision("head_b"),
        "prepare": FakeRevision("prepare", "base"),
        "base": FakeRevision("base"),
    }

    class FakeScriptDirectory:
        def get_revision(self, revision):
            return revisions.get(revision)

    monkeypatch.setattr(module, "inspect", lambda _connection: SimpleNamespace(has_table=lambda _name: True))
    monkeypatch.setattr(
        module.ScriptDirectory,
        "from_config",
        lambda _config: FakeScriptDirectory(),
    )

    assert module._database_revision_includes(object(), FakeEngine(), "prepare") is True
    assert module._database_revision_includes(object(), FakeEngine(), "missing") is False


def test_deploy_entrypoint_reacquires_lock_when_cutover_complete_but_validation_missing(monkeypatch):
    module = _load_module(DEPLOY_PATH, "checkout_prerequisite_deploy_relock")
    calls = []

    class Engine:
        def dispose(self):
            calls.append(("dispose",))

    class LockContext:
        def __enter__(self):
            calls.append(("lock_enter",))
            return "LOCKED-CONNECTION"

        def __exit__(self, exc_type, exc, tb):
            calls.append(("lock_exit",))

    monkeypatch.setattr(module, "create_engine", lambda url: calls.append(("create_engine", url)) or Engine())
    monkeypatch.setattr(module.command, "upgrade", lambda config, revision: calls.append(("upgrade", revision, config.attributes.get("connection"))))
    monkeypatch.setattr(module, "_cutover_already_complete", lambda _engine: True)
    monkeypatch.setattr(module, "_hold_cutover_validation_lock", lambda _engine: LockContext())
    monkeypatch.setattr(module, "start_workflow_classification_run", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("classification must stay skipped")))
    monkeypatch.setattr(module, "classify_workflow_batch", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("classification batches must stay skipped")))
    monkeypatch.setattr(module, "finalize_workflow_classification", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("finalize must stay skipped")))
    monkeypatch.setattr(module, "_database_revision_includes", lambda _config, _engine, revision: calls.append(("includes", revision)) or (revision == module.PREPARE_REVISION))

    module.run(database_url="postgresql+asyncpg://user:pass@localhost/db")

    assert calls == [
        ("create_engine", module._sync_database_url("postgresql+asyncpg://user:pass@localhost/db")),
        ("includes", module.PREPARE_REVISION),
        ("includes", module.VALIDATE_REVISION),
        ("lock_enter",),
        ("upgrade", "heads", "LOCKED-CONNECTION"),
        ("lock_exit",),
        ("dispose",),
    ]


@pytest.mark.asyncio
async def test_reconcile_paystack_initialization_recovers_pending_mapping(monkeypatch):
    module = _load_module(PAYMENTS_PATH, "payments_followup")
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": True,
                "data": {
                    "id": 321,
                    "reference": "ref-123",
                    "status": "processing",
                    "amount": 15500,
                    "currency": "NGN",
                },
            }

    class FakeClient:
        async def get(self, url, *, headers, timeout):
            calls.append(("get", url, headers["Authorization"], timeout))
            return FakeResponse()

    class FakeDB:
        async def commit(self):
            calls.append(("commit",))

    async def fake_recover_pending_payment_mapping(db, **kwargs):
        calls.append(("recover_pending", db, kwargs))
        return object()

    monkeypatch.setattr(module, "recover_pending_payment_mapping", fake_recover_pending_payment_mapping)

    with pytest.raises(HTTPException) as excinfo:
        await module._reconcile_paystack_initialization(
            FakeClient(),
            reference="ref-123",
            headers={"Authorization": "Bearer test"},
            db=FakeDB(),
        )

    assert excinfo.value.status_code == 503
    assert excinfo.value.detail == "Payment initialization is still pending"
    recover_call = next(call for call in calls if call[0] == "recover_pending")
    assert recover_call[2]["provider"] == "paystack"
    assert recover_call[2]["provider_reference"] == "ref-123"
    assert recover_call[2]["transaction_id"] == "ref-123"
    assert recover_call[2]["observed_amount"] == module.Decimal("155")
    assert recover_call[2]["observed_currency"] == "NGN"
    assert calls[-1] == ("commit",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "gateway_response",
    [
        {
            "reference": "ref-123",
            "status": "processing",
            "amount": 15500,
            "currency": "NGN",
        },
        {
            "status": True,
            "data": {
                "reference": "ref-123",
                "status": "processing",
                "amount": 15500,
                "currency": "NGN",
            },
        },
    ],
)
async def test_stored_paystack_pending_recovery_state_returns_none(gateway_response):
    module = _load_module(PAYMENTS_PATH, "payments_pending_session")
    order = SimpleNamespace(id="order-1", total_amount=Decimal("155.00"), currency="NGN")
    attempt = SimpleNamespace(order_id="order-1", provider="paystack", provider_reference="ref-123")
    payment = SimpleNamespace(
        order_id="order-1",
        payment_gateway=module.PaymentGateway.PAYSTACK,
        payment_method="paystack",
        amount=Decimal("155.00"),
        currency="NGN",
        gateway_response=gateway_response,
    )

    class FakeDB:
        async def get(self, model, value):
            assert model is module.PaymentAttempt
            assert value == "attempt-1"
            return attempt

        async def scalar(self, stmt):
            return payment

    result = await module._stored_paystack_initialization_session(
        FakeDB(), order=order, attempt_id="attempt-1", reference="ref-123"
    )

    assert result is None


@pytest.mark.asyncio
async def test_expired_call_started_attempt_is_closed_before_replay(monkeypatch):
    module = _load_module(BRIDGE_PATH, "bridge_attempt_expiry_followup")
    predecessor = SimpleNamespace(
        id="attempt-1",
        state="call_started",
        authorization_deadline_at=datetime.now(timezone.utc) - timedelta(seconds=5),
        terminal_reason=None,
        terminal_at=None,
        row_version=7,
    )
    locked_order = SimpleNamespace(id="order-1", workflow_cohort="domestic_checkout_v1")
    observed = {}
    reservation = SimpleNamespace(
        state="active",
        terminal_reason=None,
        terminal_at=None,
        row_version=4,
    )

    class FakeSession:
        def __init__(self):
            self.flush_calls = 0

        async def scalar(self, statement):
            sql = str(statement)
            if "SELECT clock_timestamp()" in sql:
                return datetime.now(timezone.utc)
            return locked_order

        async def flush(self):
            self.flush_calls += 1

    session = FakeSession()

    async def fake_active_bridge_attempt(_session, *, order_id, lock=False):
        assert order_id == "order-1"
        assert lock is True
        return predecessor

    async def fake_ensure_domestic_bridge_attempt(_session, *, order, provider, predecessor):
        observed["order"] = order
        observed["provider"] = provider
        observed["predecessor"] = predecessor
        return "NEW-ATTEMPT"

    monkeypatch.setattr(module, "active_bridge_attempt", fake_active_bridge_attempt)
    monkeypatch.setattr(module, "_attempt_reservations", lambda *_args, **_kwargs: None)
    async def fake_attempt_reservations(_session, *, attempt_id):
        assert attempt_id == "attempt-1"
        return [reservation]
    monkeypatch.setattr(module, "_attempt_reservations", fake_attempt_reservations)
    monkeypatch.setattr(
        module, "_ensure_domestic_bridge_attempt", fake_ensure_domestic_bridge_attempt
    )

    result = await module._ensure_bridge_attempt(
        session, order=locked_order, provider="stripe"
    )

    assert result == "NEW-ATTEMPT"
    assert predecessor.state == "expired"
    assert predecessor.terminal_reason == "authorization_deadline_elapsed"
    assert predecessor.terminal_at is not None
    assert predecessor.row_version == 8
    assert reservation.state == "expired"
    assert reservation.terminal_reason == "authorization_deadline_elapsed"
    assert reservation.terminal_at is None
    assert reservation.row_version == 5
    assert session.flush_calls == 1
    assert observed["predecessor"] is predecessor


def test_effective_claim_sql_bounds_unresolved_attempts_by_authorization_deadline():
    module = _load_module(RESERVATIONS_PATH, "reservations_deadline_followup")
    normalized = " ".join(str(module._EFFECTIVE_CLAIM_SQL).split())
    assert "pa.state IN ('call_started','abandoned_unknown') AND pa.authorization_deadline_at>=clock_timestamp()" in normalized
    assert "OR (pa.state='verified' AND pa.authorization_deadline_at>=clock_timestamp())" in normalized
    assert "pa.state IN ('call_started','abandoned_unknown') OR (pa.state='verified'" not in normalized


@pytest.mark.asyncio
async def test_shared_inventory_subjects_are_checked_once(monkeypatch):
    module = _load_module(RESERVATIONS_PATH, "reservations_followup")
    seen = []

    async def fake_lock_and_available(_db, item):
        seen.append((item.inventory_subject_kind, item.inventory_subject_id))
        return 10

    monkeypatch.setattr(module, "_lock_and_available", fake_lock_and_available)

    item_a1 = SimpleNamespace(inventory_subject_kind="product", inventory_subject_id="A", quantity=2)
    item_a2 = SimpleNamespace(inventory_subject_kind="product", inventory_subject_id="A", quantity=1)
    item_b = SimpleNamespace(inventory_subject_kind="product", inventory_subject_id="B", quantity=4)

    required = {}
    subject_examples = {}
    for item in [item_a1, item_a2, item_b]:
        key = (item.inventory_subject_kind, item.inventory_subject_id)
        required[key] = required.get(key, 0) + item.quantity
        subject_examples.setdefault(key, item)
    for key, required_quantity in required.items():
        if await module._lock_and_available(None, subject_examples[key]) < required_quantity:
            raise HTTPException(status_code=409, detail="insufficient stock")

    assert seen == [("product", "A"), ("product", "B")]


@pytest.mark.asyncio
async def test_recover_payment_mapping_locks_order_before_attempt(monkeypatch):
    module = _load_module(BRIDGE_PATH, "bridge_recover_lock_order_followup")
    attempt = SimpleNamespace(id="attempt-1", order_id="order-1", amount=Decimal("155.00"), currency="NGN")
    order = SimpleNamespace(id="order-1")
    payment = SimpleNamespace(order_id="order-1")
    calls = []

    class FakeScalarResult:
        def __init__(self, value):
            self.value = value

    class FakeSession:
        async def scalar(self, statement):
            sql = " ".join(str(statement).split())
            if "FROM payment_attempts" in sql and "provider_reference" in sql and "FOR UPDATE" not in sql:
                calls.append("attempt_lookup")
                return attempt
            if "FROM orders" in sql and "FOR UPDATE" in sql:
                calls.append("order_lock")
                return order
            if "FROM payment_attempts" in sql and "id = :id_1" in sql and "FOR UPDATE" in sql:
                calls.append("attempt_lock")
                return attempt
            if "FROM payments" in sql and "gateway_response" in sql:
                calls.append("payment_by_reference")
                return None
            if "FROM payments" in sql and "transaction_id = :transaction_id_1" in sql:
                calls.append("payment_by_tx")
                return payment
            raise AssertionError(sql)

        async def scalars(self, statement):
            sql = " ".join(str(statement).split())
            if "FROM payments" in sql and "gateway_response" in sql:
                calls.append("payment_by_reference")
                return iter([payment])
            raise AssertionError(str(statement))

        def add(self, _obj):
            raise AssertionError("new payment should not be created")

        async def flush(self):
            calls.append("flush")

    async def fake_finalize(session, **kwargs):
        calls.append(("finalize", kwargs["payment"], kwargs["provider_reference"]))
        return "FINALIZED"

    monkeypatch.setattr(module, "finalize_verified_payment", fake_finalize)

    payment_result, result = await module.recover_payment_mapping(
        FakeSession(),
        provider="paystack",
        provider_reference="ref-123",
        transaction_id="tx-123",
        observed_amount=Decimal("155.00"),
        observed_currency="NGN",
        event_id="evt-1",
        evidence_payload={"reference": "ref-123"},
    )

    assert payment_result is payment
    assert result == "FINALIZED"
    assert calls[:3] == ["attempt_lookup", "order_lock", "attempt_lock"]


@pytest.mark.asyncio
async def test_recover_failed_payment_mapping_locks_order_before_attempt(monkeypatch):
    module = _load_module(BRIDGE_PATH, "bridge_failed_recover_lock_order_followup")
    attempt = SimpleNamespace(
        id="attempt-1",
        order_id="order-1",
        amount=Decimal("155.00"),
        currency="NGN",
    )
    order = SimpleNamespace(id="order-1")
    payment = SimpleNamespace(order_id="order-1")
    calls = []

    class FakeSession:
        async def scalar(self, statement):
            sql = " ".join(str(statement).split())
            if "FROM payment_attempts" in sql and "payment_attempts.provider = :provider_1" in sql and "payment_attempts.provider_reference = :provider_reference_1" in sql and "FOR UPDATE" not in sql:
                calls.append("attempt_lookup")
                return attempt
            if "FROM orders" in sql and "FOR UPDATE" in sql:
                calls.append("order_lock")
                return order
            if "FROM payment_attempts" in sql and "payment_attempts.id = :id_1" in sql and "FOR UPDATE" in sql:
                calls.append("attempt_lock")
                return attempt
            if "FROM payments" in sql and "transaction_id = :transaction_id_1" in sql:
                calls.append("payment_by_tx")
                return payment
            raise AssertionError(sql)

        def add(self, _obj):
            raise AssertionError("new payment should not be created")

        async def flush(self):
            calls.append("flush")

    async def fake_finalize(session, **kwargs):
        calls.append(("finalize_failed", kwargs["payment"], kwargs["provider_reference"]))
        return "FAILED-FINALIZED"

    monkeypatch.setattr(module, "finalize_failed_payment", fake_finalize)

    payment_result, result = await module.recover_failed_payment_mapping(
        FakeSession(),
        provider="paystack",
        provider_reference="ref-123",
        transaction_id="tx-123",
        event_id="evt-1",
        evidence_payload={"reference": "ref-123"},
        failure_reason="provider_failed",
    )

    assert payment_result is payment
    assert result == "FAILED-FINALIZED"
    assert calls[:4] == ["attempt_lookup", "order_lock", "attempt_lock", "payment_by_tx"]


@pytest.mark.asyncio
async def test_finalize_verified_payment_routes_expired_attempt_to_late_payment_exception(monkeypatch):
    module = _load_module(BRIDGE_PATH, "bridge_expired_verification_followup")
    order = SimpleNamespace(
        id="order-1",
        workflow_cohort="domestic_checkout_v1",
        payment_status=module.PaymentStatus.PENDING,
        fulfillment_status=module.FulfillmentStatus.ORDER_RECEIVED,
    )
    payment = SimpleNamespace(
        status=module.TransactionStatus.PENDING,
        completed_at=None,
        order_id="order-1",
    )
    attempt = SimpleNamespace(
        id="attempt-1",
        order_id="order-1",
        amount=Decimal("155.00"),
        currency="NGN",
        provider_reference="ref-123",
        provider="paystack",
        state="expired",
        workflow_cohort="domestic_checkout_v1",
    )
    successor = SimpleNamespace(
        id="attempt-2",
        order_id="order-1",
        state="call_started",
        provider="paystack",
        provider_reference="ref-456",
        lease_token="lease-2",
        claim_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        terminal_reason=None,
        terminal_at=None,
        terminal_evidence_id=None,
        row_version=3,
    )
    intermediary = SimpleNamespace(
        id="attempt-mid",
        order_id="order-1",
        state="abandoned_unknown",
        provider="paystack",
        provider_reference="ref-mid",
        lease_token=None,
        terminal_reason="authorization_deadline_elapsed",
        terminal_at=datetime.now(timezone.utc),
        terminal_evidence_id="evidence-mid",
        row_version=5,
    )
    successor_reservation = SimpleNamespace(
        state="active",
        terminal_reason=None,
        terminal_at=None,
        row_version=9,
    )
    events = []
    session_calls = []
    added = []

    class FakeSession:
        async def scalar(self, statement):
            sql = str(statement)
            if "SELECT clock_timestamp()" in sql:
                return datetime.now(timezone.utc)
            if "FROM payment_attempts" in sql and "payment_attempts.provider = :provider_1" in sql and "payment_attempts.provider_reference = :provider_reference_1" in sql:
                return attempt
            if "FROM payment_attempts" in sql and "payment_attempts.id = :id_1" in sql and "FOR UPDATE" in sql:
                return attempt
            if "FROM orders" in sql:
                return order
            return None

        async def scalars(self, statement):
            sql = " ".join(str(statement).split())
            if "WITH RECURSIVE attempt_lineage" in sql and "FROM payment_attempts JOIN attempt_lineage" in sql:
                assert "payment_attempts.state IN" in sql
                return iter([successor])
            raise AssertionError(sql)

        def add(self, obj):
            added.append(obj)

        async def flush(self):
            for index, obj in enumerate(added, start=1):
                if getattr(obj, "id", None) is None:
                    obj.id = f"evidence-{index}"
            session_calls.append("flush")

        async def execute(self, statement, params=None):
            session_calls.append((str(statement), params))
            return None

    async def fake_validate(*_args, **_kwargs):
        return None

    async def fake_enqueue(session, *, attempt, event_type, reason_code):
        events.append((attempt.id, event_type, reason_code))

    async def fake_attempt_reservations(_session, *, attempt_id):
        assert attempt_id == "attempt-2"
        return [successor_reservation]

    monkeypatch.setattr(module, "_validate_attempt_payment_mapping", fake_validate)
    monkeypatch.setattr(module, "_enqueue_payment_event", fake_enqueue)
    monkeypatch.setattr(module, "_attempt_reservations", fake_attempt_reservations)

    result = await module.finalize_verified_payment(
        FakeSession(),
        payment=payment,
        provider="paystack",
        provider_reference="ref-123",
        event_id="evt-1",
        evidence_payload={"ok": True},
        observed_amount=Decimal("155.00"),
        observed_currency="NGN",
        observed_at=datetime.now(timezone.utc),
    )

    assert result.bridge_applied is True
    assert result.replay is False
    assert result.order is order
    assert result.order is order
    assert payment.status == module.TransactionStatus.COMPLETED
    assert order.payment_status == module.PaymentStatus.PAID
    assert successor.state == "failed"
    assert successor.terminal_reason == "superseded_by_late_verified_capture"
    assert successor.terminal_at is None
    assert successor.row_version == 4
    assert successor.terminal_evidence_id is not None
    assert successor_reservation.state == "released"
    assert successor_reservation.terminal_reason == "superseded_by_late_verified_capture"
    assert successor_reservation.terminal_at is None
    assert successor_reservation.row_version == 10
    assert [obj.evidence_type for obj in added] == ["payment_failed"]
    assert events == [("attempt-1", "late_payment_exception", "reservation_released")]


@pytest.mark.asyncio
async def test_finalize_verified_payment_routes_expired_successor_lease_through_unknown_then_failed(monkeypatch):
    module = _load_module(BRIDGE_PATH, "bridge_expired_successor_lease_followup")
    now = datetime.now(timezone.utc)
    order = SimpleNamespace(
        id="order-1",
        workflow_cohort="domestic_checkout_v1",
        payment_status=module.PaymentStatus.PENDING,
        fulfillment_status=module.FulfillmentStatus.ORDER_RECEIVED,
    )
    payment = SimpleNamespace(
        status=module.TransactionStatus.PENDING,
        completed_at=None,
        order_id="order-1",
    )
    attempt = SimpleNamespace(
        id="attempt-1",
        order_id="order-1",
        amount=Decimal("155.00"),
        currency="NGN",
        provider_reference="ref-123",
        provider="paystack",
        state="expired",
        workflow_cohort="domestic_checkout_v1",
    )
    successor = SimpleNamespace(
        id="attempt-2",
        order_id="order-1",
        state="call_started",
        provider="paystack",
        provider_reference="ref-456",
        lease_token="lease-2",
        claim_expires_at=now - timedelta(minutes=5),
        terminal_reason=None,
        terminal_at=None,
        terminal_evidence_id=None,
        row_version=3,
    )
    successor_reservation = SimpleNamespace(
        state="active",
        terminal_reason=None,
        terminal_at=None,
        row_version=9,
    )
    events = []
    session_calls = []
    scalar_calls = []
    added = []

    class FakeSession:
        async def scalar(self, statement):
            sql = " ".join(str(statement).split())
            if "SELECT clock_timestamp()" in sql:
                scalar_calls.append("SELECT clock_timestamp()")
                return now
            if "FROM payment_attempts" in sql and "payment_attempts.provider = :provider_1" in sql and "payment_attempts.provider_reference = :provider_reference_1" in sql:
                return attempt
            if "FROM payment_attempts" in sql and "payment_attempts.id = :id_1" in sql and "FOR UPDATE" in sql:
                return attempt
            if "FROM orders" in sql:
                return order
            return None

        async def scalars(self, statement):
            sql = " ".join(str(statement).split())
            if "WITH RECURSIVE attempt_lineage" in sql and "FROM payment_attempts JOIN attempt_lineage" in sql:
                return iter([successor])
            raise AssertionError(sql)

        def add(self, obj):
            added.append(obj)

        async def flush(self):
            for index, obj in enumerate(added, start=1):
                if getattr(obj, "id", None) is None:
                    obj.id = f"evidence-{index}"
            session_calls.append("flush")

        async def execute(self, statement, params=None):
            session_calls.append((str(statement), params))
            return None

    async def fake_validate(*_args, **_kwargs):
        return None

    async def fake_enqueue(session, *, attempt, event_type, reason_code):
        events.append((attempt.id, event_type, reason_code))

    async def fake_attempt_reservations(_session, *, attempt_id):
        assert attempt_id == "attempt-2"
        return [successor_reservation]

    monkeypatch.setattr(module, "_validate_attempt_payment_mapping", fake_validate)
    monkeypatch.setattr(module, "_enqueue_payment_event", fake_enqueue)
    monkeypatch.setattr(module, "_attempt_reservations", fake_attempt_reservations)

    result = await module.finalize_verified_payment(
        FakeSession(),
        payment=payment,
        provider="paystack",
        provider_reference="ref-123",
        event_id="evt-1",
        evidence_payload={"ok": True},
        observed_amount=Decimal("155.00"),
        observed_currency="NGN",
        observed_at=now,
    )

    assert result.bridge_applied is True
    assert payment.status == module.TransactionStatus.COMPLETED
    assert successor.state == "failed"
    assert successor.terminal_reason == "superseded_by_late_verified_capture"
    assert successor.terminal_evidence_id == "evidence-2"
    assert successor.row_version == 5
    assert successor_reservation.state == "released"
    assert [obj.evidence_type for obj in added] == ["outcome_unknown", "payment_failed"]
    assert scalar_calls == [
        "SELECT clock_timestamp()",
        "SELECT clock_timestamp()",
    ]
    assert any("set_config('shopsoma.payment_lease_token'" in call[0] for call in session_calls if isinstance(call, tuple))
    assert events == [("attempt-1", "late_payment_exception", "reservation_released")]


def test_create_estimate_refresh_supersedes_current_unselected_leaf(monkeypatch):
    module = _load_module(ESTIMATES_PATH, "estimates_refresh_followup")
    predecessor = SimpleNamespace(id="estimate-1")
    captured = {}

    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

        def scalars(self):
            return self

        def all(self):
            if isinstance(self._value, list):
                return self._value
            if self._value is None:
                return []
            return [self._value]

    class FakeDB:
        def add(self, obj):
            if obj.__class__.__name__ == "CheckoutShippingEstimate":
                captured["estimate"] = obj

        async def execute(self, statement):
            sql = str(statement)
            if "FROM checkout_shipping_estimates" in sql and "source_command IN" in sql:
                return FakeResult(None)
            if "FROM checkout_shipping_estimates" in sql and "ORDER BY checkout_shipping_estimates.created_at DESC" in sql:
                return FakeResult(predecessor)
            if "FROM shipping_rates" in sql:
                rate = SimpleNamespace(
                    id="rate-1",
                    is_active=True,
                    country="NG",
                    state=None,
                    priority=1,
                    min_order_value=None,
                    max_order_value=None,
                    base_rate=Decimal("2500.00"),
                    name="Standard",
                    min_delivery_days=2,
                    max_delivery_days=5,
                )
                return FakeResult(rate)
            raise AssertionError(sql)

        async def scalar(self, statement):
            sql = str(statement)
            if "statement_timestamp()" in sql:
                return datetime.now(timezone.utc)
            raise AssertionError(sql)

        async def flush(self):
            estimate = captured.get("estimate")
            if estimate is not None and getattr(estimate, "id", None) is None:
                estimate.id = "estimate-2"

    order = SimpleNamespace(
        id="order-1",
        customer_id="customer-1",
        workflow_cohort="domestic_checkout_v1",
        currency="NGN",
        subtotal=Decimal("155000.00"),
        shipping_address=SimpleNamespace(country="NG", state="Lagos"),
    )

    monkeypatch.setattr(module, "order_snapshot", lambda _order: ("dest-hash", "snap-hash"))
    monkeypatch.setattr(module, "_hash", lambda payload: "f" * 64)
    monkeypatch.setattr(module, "_estimate_expiry_delta", lambda ttl: timedelta(seconds=ttl))

    import asyncio
    estimate = asyncio.run(
        module.create_estimate(
            FakeDB(),
            order=order,
            actor_type="customer",
            actor_id="customer-1",
            idempotency_key="estimate-2",
        )
    )

    assert estimate is captured["estimate"]
    assert estimate.supersedes_estimate_id == "estimate-1"
    assert estimate.source_command == "refresh_checkout_estimate"


def test_create_estimate_replays_refresh_idempotency_key(monkeypatch):
    module = _load_module(ESTIMATES_PATH, "estimates_refresh_replay_followup")
    existing = SimpleNamespace(
        request_fingerprint="f" * 64,
        source_command="refresh_checkout_estimate",
        idempotency_key="estimate-2",
    )

    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class FakeDB:
        async def execute(self, statement):
            sql = str(statement)
            assert "source_command IN" in sql
            return FakeResult(existing)

    order = SimpleNamespace(
        id="order-1",
        customer_id="customer-1",
        workflow_cohort="domestic_checkout_v1",
    )

    monkeypatch.setattr(module, "order_snapshot", lambda _order: ("dest-hash", "snap-hash"))
    monkeypatch.setattr(module, "_hash", lambda payload: "f" * 64)

    import asyncio
    replay = asyncio.run(
        module.create_estimate(
            FakeDB(),
            order=order,
            actor_type="customer",
            actor_id="customer-1",
            idempotency_key="estimate-2",
        )
    )

    assert replay is existing
