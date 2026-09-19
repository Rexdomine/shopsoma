from datetime import datetime, timedelta, timezone

import pytest


@pytest.mark.asyncio
async def test_public_coming_soon_is_off_by_default(client):
    response = await client.get('/api/v1/settings/public/coming-soon')

    assert response.status_code == 200
    assert response.json() == {
        'enabled': False,
        'launch_at': None,
        'image_url': '/images/hero/campaign/campaign-exterior-desktop.webp',
        'updated_at': None,
    }


@pytest.mark.asyncio
async def test_admin_can_schedule_coming_soon_and_public_gate_expires(
    client,
    admin_user,
):
    launch_at = datetime.now(timezone.utc) + timedelta(days=3)
    response = await client.put(
        '/api/v1/settings/admin/coming-soon',
        json={
            'enabled': True,
            'launch_at': launch_at.isoformat(),
            'image_url': '/images/hero/campaign/campaign-exterior-mobile.webp',
        },
        headers=admin_user['headers'],
    )

    assert response.status_code == 200
    assert response.json()['enabled'] is True
    assert response.json()['image_url'].endswith('campaign-exterior-mobile.webp')

    public = await client.get('/api/v1/settings/public/coming-soon')
    assert public.status_code == 200
    assert public.json()['enabled'] is True

    expired = await client.put(
        '/api/v1/settings/admin/coming-soon',
        json={'enabled': True, 'launch_at': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
        headers=admin_user['headers'],
    )
    assert expired.status_code == 200

    public_expired = await client.get('/api/v1/settings/public/coming-soon')
    assert public_expired.status_code == 200
    assert public_expired.json()['enabled'] is False
