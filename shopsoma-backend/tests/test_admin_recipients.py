from app.api.v1.orders import _build_admin_recipients
from app.core.config import settings
from app.models.user import User, UserRole


def test_build_admin_recipients_adds_default_admin_email(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@example.com")

    user = User(email="admin2@example.com", full_name="Admin Two", role=UserRole.ADMIN)
    recipients = _build_admin_recipients([user])

    emails = {recipient["email"] for recipient in recipients}
    assert emails == {"admin2@example.com", "admin@example.com"}


def test_build_admin_recipients_avoids_duplicate_admin_email(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAIL", "admin@example.com")

    user = User(email="admin@example.com", full_name="Admin One", role=UserRole.ADMIN)
    recipients = _build_admin_recipients([user])

    emails = [recipient["email"] for recipient in recipients]
    assert emails == ["admin@example.com"]
