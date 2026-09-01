"""Milestone 2 guest capability persistence/config contract only."""


def test_capability_config_is_empty_and_inactive_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", raising=False)
    monkeypatch.delenv("CHECKOUT_CAPABILITY_ACTIVE_PEPPER", raising=False)
    monkeypatch.delenv("CHECKOUT_CAPABILITY_PREVIOUS_PEPPER_VERSION", raising=False)
    monkeypatch.delenv("CHECKOUT_CAPABILITY_PREVIOUS_PEPPER", raising=False)
    from app.core.config import Settings

    settings = Settings()
    assert settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION is None
    assert settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER.get_secret_value() == ""
    assert settings.checkout_capability_configured is False
