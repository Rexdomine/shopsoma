"""Test-only overrides; no fixture HTTP endpoints."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn

pytest_plugins = ["tests.conftest"]
EVIDENCE = Path("/evidence")


@pytest.fixture
def external_effects(monkeypatch):
    """Fail on attempted effects even if application code catches their exceptions."""
    from app.services.email_service import EmailService
    from app.services.image_service import ImageService
    from botocore.client import BaseClient
    from celery.app.task import Task
    from stripe import _api_requestor
    import requests

    state = {"attempts": [], "expect_email_failure": False}

    def denied(*args, **kwargs):
        state["attempts"].append("forbidden external effect")
        raise RuntimeError("External effect forbidden in DHL QA")

    async def denied_async(*args, **kwargs):
        return denied()

    async def email_failure(*args, **kwargs):
        state["attempts"].append("email failed before delivery")
        raise RuntimeError("Synthetic email transport failure")

    for name in vars(EmailService):
        if name.startswith("send_"):
            monkeypatch.setattr(EmailService, name, email_failure)
    for name in [
        "upload_image",
        "_upload_local",
        "_upload_s3",
        "copy_image_key",
        "delete_image",
        "delete_images",
    ]:
        monkeypatch.setattr(ImageService, name, denied_async)
    for name in [
        "generate_presigned_url",
        "_copy_image_key",
        "_delete_local_image",
        "get_image_info",
    ]:
        monkeypatch.setattr(ImageService, name, denied)
    monkeypatch.setattr(BaseClient, "_make_api_call", denied)
    monkeypatch.setattr(_api_requestor._APIRequestor, "request", denied)
    monkeypatch.setattr(Task, "apply_async", denied)
    monkeypatch.setattr(requests.sessions.Session, "request", denied)
    original = httpx.AsyncHTTPTransport.handle_async_request

    async def local_only(transport, request):
        if request.url.host not in ("127.0.0.1", "localhost", "::1"):
            denied()
        return await original(transport, request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", local_only)
    yield state
    assert not [
        attempt
        for attempt in state["attempts"]
        if attempt != "email failed before delivery"
        or not state["expect_email_failure"]
    ], "Unexpected external effect, including swallowed errors"


@pytest.fixture
def provider(monkeypatch, external_effects):
    from app.services.dhl.client import DHLClient
    from tests.test_dhl_phase4_booking import PHASE4

    state = {"mode": "success", "booking_calls": 0, "tracking_calls": 0}

    async def transport(request):
        if request.method == "POST" and request.url.path == "/shipments":
            state["booking_calls"] += 1
            # Lets two independent requests contend against real database guards.
            await asyncio.sleep(0.25)
            if state["mode"] == "timeout":
                raise httpx.ReadTimeout("synthetic timeout", request=request)
            if state["mode"] == "unknown":
                return httpx.Response(200, json={"synthetic": "ambiguous response"})
            return httpx.Response(200, json=PHASE4._fake_booking_response())
        if request.method == "GET" and request.url.path.endswith("/tracking"):
            state["tracking_calls"] += 1
            return httpx.Response(
                200,
                json={
                    "events": [
                        {
                            "typeCode": "COLLECTED",
                            "description": "Synthetic collection",
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    ]
                },
            )
        raise AssertionError("Unexpected DHL transport request")

    original = DHLClient.__init__

    def initialize(client, *, config, transport=None):
        original(
            client, config=config, transport=httpx.MockTransport(transport_handler)
        )

    transport_handler = transport
    monkeypatch.setattr(DHLClient, "__init__", initialize)
    return state


@pytest.fixture
async def runtime(db_session, admin_user, vendor_user, customer_user, provider):
    from app.main import app
    from app.core.database import get_db
    from app.api.v1.admin_orders import get_app_settings
    from tests.conftest import TestSessionLocal
    from tests.test_dhl_phase4_booking import _settings_stub

    # Retain all actual auth/permission dependencies. Each HTTP request owns a
    # session, unlike conftest's in-process HTTP client (essential for races).
    async def database():
        async with TestSessionLocal() as session:
            yield session

    settings = _settings_stub()
    settings.dhl_base_url = "http://127.0.0.1:9"
    # Reset only test-owned in-memory counters between independent fixtures;
    # actual rate limits remain active within each scenario.
    from app.middleware.rate_limit import RateLimitMiddleware

    middleware = app.middleware_stack
    while middleware is not None:
        if isinstance(middleware, RateLimitMiddleware):
            middleware.requests.clear()
        middleware = getattr(middleware, "app", None)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_app_settings] = lambda: settings
    # Access logs and application logs are not evidence; never retain auth bodies.
    logging.disable(logging.CRITICAL)
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=8000, access_log=False, log_level="critical"
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if task.done():
                await task
                raise RuntimeError("API exited during startup")
            if server.started:
                break
            await asyncio.sleep(0.05)
        else:
            raise RuntimeError("API startup deadline exceeded")
        yield {"settings": settings, "provider": provider}
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        app.dependency_overrides.pop(get_app_settings, None)
        logging.disable(logging.NOTSET)


@pytest.fixture
async def make_subject(db_session, vendor_user, customer_user, runtime):
    from app.models.package_custody import OutboundShipmentIntent
    from tests.test_dhl_phase4_booking import PHASE4
    from tests.test_domestic_rate_persistence import _PACKAGE

    async def create(count=1):
        graph, package, seal, intent = await PHASE4._subject(
            db_session, vendor_user, customer_user
        )
        # Zero-ready scenario retains a genuine order graph but no ready package.
        if count == 0:
            # Use another graph with no packages; do not reverse immutable states.
            graph = await _PACKAGE._passed_graph(db_session, vendor_user, customer_user)
            packages = []
        else:
            packages = [(package, seal, intent)]
            for _ in range(count - 1):
                extra, _, _, extra_seal = await _PACKAGE._ready_package(
                    db_session, graph
                )
                extra_intent = OutboundShipmentIntent(
                    package_id=extra.id,
                    package_version=1,
                    seal_id=extra_seal.id,
                    order_id=graph["order"].id,
                    origin_hub_id=graph["hub"].id,
                    destination_name=intent.destination_name,
                    destination_phone=intent.destination_phone,
                    destination_address_line1=intent.destination_address_line1,
                    destination_city=intent.destination_city,
                    destination_state=intent.destination_state,
                    destination_postal_code=intent.destination_postal_code,
                    destination_country_code="NG",
                    source_command="prepare_outbound",
                    idempotency_key=f"http-intent-{extra.id}",
                    created_by_id=graph["operator_id"],
                    outbound_state="staged",
                )
                db_session.add(extra_intent)
                await db_session.flush()
                packages.append((extra, extra_seal, extra_intent))
            for package, seal, intent in packages:
                await PHASE4._seed_selected_dhl_quote(
                    db_session, graph, package, seal, intent, customer_user["user"]
                )
                await PHASE4._chain_custody(db_session, graph, package, seal)
        runtime["settings"].dhl_domestic_sandbox_cohort_ids = runtime[
            "settings"
        ].dhl_domestic_sandbox_cohort_ids | {graph["cohort"].id}
        await db_session.commit()
        return {
            "order": str(graph["order"].id),
            "packages": [str(p.id) for p, _, _ in packages],
            "graph": graph,
        }

    return create


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    # conftest's ownership-fenced cleanup must complete before recording proof.
    from tests.conftest import (
        TEST_DATABASE_NAME,
        RESOLVED_DB_URL,
        build_sync_database_url,
    )
    from sqlalchemy import create_engine, text

    engine = create_engine(build_sync_database_url(RESOLVED_DB_URL, "postgres"))
    with engine.connect() as connection:
        remains = connection.scalar(
            text("SELECT count(*) FROM pg_database WHERE datname=:name"),
            {"name": TEST_DATABASE_NAME},
        )
    engine.dispose()
    (EVIDENCE / "http-database-teardown.json").write_text(
        json.dumps({"owned_database_absent": remains == 0})
    )
    if remains:
        session.exitstatus = 1
