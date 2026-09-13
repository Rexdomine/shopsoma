"""WebSocket authentication must not provide a guest capability bypass."""

from pathlib import Path


def test_guest_websocket_fallback_is_not_present():
    source = Path("app/api/v1/websocket.py").read_text()
    assert "Falling back to guest access" not in source
    assert "Authentication required" in source
    # The endpoint must reject before accepting a connection when no JWT is
    # supplied; this source-level guard keeps the URL/header boundary explicit.
    assert source.count("await websocket.close(code=1008, reason=\"Authentication required\")") >= 2