from decimal import Decimal
from sqlalchemy import select
from app.core.config import settings
from app.models.app_setting import AppSetting
from app.models.shipping_rate import ShippingRate
from tests.test_checkout_estimate_api import _domestic_catalogue, _create_authenticated_estimate

import pytest
from pydantic import ValidationError

from app.schemas.app_setting import ShippingProviderSettingsUpdate


def test_legacy_provider_payload_is_preserved():
    assert ShippingProviderSettingsUpdate(use_shipbubble=True).provider == "shipbubble"
    assert ShippingProviderSettingsUpdate(use_shipbubble=False).provider == "manual"


def test_provider_conflicts_rejected():
    with pytest.raises(ValidationError):
        ShippingProviderSettingsUpdate(provider="manual", use_shipbubble=True)
    with pytest.raises(ValidationError):
        ShippingProviderSettingsUpdate()


def test_dhl_selection_is_a_valid_mode_subject_to_server_readiness():
    assert ShippingProviderSettingsUpdate(provider="dhl").provider == "dhl"



def rate_payload(**changes):
    return {"name": "Free delivery", "base_rate": 0, "country": " ng ", "state": " LAGOS ",
            "min_delivery_days": 2, "max_delivery_days": 4, "is_default": True, **changes}


@pytest.mark.asyncio
async def test_admin_provider_persistence_readiness_and_legacy(client, admin_user, customer_user, db_session):
    for headers in ({}, customer_user['headers']):
        response = await client.put('/api/v1/settings/shipping-provider', headers=headers, json={'provider': 'manual'})
        assert response.status_code in (401, 403)
    response = await client.put('/api/v1/settings/shipping-provider', headers=admin_user['headers'], json={'use_shipbubble': False})
    assert response.status_code == 200, response.text
    assert response.json()['provider'] == 'manual'
    assert response.json()['readiness']['shipbubble'] is False
    persisted = await client.get('/api/v1/settings/shipping-provider')
    assert persisted.json() == response.json()
    row = await db_session.scalar(select(AppSetting).where(AppSetting.key == 'shipping_provider'))
    assert str(admin_user['user'].id) in row.description
    for payload in ({'use_shipbubble': True}, {'provider': 'dhl'}):
        rejected = await client.put('/api/v1/settings/shipping-provider', headers=admin_user['headers'], json=payload)
        assert rejected.status_code == 409, rejected.text
    assert (await client.get('/api/v1/settings/shipping-provider')).json()['provider'] == 'manual'


@pytest.mark.asyncio
async def test_rate_crud_normalization_defaults_zero_and_preview(client, admin_user, customer_user, db_session):
    url = '/api/v1/shipping-rates'
    denied = await client.post(url, headers=customer_user['headers'], json=rate_payload())
    assert denied.status_code == 403
    first = await client.post(url, headers=admin_user['headers'], json=rate_payload())
    assert first.status_code == 201, first.text
    rate_id = first.json()['id']
    assert first.json()['country'] == 'Nigeria'
    assert first.json()['state'] == 'Lagos'
    preview = await client.post(url + '/calculate', json={'country': ' NIGERIA ', 'state': 'lagos', 'order_value': 60000})
    assert preview.status_code == 200, preview.text
    assert preview.json()['recommended_rate']['base_rate'] == 0
    second = await client.post(url, headers=admin_user['headers'], json=rate_payload(name='Countrywide', state='', base_rate=1000))
    assert second.status_code == 201, second.text
    rows = (await client.get(url)).json()['shipping_rates']
    assert sum(r['is_default'] for r in rows) == 1
    changed = await client.put(url + '/' + rate_id, headers=admin_user['headers'], json={'country': ' nigeria ', 'state': ' abuja ', 'name': ' Trimmed '})
    assert changed.status_code == 200, changed.text
    assert changed.json()['name'] == 'Trimmed'
    assert changed.json()['state'] == 'Abuja'
    invalid = await client.put(url + '/' + rate_id, headers=admin_user['headers'], json={'min_delivery_days': 6})
    assert invalid.status_code == 422
    assert (await client.get(url + '/' + rate_id)).json()['min_delivery_days'] == 2
    removed = await client.delete(url + '/' + rate_id, headers=admin_user['headers'])
    assert removed.status_code == 204
    assert (await client.get(url + '/' + rate_id)).json()['is_active'] is False
    inactive_default = await client.post(url + '/' + rate_id + '/set-default', headers=admin_user['headers'])
    assert inactive_default.status_code == 422
    unsupported = await client.post(url + '/calculate', json={'country': 'Ghana', 'state': 'Accra', 'order_value': 60000})
    assert unsupported.status_code == 404


@pytest.mark.asyncio
async def test_manual_quote_keeps_snapshot_after_deactivation_with_dhl_gate_on(client, db_session, admin_user, vendor_user, customer_user, monkeypatch):
    from app.services.checkout import estimates
    from unittest.mock import AsyncMock
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, 'DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED', True)
    monkeypatch.setattr(settings, 'DOMESTIC_CHECKOUT_COHORT_ALLOWLIST', str(customer_user['user'].id))
    from pydantic import SecretStr
    for flag in ('DHL_ENABLED', 'DHL_DOMESTIC_WORKFLOW_ENABLED', 'DHL_DOMESTIC_PROVIDER_CALLS_ENABLED', 'DHL_DOMESTIC_CHECKOUT_ENABLED'):
        monkeypatch.setattr(settings, flag, True)
    for credential in ('DHL_API_USERNAME', 'DHL_API_PASSWORD', 'DHL_EXPORT_ACCOUNT_NUMBER'):
        monkeypatch.setattr(settings, credential, SecretStr('local-test-only'))
    monkeypatch.setattr(settings, 'DHL_DOMESTIC_SANDBOX_COHORT_IDS', str(customer_user['user'].id))
    provider_call = AsyncMock(side_effect=AssertionError('Manual must not call DHL'))
    monkeypatch.setattr(estimates, '_dhl_checkout_options', provider_call)
    db_session.add(AppSetting(key='shipping_provider', value='manual', value_type='string'))
    await db_session.commit()
    order_id, quote = await _create_authenticated_estimate(client, customer_user, address, product, key='manual-immutable')
    option = next(o for o in quote['options'] if o['service_label'] == 'Standard')
    rate = await db_session.scalar(select(ShippingRate).where(ShippingRate.name == 'Standard'))
    changed = await client.put(f'/api/v1/shipping-rates/{rate.id}', headers=admin_user['headers'], json={'base_rate': 9000, 'is_active': False})
    assert changed.status_code == 200, changed.text
    provider_row = await db_session.scalar(select(AppSetting).where(AppSetting.key == 'shipping_provider'))
    provider_row.value = 'shipbubble'
    await db_session.commit()
    replay = await client.post(f'/api/v1/orders/{order_id}/checkout-estimates', headers={**customer_user['headers'], 'X-Idempotency-Key': 'manual-immutable'})
    assert replay.status_code in (200, 201), replay.text
    assert replay.json()['id'] == quote['id']
    selected = await client.post(f'/api/v1/orders/{order_id}/checkout-estimates/{quote["id"]}/options/{option["id"]}/select', headers={**customer_user['headers'], 'X-Idempotency-Key': 'manual-select'}, json={'option_id': option['id'], 'amount': '0.01'})
    assert selected.status_code == 200, selected.text
    assert selected.json()['selected_option']['amount'] == option['amount']
    assert Decimal(selected.json()['selected_option']['amount']) == Decimal('1500')
    provider_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_thresholds_and_ineligible_id_rejected_in_review_and_order(client, db_session, customer_user, vendor_user):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    standard = await db_session.scalar(select(ShippingRate).where(ShippingRate.name == 'Standard'))
    standard.min_order_value = Decimal('90000')
    await db_session.commit()
    payload = {'items': [{'product_id': str(product.id), 'quantity': 1}],
               'shipping_address_id': str(address.id), 'currency': 'NGN', 'shipping_rate_id': str(standard.id)}
    for path in ('/api/v1/orders/review', '/api/v1/orders'):
        response = await client.post(path, headers=customer_user['headers'], json=payload)
        assert response.status_code == 422, response.text
    preview = await client.post('/api/v1/shipping-rates/calculate', json={'country': 'ng', 'state': 'lagos', 'order_value': 80000})
    assert preview.status_code == 200, preview.text
    assert all(rate['id'] != str(standard.id) for rate in preview.json()['available_rates'])


@pytest.mark.asyncio
async def test_concurrent_first_provider_save_and_defaults_are_serialized(client, db_session, admin_user):
    import asyncio
    from tests.test_checkout_estimate_api import _isolated_route_client
    async with _isolated_route_client('manual-concurrency') as isolated:
        results = await asyncio.gather(*[
            isolated.put('/api/v1/settings/shipping-provider', headers=admin_user['headers'], json={'provider': 'manual'})
            for _ in range(2)
        ])
        assert all(response.status_code == 200 for response in results), [r.text for r in results]
        results = await asyncio.gather(*[
            isolated.post('/api/v1/shipping-rates', headers=admin_user['headers'], json=rate_payload(name=f'Concurrent {i}'))
            for i in range(2)
        ])
        assert all(response.status_code == 201 for response in results), [r.text for r in results]
    rates = (await client.get('/api/v1/shipping-rates')).json()['shipping_rates']
    assert sum(rate['is_default'] for rate in rates) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["min_order_value", "max_order_value"])
@pytest.mark.parametrize("value", ["100000000", "9999999999", "1.001"])
async def test_create_rate_rejects_unstorable_monetary_bounds(client, admin_user, field, value):
    response = await client.post('/api/v1/shipping-rates', headers=admin_user['headers'],
                                 json=rate_payload(**{field: value}))
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("key,value", [("shipping_provider", "shipbubble"), ("shipping_provider", "dhl"), ("shipping_use_shipbubble", "true")])
async def test_legacy_order_routes_reject_nonmanual_provider(client, db_session, customer_user, vendor_user, monkeypatch, key, value):
    monkeypatch.setattr(settings, 'DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED', False)
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    db_session.add(AppSetting(key=key, value=value, value_type='string'))
    await db_session.commit()
    payload = {'items': [{'product_id': str(product.id), 'quantity': 1}],
               'shipping_address_id': str(address.id), 'currency': 'NGN'}
    for path in ('/api/v1/orders/review', '/api/v1/orders'):
        response = await client.post(path, headers=customer_user['headers'], json=payload)
        assert response.status_code == 503, response.text
        assert 'manual pricing requires manual mode' in response.json()['detail']


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_manual", [False, True])
async def test_legacy_manual_pricing_remains_available(client, db_session, customer_user, vendor_user, monkeypatch, explicit_manual):
    monkeypatch.setattr(settings, 'DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED', False)
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    if explicit_manual:
        db_session.add(AppSetting(key='shipping_provider', value='manual', value_type='string'))
        await db_session.commit()
    payload = {'items': [{'product_id': str(product.id), 'quantity': 1}],
               'shipping_address_id': str(address.id), 'currency': 'NGN'}
    review = await client.post('/api/v1/orders/review', headers=customer_user['headers'], json=payload)
    assert review.status_code == 200, review.text
    created = await client.post('/api/v1/orders', headers=customer_user['headers'], json=payload)
    assert created.status_code == 201, created.text
    assert Decimal(str(created.json()['shipping_cost'])) == Decimal(str(review.json()['summary']['shipping_cost']))


@pytest.mark.asyncio
async def test_implicit_dhl_gate_keeps_legacy_pricing_compatibility(db_session, monkeypatch):
    from types import SimpleNamespace
    from app.services.shipping import provider_settings
    monkeypatch.setattr(provider_settings, 'domestic_shipping_capabilities', lambda config: SimpleNamespace(checkout_enabled=True))
    monkeypatch.setattr(settings, 'ENVIRONMENT', 'test')
    assert (await provider_settings.shipping_provider_settings(db_session)).provider == 'dhl'
    await provider_settings.require_manual_order_pricing(db_session)
