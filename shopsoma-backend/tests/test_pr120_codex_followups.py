from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).parents[1]
DEPLOY_PATH = ROOT / "run_checkout_prerequisite_deploy.py"
PAYMENTS_PATH = ROOT / "app" / "api" / "v1" / "payments.py"
RESERVATIONS_PATH = ROOT / "app" / "services" / "checkout" / "reservations.py"


def _load_module(path: Path, name: str):
    spec = spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
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
