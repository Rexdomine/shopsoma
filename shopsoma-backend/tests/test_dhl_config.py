import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings


BASE_SETTINGS = {
    "SECRET_KEY": "unit-test-secret",
    "DATABASE_URL": "postgresql://unit:unit@localhost:5432/shopsoma_unit",
    "_env_file": None,
}


def make_settings(**overrides) -> Settings:
    cleaned_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DHL_", "CHECKOUT_CAPABILITY_", "DOMESTIC_CHECKOUT_"))
    }
    with patch.dict(os.environ, cleaned_env, clear=True):
        return Settings(**BASE_SETTINGS, **overrides)


def test_dhl_is_disabled_and_unconfigured_by_default() -> None:
    config = make_settings()

    assert config.DHL_ENABLED is False
    assert config.DHL_ENVIRONMENT == "sandbox"
    assert config.dhl_base_url == "https://express.api.dhl.com/mydhlapi/test"
    assert config.dhl_configured is False


def test_domestic_dhl_workflow_gates_are_inert_by_default() -> None:
    config = make_settings()

    assert (
        config.DHL_DOMESTIC_WORKFLOW_ENABLED,
        config.DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED,
        config.DHL_DOMESTIC_PROVIDER_CALLS_ENABLED,
    ) == (False, False, False)
    assert (
        config.DHL_DOMESTIC_QUOTE_TTL_SECONDS,
        config.DHL_DOMESTIC_PAYMENT_WINDOW_SECONDS,
        config.DHL_DOMESTIC_AUTH_GRACE_SECONDS,
    ) == (1800, 1800, 900)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("DHL_DOMESTIC_QUOTE_TTL_SECONDS", 299),
        ("DHL_DOMESTIC_QUOTE_TTL_SECONDS", 3601),
        ("DHL_DOMESTIC_PAYMENT_WINDOW_SECONDS", 299),
        ("DHL_DOMESTIC_PAYMENT_WINDOW_SECONDS", 3601),
        ("DHL_DOMESTIC_AUTH_GRACE_SECONDS", 59),
        ("DHL_DOMESTIC_AUTH_GRACE_SECONDS", 1801),
    ],
)
def test_domestic_dhl_timing_settings_reject_values_outside_safe_bounds(
    field_name: str, invalid_value: int
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        make_settings(**{field_name: invalid_value})


def test_domestic_dhl_timing_settings_accept_safe_boundaries() -> None:
    config = make_settings(
        **{
            "DHL_DOMESTIC_QUOTE_TTL_SECONDS": 300,
            "DHL_DOMESTIC_PAYMENT_WINDOW_SECONDS": 3600,
            "DHL_DOMESTIC_AUTH_GRACE_SECONDS": 60,
        }
    )

    assert (
        config.DHL_DOMESTIC_QUOTE_TTL_SECONDS,
        config.DHL_DOMESTIC_PAYMENT_WINDOW_SECONDS,
        config.DHL_DOMESTIC_AUTH_GRACE_SECONDS,
    ) == (300, 3600, 60)


def test_dhl_production_environment_uses_fixed_official_url() -> None:
    config = make_settings(DHL_ENVIRONMENT="production")

    assert config.dhl_base_url == "https://express.api.dhl.com/mydhlapi"


def test_dhl_rejects_unknown_environment() -> None:
    with pytest.raises(ValidationError, match="DHL_ENVIRONMENT"):
        make_settings(DHL_ENVIRONMENT="custom")


def test_dhl_rejects_arbitrary_base_url_override() -> None:
    with pytest.raises(ValidationError, match="DHL_BASE_URL"):
        make_settings(DHL_BASE_URL="https://example.invalid")


@pytest.mark.parametrize("timeout", [0, 0.5, 60.1])
def test_dhl_rejects_timeout_outside_safe_bounds(timeout: float) -> None:
    with pytest.raises(ValidationError, match="DHL_REQUEST_TIMEOUT_SECONDS"):
        make_settings(DHL_REQUEST_TIMEOUT_SECONDS=timeout)


def test_enabled_dhl_requires_api_credentials_and_export_account() -> None:
    with pytest.raises(ValidationError) as exc_info:
        make_settings(DHL_ENABLED=True)

    error = str(exc_info.value)
    assert "DHL_API_USERNAME" in error
    assert "DHL_API_PASSWORD" in error
    assert "DHL_EXPORT_ACCOUNT_NUMBER" in error
    assert "unit-test-secret" not in error


def test_enabled_dhl_configuration_is_ready_and_secret_safe() -> None:
    config = make_settings(
        DHL_ENABLED=True,
        DHL_API_USERNAME="dummy-api-user",
        DHL_API_PASSWORD="dummy-api-password",
        DHL_EXPORT_ACCOUNT_NUMBER="123456789",
    )

    assert config.dhl_configured is True
    representation = repr(config)
    assert "dummy-api-user" not in representation
    assert "dummy-api-password" not in representation
    assert "123456789" not in representation
