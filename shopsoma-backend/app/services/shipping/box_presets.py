"""ShopSoma standard shipping box presets (admin-configurable).

The hub packs orders into a small set of standard boxes. Each preset stores the
box's external dimensions and empty (tare) weight so admins only need to pick a
box and read the scale. Presets live in ``app_settings`` under
``shipping_box_presets`` and fall back to the defaults below until an admin
saves ShopSoma's real box catalogue.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.services.dhl.parcel_limits import ParcelValidationError, normalize_dhl_parcel

SHIPPING_BOX_PRESETS_KEY = "shipping_box_presets"
_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,49}$")


class ShippingBoxPreset(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=80)
    length_cm: Decimal = Field(..., gt=0)
    width_cm: Decimal = Field(..., gt=0)
    height_cm: Decimal = Field(..., gt=0)
    tare_weight_kg: Decimal = Field(Decimal("0"), ge=0, le=20)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _canonical_code(cls, value: str) -> str:
        code = value.strip().upper()
        if not _CODE_RE.fullmatch(code):
            raise ValueError("code may only contain A-Z, 0-9, '-' and '_'")
        return code

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("name is required")
        return name

    @model_validator(mode="after")
    def _within_dhl_limits(self) -> "ShippingBoxPreset":
        try:
            parcel = normalize_dhl_parcel(
                max(self.tare_weight_kg, Decimal("0.01")),
                self.length_cm,
                self.width_cm,
                self.height_cm,
            )
        except ParcelValidationError as exc:
            raise ValueError(f"box {self.code}: {exc}") from None
        self.length_cm, self.width_cm, self.height_cm = (
            parcel.length_cm,
            parcel.width_cm,
            parcel.height_cm,
        )
        return self


class ShippingBoxPresetList(BaseModel):
    presets: list[ShippingBoxPreset] = Field(..., min_length=1, max_length=30)

    @model_validator(mode="after")
    def _unique_codes(self) -> "ShippingBoxPresetList":
        codes = [preset.code for preset in self.presets]
        if len(codes) != len(set(codes)):
            raise ValueError("box codes must be unique")
        if not any(preset.is_active for preset in self.presets):
            raise ValueError("at least one box must be active")
        return self


# Placeholder catalogue until ShopSoma saves its real boxes in Admin settings.
DEFAULT_BOX_PRESETS: tuple[ShippingBoxPreset, ...] = (
    ShippingBoxPreset(code="SS-MAILER", name="Mailer bag (small)", length_cm=Decimal("35"), width_cm=Decimal("25"), height_cm=Decimal("4"), tare_weight_kg=Decimal("0.05")),
    ShippingBoxPreset(code="SS-S", name="Small box", length_cm=Decimal("30"), width_cm=Decimal("22"), height_cm=Decimal("10"), tare_weight_kg=Decimal("0.20")),
    ShippingBoxPreset(code="SS-M", name="Medium box", length_cm=Decimal("40"), width_cm=Decimal("30"), height_cm=Decimal("15"), tare_weight_kg=Decimal("0.35")),
    ShippingBoxPreset(code="SS-L", name="Large box", length_cm=Decimal("50"), width_cm=Decimal("40"), height_cm=Decimal("25"), tare_weight_kg=Decimal("0.60")),
    ShippingBoxPreset(code="SS-XL", name="Extra-large box", length_cm=Decimal("60"), width_cm=Decimal("45"), height_cm=Decimal("35"), tare_weight_kg=Decimal("0.90")),
)


async def load_box_presets(db: AsyncSession) -> tuple[list[ShippingBoxPreset], bool]:
    """Return ``(presets, is_default)``; invalid stored JSON falls back to defaults."""
    raw = await db.scalar(
        select(AppSetting.value).where(AppSetting.key == SHIPPING_BOX_PRESETS_KEY)
    )
    if raw:
        try:
            return ShippingBoxPresetList.model_validate({"presets": json.loads(raw)}).presets, False
        except (ValueError, TypeError):
            pass
    return [preset.model_copy() for preset in DEFAULT_BOX_PRESETS], True


async def save_box_presets(
    db: AsyncSession, presets: ShippingBoxPresetList, *, actor_id: object
) -> list[ShippingBoxPreset]:
    await db.execute(text("SELECT pg_advisory_xact_lock(736401, 2)"))
    row = await db.scalar(select(AppSetting).where(AppSetting.key == SHIPPING_BOX_PRESETS_KEY))
    if row is None:
        row = AppSetting(key=SHIPPING_BOX_PRESETS_KEY, value_type="json")
        db.add(row)
    row.value = json.dumps([preset.model_dump(mode="json") for preset in presets.presets])
    row.description = f"Shipping box presets updated by admin {actor_id}"
    await db.flush()
    return presets.presets


async def find_box_preset(db: AsyncSession, code: str | None) -> ShippingBoxPreset | None:
    if not code:
        return None
    presets, _ = await load_box_presets(db)
    wanted = code.strip().upper()
    return next((preset for preset in presets if preset.code == wanted), None)
