"""WebSocket authentication must not provide a guest capability bypass."""

from pathlib import Path


def test_guest_websocket_fallback_is_not_present():
    source = Path("app/api/v1/websocket.py").read_text()
    assert "Falling back to guest access" not in source
    assert "Authentication required" in source
    # The endpoint must reject before accepting a connection when no JWT is
    # supplied; this source-level guard keeps the URL/header boundary explicit.
    assert source.count("await websocket.close(code=1008, reason=\"Authentication required\")") >= 2


def test_authenticated_websocket_uses_canonical_current_owner():
    source = Path("app/api/v1/websocket.py").read_text()
    assert "from app.models.order_guest_capability import OrderCurrentOwner" in source
    assert "current_owner.current_authenticated_user_id" in source
    assert "canonical_owner_id" in source


def test_order_creation_requires_effective_dhl_for_rate_less_secure_checkout():
    source = Path("app/api/v1/orders.py").read_text()
    assert "effective_shipping_settings.provider == \"dhl\"" in source
    assert "No shipping available for this location" in source