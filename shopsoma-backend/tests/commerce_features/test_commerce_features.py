"""Isolated route and persistence checks; no PostgreSQL services required.

Run with --confcutdir=tests/commerce_features so the global PostgreSQL fixture
bootstrap is not loaded. Settings use the real ORM and a file-backed SQLite DB.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.api.v1 import settings as routes
from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.app_setting import AppSetting
from app.models.user import UserRole
from app.services.commerce_features import get_commerce_features, shopping_currency


class AsyncSettingsSession:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    def add(self, row):
        self.session.add(row)

    async def commit(self):
        self.session.commit()


@pytest.fixture
def api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'settings.db'}", connect_args={"check_same_thread": False})
    AppSetting.__table__.create(engine)
    app = FastAPI()
    app.include_router(routes.router)

    async def db():
        with Session(engine) as session:
            yield AsyncSettingsSession(session)

    app.dependency_overrides[get_db] = db
    with TestClient(app) as client:
        yield app, client, engine
    engine.dispose()


def actor(app, role):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(role=role, is_active=True)


def test_defaults_and_no_unsafe_public_fields(api):
    _, client, engine = api
    with Session(engine) as db:
        db.add(AppSetting(key="private_provider_secret", value="test-only-placeholder"))
        db.commit()
    response = client.get('/settings/public/commerce-features')
    assert response.json() == {"stripe_enabled": False, "usd_switching_enabled": False}


@pytest.mark.parametrize('stripe,usd', [(False, False), (False, True), (True, False), (True, True)])
def test_independent_flags_persist_across_sessions(api, stripe, usd):
    app, client, _ = api
    actor(app, UserRole.ADMIN)
    flags = {"stripe_enabled": stripe, "usd_switching_enabled": usd}
    response = client.put('/settings/admin/commerce-features', json=flags)
    assert response.status_code == 200
    assert response.json() == flags
    app.dependency_overrides.pop(get_current_user)
    assert client.get('/settings/public/commerce-features').json() == flags


@pytest.mark.parametrize('role', [None, UserRole.CUSTOMER, UserRole.VENDOR])
def test_only_admin_can_write(api, role):
    app, client, _ = api
    if role:
        actor(app, role)
    response = client.put('/settings/admin/commerce-features', json={"stripe_enabled": True, "usd_switching_enabled": True})
    assert response.status_code == 403
    assert client.get('/settings/public/commerce-features').json()['stripe_enabled'] is False


def test_write_requires_explicit_booleans(api):
    app, client, _ = api
    actor(app, UserRole.ADMIN)
    assert client.put('/settings/admin/commerce-features', json={"stripe_enabled": "false", "usd_switching_enabled": False}).status_code == 422


@pytest.mark.asyncio
async def test_new_shopping_currency_and_malformed_flag_fail_closed(api):
    _, _, engine = api
    with Session(engine) as session:
        session.add(AppSetting(key='usd_switching_enabled', value='invalid'))
        session.commit()
        db = AsyncSettingsSession(session)
        assert not (await get_commerce_features(db)).usd_switching_enabled
        assert await shopping_currency(db, 'USD') == 'NGN'
        assert await shopping_currency(db, 'NGN') == 'NGN'


@pytest.mark.asyncio
async def test_disabled_stripe_never_reaches_provider_for_legacy_order(monkeypatch):
    from app.api.v1 import payments
    from app.schemas.app_setting import CommerceFeatures
    monkeypatch.setattr(payments, 'get_commerce_features', AsyncMock(return_value=CommerceFeatures()))
    truth = AsyncMock(return_value=SimpleNamespace(bridge_applied=False))
    monkeypatch.setattr(payments, 'payment_initialization_truth', truth)
    provider = AsyncMock()
    monkeypatch.setattr(payments.stripe.PaymentIntent, 'create', provider)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        await payments._initialize_stripe_payment(SimpleNamespace(), SimpleNamespace(), AsyncMock())
    assert error.value.status_code == 403
    assert truth.call_args.kwargs['allow_new_attempt'] is False
    provider.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['pending', 'failed', 'expired'])
async def test_disabled_provider_cannot_start_or_replace_attempt(monkeypatch, state):
    from app.services.payments import fulfilment_bridge as bridge
    from decimal import Decimal
    from datetime import datetime, timezone
    order = SimpleNamespace(id='order', total_amount=Decimal('10'), currency='NGN', workflow_cohort='domestic_checkout_v1')
    attempt = SimpleNamespace(provider='stripe', state=state, authorization_deadline_at=None)
    monkeypatch.setattr(bridge, 'active_bridge_attempt', AsyncMock(return_value=attempt))
    create = AsyncMock()
    monkeypatch.setattr(bridge, '_ensure_domestic_bridge_attempt', create)
    db = AsyncMock()
    db.scalar.side_effect = [order, datetime.now(timezone.utc)]
    with pytest.raises(bridge.PaymentBridgeError, match='disabled'):
        await bridge.payment_initialization_truth(db, order=order, provider='stripe', capabilities=SimpleNamespace(quote_enforcement_enabled=True), allow_new_attempt=False)
    create.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_provider_can_replay_started_idempotent_attempt(monkeypatch):
    from app.services.payments import fulfilment_bridge as bridge
    from decimal import Decimal
    from datetime import datetime, timezone
    from uuid import uuid4
    order = SimpleNamespace(id=uuid4(), total_amount=Decimal('10'), currency='USD', workflow_cohort='domestic_checkout_v1')
    attempt = SimpleNamespace(id=uuid4(), provider='stripe', state='call_started', authorization_deadline_at=None, amount=Decimal('10'), currency='USD', provider_reference='original-reference', lease_token=uuid4())
    monkeypatch.setattr(bridge, 'active_bridge_attempt', AsyncMock(return_value=attempt))
    db = AsyncMock()
    db.scalar.side_effect = [order, datetime.now(timezone.utc)]
    truth = await bridge.payment_initialization_truth(db, order=order, provider='stripe', capabilities=SimpleNamespace(quote_enforcement_enabled=True), allow_new_attempt=False)
    assert truth.attempt_id == attempt.id
    assert truth.provider_reference == 'original-reference'
    assert truth.currency == 'USD'
    assert truth.amount == Decimal('10')
