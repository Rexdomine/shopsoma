from dataclasses import asdict

import pytest

from app.core.config import Settings
from app.services.shipping.capabilities import domestic_shipping_capabilities


BASE_SETTINGS = {
    "SECRET_KEY": "unit-test-secret",
    "DATABASE_URL": "postgresql://unit:password@localhost:5432/shopsoma_unit",
    "_env_file": None,
}


def make_settings(**overrides) -> Settings:
    return Settings(**BASE_SETTINGS, **overrides)


def test_all_domestic_shipping_capabilities_are_false_by_default() -> None:
    capabilities = domestic_shipping_capabilities(make_settings())

    assert asdict(capabilities) == {
        "workflow_enabled": False,
        "quote_enforcement_enabled": False,
        "provider_calls_enabled": False,
        "checkout_enabled": False,
    }


def test_workflow_can_be_enabled_inertly_without_credentials() -> None:
    capabilities = domestic_shipping_capabilities(
        make_settings(DHL_DOMESTIC_WORKFLOW_ENABLED=True)
    )

    assert capabilities.workflow_enabled is True
    assert capabilities.quote_enforcement_enabled is False
    assert capabilities.provider_calls_enabled is False


def test_quote_enforcement_requires_workflow_but_not_credentials() -> None:
    without_workflow = domestic_shipping_capabilities(
        make_settings(DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED=True)
    )
    with_workflow = domestic_shipping_capabilities(
        make_settings(
            DHL_DOMESTIC_WORKFLOW_ENABLED=True,
            DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED=True,
        )
    )

    assert without_workflow.quote_enforcement_enabled is False
    assert with_workflow.quote_enforcement_enabled is True
    assert with_workflow.provider_calls_enabled is False


@pytest.mark.parametrize(
    "settings_overrides",
    [
        {"DHL_DOMESTIC_PROVIDER_CALLS_ENABLED": True},
        {
            "DHL_DOMESTIC_WORKFLOW_ENABLED": True,
            "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED": True,
        },
    ],
)
def test_provider_calls_fail_closed_without_all_prerequisites(
    settings_overrides,
) -> None:
    capabilities = domestic_shipping_capabilities(make_settings(**settings_overrides))

    assert capabilities.provider_calls_enabled is False


def test_provider_calls_require_workflow_gate_and_configured_dhl() -> None:
    dhl_credentials = {
        "DHL_ENABLED": True,
        "DHL_API_USERNAME": "dummy-api-user",
        "DHL_API_PASSWORD": "dummy-api-password",
        "DHL_EXPORT_ACCOUNT_NUMBER": "123456789",
        "DHL_DOMESTIC_SANDBOX_COHORT_IDS": "22222222-2222-4222-8222-222222222222",
    }
    without_workflow = domestic_shipping_capabilities(
        make_settings(
            **dhl_credentials,
            DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        )
    )
    enabled = domestic_shipping_capabilities(
        make_settings(
            **dhl_credentials,
            DHL_DOMESTIC_WORKFLOW_ENABLED=True,
            DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        )
    )

    assert without_workflow.provider_calls_enabled is False
    assert enabled.provider_calls_enabled is True
    assert enabled.checkout_enabled is False


def test_checkout_calls_require_the_dedicated_activation_gate() -> None:
    credentials = {
        "DHL_ENABLED": True,
        "DHL_API_USERNAME": "dummy-api-user",
        "DHL_API_PASSWORD": "dummy-api-password",
        "DHL_EXPORT_ACCOUNT_NUMBER": "123456789",
        "DHL_DOMESTIC_WORKFLOW_ENABLED": True,
        "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED": True,
        "DHL_DOMESTIC_SANDBOX_COHORT_IDS": "22222222-2222-4222-8222-222222222222",
    }
    disabled = domestic_shipping_capabilities(make_settings(**credentials))
    enabled = domestic_shipping_capabilities(
        make_settings(**credentials, DHL_DOMESTIC_CHECKOUT_ENABLED=True)
    )

    assert disabled.provider_calls_enabled is True
    assert disabled.checkout_enabled is False
    assert enabled.checkout_enabled is True


def test_provider_calls_fail_closed_in_production_with_all_gates_and_config() -> None:
    capabilities = domestic_shipping_capabilities(
        make_settings(
            DHL_ENABLED=True,
            DHL_ENVIRONMENT="production",
            DHL_API_USERNAME="dummy-api-user",
            DHL_API_PASSWORD="dummy-api-password",
            DHL_EXPORT_ACCOUNT_NUMBER="dummy-account-number",
            DHL_DOMESTIC_WORKFLOW_ENABLED=True,
            DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED=True,
            DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        )
    )

    assert capabilities.workflow_enabled is True
    assert capabilities.quote_enforcement_enabled is True
    assert capabilities.provider_calls_enabled is False


def test_capability_output_contains_only_booleans_and_no_dhl_details() -> None:
    capabilities = domestic_shipping_capabilities(
        make_settings(
            DHL_ENABLED=True,
            DHL_API_USERNAME="dummy-api-user",
            DHL_API_PASSWORD="dummy-api-password",
            DHL_EXPORT_ACCOUNT_NUMBER="dummy-account-number",
            DHL_ENVIRONMENT="production",
            DHL_DOMESTIC_WORKFLOW_ENABLED=True,
            DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        )
    )
    output = asdict(capabilities)

    assert output
    assert all(type(value) is bool for value in output.values())
    assert "dummy-api-user" not in repr(capabilities)
    assert "dummy-api-password" not in repr(capabilities)
    assert "123456789" not in repr(capabilities)
    assert "production" not in repr(capabilities)
