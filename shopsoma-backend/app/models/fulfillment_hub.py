"""Domestic fulfillment hub persistence model."""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    event,
    ForeignKey,
    Integer,
    inspect,
    select,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base


class FulfillmentHub(Base):
    """An operational domestic fulfillment location."""

    __tablename__ = "fulfillment_hubs"
    __table_args__ = (
        CheckConstraint(
            "code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_fulfillment_hubs_code_canonical",
        ),
        CheckConstraint(
            "name ~ '[^[:space:]]'", name="ck_fulfillment_hubs_name_present"
        ),
        CheckConstraint(
            "contact_name ~ '[^[:space:]]'",
            name="ck_fulfillment_hubs_contact_name_present",
        ),
        CheckConstraint(
            "contact_phone ~ '[^[:space:]]'",
            name="ck_fulfillment_hubs_contact_phone_present",
        ),
        CheckConstraint(
            "address_line1 ~ '[^[:space:]]'",
            name="ck_fulfillment_hubs_address_line1_present",
        ),
        CheckConstraint(
            "city ~ '[^[:space:]]'", name="ck_fulfillment_hubs_city_present"
        ),
        CheckConstraint(
            "state ~ '[^[:space:]]'", name="ck_fulfillment_hubs_state_present"
        ),
        CheckConstraint("country_code = 'NG'", name="ck_fulfillment_hubs_country_ng"),
        CheckConstraint(
            "timezone = 'Africa/Lagos'", name="ck_fulfillment_hubs_timezone_lagos"
        ),
        CheckConstraint("version >= 1", name="ck_fulfillment_hubs_version_positive"),
        CheckConstraint(
            "(activated_at IS NULL AND activated_by_id IS NULL) OR "
            "(activated_at IS NOT NULL AND activated_by_id IS NOT NULL)",
            name="ck_fulfillment_hubs_activation_audit_paired",
        ),
        CheckConstraint(
            "NOT is_active OR (activated_at IS NOT NULL AND activated_by_id IS NOT NULL)",
            name="ck_fulfillment_hubs_active_has_audit",
        ),
        UniqueConstraint("code", name="uq_fulfillment_hubs_code"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(100), nullable=False)
    name = Column(String(255), nullable=False)
    contact_name = Column(String(255), nullable=False)
    contact_phone = Column(String(32), nullable=False)
    address_line1 = Column(String(255), nullable=False)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    postal_code = Column(String(20), nullable=True)
    country_code = Column(String(2), nullable=False, default="NG", server_default="NG")
    timezone = Column(
        String(64),
        nullable=False,
        default="Africa/Lagos",
        server_default="Africa/Lagos",
    )
    cutoff_time = Column(Time, nullable=False)
    is_active = Column(Boolean, nullable=False, default=False, server_default="false")
    activated_at = Column(DateTime(timezone=True), nullable=True)
    activated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": False,
    }


@event.listens_for(FulfillmentHub, "before_update")
def _increment_hub_version(_mapper, _connection, target) -> None:
    """Preserve activation audit and increment the optimistic lock token."""
    state = inspect(target)
    audit_changed = any(
        state.attrs[field_name].history.has_changes()
        for field_name in ("activated_at", "activated_by_id")
    )
    if audit_changed:
        persisted = _connection.execute(
            select(FulfillmentHub.activated_at, FulfillmentHub.activated_by_id).where(
                FulfillmentHub.id == target.id
            )
        ).one()
        current_activated_at = state.dict.get("activated_at", persisted.activated_at)
        current_activated_by_id = state.dict.get(
            "activated_by_id", persisted.activated_by_id
        )
        if persisted.activated_at is not None and (
            current_activated_at != persisted.activated_at
            or current_activated_by_id != persisted.activated_by_id
        ):
            raise ValueError("hub activation audit is immutable once recorded")
    target.version += 1
