"""Focused persistence tests for domestic fulfillment hubs and product logistics."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import delete, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.core.base import Base
from app.models import (
    FulfillmentHub,
    LogisticsProfileSource,
    LogisticsVerificationStatus,
    ProductLogisticsProfile,
)
from app.models.product import Product, ProductVariant
from app.models.user import User


async def _rejects(db_session, instance) -> None:
    """Assert that PostgreSQL rejects an invalid row without poisoning the test."""
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(instance)
            await db_session.flush()


def _hub(**overrides) -> FulfillmentHub:
    values = {
        "code": f"lagos-{uuid.uuid4().hex[:8]}",
        "name": "Lagos Fulfillment Hub",
        "contact_name": "Operations Team",
        "contact_phone": "+2348000000000",
        "address_line1": "1 Test Street",
        "city": "Lagos",
        "state": "Lagos",
        "cutoff_time": time(14, 30),
    }
    values.update(overrides)
    return FulfillmentHub(**values)


def _profile(product_id, **overrides) -> ProductLogisticsProfile:
    values = {"product_id": product_id}
    values.update(overrides)
    return ProductLogisticsProfile(**values)


def test_models_and_enums_are_registered_in_public_models_module() -> None:
    assert Base.metadata.tables["fulfillment_hubs"] is FulfillmentHub.__table__
    assert (
        Base.metadata.tables["product_logistics_profiles"]
        is ProductLogisticsProfile.__table__
    )
    assert {member.value for member in LogisticsProfileSource} == {
        "manual",
        "measured",
        "imported",
    }
    assert {member.value for member in LogisticsVerificationStatus} == {
        "pending",
        "verified",
        "rejected",
    }
    assert FulfillmentHub.__mapper__.version_id_generator is False
    assert ProductLogisticsProfile.__mapper__.version_id_generator is False


def test_hub_activation_constraints_preserve_history_after_deactivation() -> None:
    """Inactive hubs may retain paired activation audit, but active hubs need it."""
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in FulfillmentHub.__table__.constraints
        if hasattr(constraint, "sqltext")
    }
    assert constraints["ck_fulfillment_hubs_activation_audit_paired"] == (
        "(activated_at IS NULL AND activated_by_id IS NULL) OR "
        "(activated_at IS NOT NULL AND activated_by_id IS NOT NULL)"
    )
    assert constraints["ck_fulfillment_hubs_active_has_audit"] == (
        "NOT is_active OR (activated_at IS NOT NULL AND activated_by_id IS NOT NULL)"
    )


def test_schema_has_no_carrier_vendor_or_customs_persistence() -> None:
    hub_columns = set(FulfillmentHub.__table__.columns.keys())
    profile_columns = set(ProductLogisticsProfile.__table__.columns.keys())
    forbidden = {
        "carrier",
        "provider",
        "credentials",
        "account_number",
        "vendor_id",
        "customs",
        "hs_code",
    }
    assert not hub_columns.intersection(forbidden)
    assert not profile_columns.intersection(forbidden)

    variant_fk = next(
        fk
        for fk in ProductLogisticsProfile.__table__.foreign_key_constraints
        if {column.name for column in fk.columns} == {"product_id", "variant_id"}
    )
    assert [element.target_fullname for element in variant_fk.elements] == [
        "product_variants.product_id",
        "product_variants.id",
    ]
    assert variant_fk.ondelete == "CASCADE"


@pytest.mark.asyncio
async def test_hub_safe_defaults_decimal_versioning_and_audit(db_session, vendor_user):
    hub = _hub()
    db_session.add(hub)
    await db_session.flush()
    await db_session.refresh(hub)

    assert hub.country_code == "NG"
    assert hub.timezone == "Africa/Lagos"
    assert hub.is_active is False
    assert hub.version == 1
    assert hub.created_at.tzinfo is not None
    assert hub.updated_at.tzinfo is not None
    assert inspect(FulfillmentHub).version_id_col is FulfillmentHub.__table__.c.version

    activated = _hub(
        is_active=True,
        activated_at=datetime.now(timezone.utc),
        activated_by_id=vendor_user["user"].id,
    )
    db_session.add(activated)
    await db_session.flush()
    assert activated.activated_at.tzinfo is not None

    activated.is_active = False
    await db_session.flush()
    assert activated.activated_at is not None
    assert activated.activated_by_id == vendor_user["user"].id


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["clear", "replace"])
async def test_hub_activation_audit_is_immutable_after_expiry(
    db_session, vendor_user, mutation
):
    recorded_at = datetime.now(timezone.utc)
    hub = _hub(
        is_active=True,
        activated_at=recorded_at,
        activated_by_id=vendor_user["user"].id,
    )
    db_session.add(hub)
    await db_session.commit()
    db_session.expire(hub, ["activated_at", "activated_by_id"])

    if mutation == "clear":
        hub.activated_at = None
        hub.activated_by_id = None
    else:
        hub.activated_at = recorded_at + timedelta(seconds=1)

    with pytest.raises(ValueError, match="activation audit is immutable"):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"code": ""},
        {"code": " Not-Canonical "},
        {"name": "   "},
        {"contact_name": ""},
        {"contact_phone": "\t"},
        {"address_line1": ""},
        {"city": ""},
        {"state": ""},
        {"country_code": "US"},
        {"timezone": "UTC"},
        {"cutoff_time": None},
        {"is_active": True},
        {"version": 0},
    ],
)
async def test_hub_rejects_invalid_domestic_or_audit_state(db_session, overrides):
    await _rejects(db_session, _hub(**overrides))


@pytest.mark.asyncio
async def test_hub_code_is_unique_and_audit_user_delete_is_restricted(
    db_session, vendor_user
):
    code = f"unique-{uuid.uuid4().hex[:8]}"
    db_session.add(_hub(code=code))
    await db_session.flush()
    await _rejects(db_session, _hub(code=code))

    hub = _hub(
        is_active=True,
        activated_at=datetime.now(timezone.utc),
        activated_by_id=vendor_user["user"].id,
    )
    db_session.add(hub)
    await db_session.flush()
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                delete(User).where(User.id == vendor_user["user"].id)
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_product_and_canonical_variant_profiles_round_trip_decimal(
    db_session, sample_product
):
    variant = ProductVariant(
        product_id=sample_product.id,
        size="M",
        color="Blue",
        price=Decimal("125.00"),
        stock=2,
    )
    db_session.add(variant)
    await db_session.flush()

    product_profile = _profile(
        sample_product.id,
        weight_kg=Decimal("1.250"),
        length_cm=Decimal("30.50"),
        width_cm=Decimal("20.25"),
        height_cm=Decimal("10.75"),
        preparation_min_days=0,
        preparation_max_days=2,
        source=LogisticsProfileSource.MEASURED,
    )
    variant_profile = _profile(sample_product.id, variant_id=variant.id)
    db_session.add_all([product_profile, variant_profile])
    await db_session.flush()
    product_profile_id = product_profile.id
    db_session.expire(product_profile)
    loaded = await db_session.scalar(
        select(ProductLogisticsProfile).where(
            ProductLogisticsProfile.id == product_profile_id
        )
    )

    assert loaded.weight_kg == Decimal("1.250")
    assert loaded.length_cm == Decimal("30.50")
    assert loaded.preparation_min_days == 0
    assert loaded.source is LogisticsProfileSource.MEASURED
    assert loaded.verification_status is LogisticsVerificationStatus.PENDING
    assert loaded.version == 1
    assert inspect(ProductLogisticsProfile).version_id_col is loaded.__table__.c.version


@pytest.mark.asyncio
async def test_hub_and_profile_reject_stale_concurrent_updates(
    db_session, sample_product
):
    hub = _hub()
    profile = _profile(sample_product.id)
    db_session.add_all([hub, profile])
    await db_session.commit()

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    for model, row_id in (
        (FulfillmentHub, hub.id),
        (ProductLogisticsProfile, profile.id),
    ):
        async with sessions() as first, sessions() as stale:
            current_row = await first.get(model, row_id)
            stale_row = await stale.get(model, row_id)
            if model is FulfillmentHub:
                current_row.name = "Updated Hub"
                stale_row.name = "Stale Hub"
            else:
                current_row.preparation_min_days = 1
                current_row.preparation_max_days = 2
                stale_row.preparation_min_days = 1
                stale_row.preparation_max_days = 3

            await first.commit()
            assert current_row.version == 2
            with pytest.raises(StaleDataError):
                await stale.commit()
            await stale.rollback()


@pytest.mark.asyncio
async def test_profile_nullable_uniqueness_and_cross_product_variant_binding(
    db_session, sample_product, vendor_user
):
    other = Product(
        vendor_id=vendor_user["vendor"].id,
        title="Other product",
        base_price=Decimal("10.00"),
    )
    db_session.add(other)
    await db_session.flush()
    variant = ProductVariant(
        product_id=other.id,
        size="S",
        color="Black",
        price=Decimal("10.00"),
        stock=1,
    )
    db_session.add(variant)
    await db_session.flush()

    db_session.add(_profile(sample_product.id))
    await db_session.flush()
    await _rejects(db_session, _profile(sample_product.id))
    await _rejects(
        db_session,
        _profile(sample_product.id, variant_id=variant.id),
    )

    first_variant_profile = _profile(other.id, variant_id=variant.id)
    db_session.add(first_variant_profile)
    await db_session.flush()
    await _rejects(db_session, _profile(other.id, variant_id=variant.id))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"weight_kg": Decimal("1")},
        {
            "weight_kg": Decimal("0"),
            "length_cm": Decimal("1"),
            "width_cm": Decimal("1"),
            "height_cm": Decimal("1"),
        },
        {
            "weight_kg": Decimal("1000.001"),
            "length_cm": Decimal("1"),
            "width_cm": Decimal("1"),
            "height_cm": Decimal("1"),
        },
        {
            "weight_kg": Decimal("1"),
            "length_cm": Decimal("1000.01"),
            "width_cm": Decimal("1"),
            "height_cm": Decimal("1"),
        },
        {"preparation_min_days": 0},
        {"preparation_min_days": -1, "preparation_max_days": 1},
        {"preparation_min_days": 4, "preparation_max_days": 3},
        {"preparation_min_days": 0, "preparation_max_days": 366},
        {"version": 0},
    ],
)
async def test_profile_rejects_invalid_measurements_prep_or_version(
    db_session, sample_product, overrides
):
    await _rejects(db_session, _profile(sample_product.id, **overrides))


@pytest.mark.asyncio
async def test_verification_consistency_and_audit_delete_restriction(
    db_session, sample_product, vendor_user
):
    now = datetime.now(timezone.utc)
    await _rejects(
        db_session,
        _profile(
            sample_product.id,
            verification_status=LogisticsVerificationStatus.VERIFIED,
        ),
    )
    await _rejects(
        db_session,
        _profile(
            sample_product.id,
            verified_at=now,
            verified_by_id=vendor_user["user"].id,
        ),
    )

    profile = _profile(
        sample_product.id,
        verification_status=LogisticsVerificationStatus.REJECTED,
        verified_at=now,
        verified_by_id=vendor_user["user"].id,
    )
    db_session.add(profile)
    await db_session.flush()
    assert profile.verified_at.tzinfo is not None
    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.execute(
                delete(User).where(User.id == vendor_user["user"].id)
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_product_and_variant_deletes_cascade_profiles(db_session, sample_product):
    variant = ProductVariant(
        product_id=sample_product.id,
        size="L",
        color="Green",
        price=Decimal("20.00"),
        stock=1,
    )
    db_session.add(variant)
    await db_session.flush()
    product_profile = _profile(sample_product.id)
    variant_profile = _profile(sample_product.id, variant_id=variant.id)
    db_session.add_all([product_profile, variant_profile])
    await db_session.flush()
    product_profile_id = product_profile.id
    variant_profile_id = variant_profile.id
    sample_product_id = sample_product.id

    await db_session.execute(
        delete(ProductVariant).where(ProductVariant.id == variant.id)
    )
    await db_session.flush()
    db_session.expire_all()
    assert await db_session.get(ProductLogisticsProfile, variant_profile_id) is None
    assert await db_session.get(ProductLogisticsProfile, product_profile_id) is not None

    await db_session.execute(delete(Product).where(Product.id == sample_product_id))
    await db_session.flush()
    db_session.expire_all()
    assert await db_session.get(ProductLogisticsProfile, product_profile_id) is None
