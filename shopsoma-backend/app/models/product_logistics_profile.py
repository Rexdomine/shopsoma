"""Per-product and per-variant domestic logistics measurements."""

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLEnum,
    event,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base


class LogisticsProfileSource(str, enum.Enum):
    """How a logistics profile's measurements were obtained."""

    MANUAL = "manual"
    MEASURED = "measured"
    IMPORTED = "imported"


class LogisticsVerificationStatus(str, enum.Enum):
    """Review status for logistics measurements."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"


def _enum_values(enum_class):
    return [member.value for member in enum_class]


class ProductLogisticsProfile(Base):
    """Shipping dimensions and preparation time for a product or variant."""

    __tablename__ = "product_logistics_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_id = Column(UUID(as_uuid=True), nullable=True)
    weight_kg = Column(Numeric(7, 3), nullable=True)
    length_cm = Column(Numeric(6, 2), nullable=True)
    width_cm = Column(Numeric(6, 2), nullable=True)
    height_cm = Column(Numeric(6, 2), nullable=True)
    preparation_min_days = Column(Integer, nullable=True)
    preparation_max_days = Column(Integer, nullable=True)
    source = Column(
        SQLEnum(
            LogisticsProfileSource,
            values_callable=_enum_values,
            name="logistics_profile_source",
        ),
        nullable=False,
        default=LogisticsProfileSource.MANUAL,
        server_default=LogisticsProfileSource.MANUAL.value,
    )
    verification_status = Column(
        SQLEnum(
            LogisticsVerificationStatus,
            values_callable=_enum_values,
            name="logistics_verification_status",
        ),
        nullable=False,
        default=LogisticsVerificationStatus.PENDING,
        server_default=LogisticsVerificationStatus.PENDING.value,
    )
    verified_at = Column(DateTime(timezone=True), nullable=True)
    verified_by_id = Column(
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

    __table_args__ = (
        ForeignKeyConstraint(
            ["product_id", "variant_id"],
            ["product_variants.product_id", "product_variants.id"],
            name="fk_product_logistics_profiles_variant",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "(weight_kg IS NULL AND length_cm IS NULL AND width_cm IS NULL "
            "AND height_cm IS NULL) OR "
            "(weight_kg IS NOT NULL AND length_cm IS NOT NULL "
            "AND width_cm IS NOT NULL AND height_cm IS NOT NULL "
            "AND weight_kg > 0 AND weight_kg <= 1000 "
            "AND length_cm > 0 AND length_cm <= 1000 "
            "AND width_cm > 0 AND width_cm <= 1000 "
            "AND height_cm > 0 AND height_cm <= 1000)",
            name="ck_product_logistics_profiles_measurements",
        ),
        CheckConstraint(
            "(preparation_min_days IS NULL AND preparation_max_days IS NULL) OR "
            "(preparation_min_days IS NOT NULL "
            "AND preparation_max_days IS NOT NULL "
            "AND preparation_min_days >= 0 AND preparation_max_days >= "
            "preparation_min_days AND preparation_max_days <= 365)",
            name="ck_product_logistics_profiles_preparation_days",
        ),
        CheckConstraint(
            "version >= 1", name="ck_product_logistics_profiles_version_positive"
        ),
        CheckConstraint(
            "(verification_status = 'pending' AND verified_at IS NULL "
            "AND verified_by_id IS NULL) OR "
            "(verification_status IN ('verified', 'rejected') "
            "AND verified_at IS NOT NULL AND verified_by_id IS NOT NULL)",
            name="ck_product_logistics_profiles_verification_consistent",
        ),
        Index(
            "uq_product_logistics_profiles_product",
            "product_id",
            unique=True,
            postgresql_where=text("variant_id IS NULL"),
        ),
        Index(
            "uq_product_logistics_profiles_variant",
            "product_id",
            "variant_id",
            unique=True,
            postgresql_where=text("variant_id IS NOT NULL"),
        ),
    )
    __mapper_args__ = {
        "version_id_col": version,
        "version_id_generator": False,
    }


@event.listens_for(ProductLogisticsProfile, "before_update")
def _increment_profile_version(_mapper, _connection, target) -> None:
    """Increment the lock token while preserving explicit invalid inserts."""
    target.version += 1
