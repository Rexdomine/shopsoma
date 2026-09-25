"""Admin-curated Shop Edits association rules."""

SHOP_EDIT_SLUGS = {
    "casual": "shop-edits-occasion-wear-casual",
    "evening": "shop-edits-occasion-wear-evening",
    "party": "shop-edits-occasion-wear-party",
    "workwear": "shop-edits-occasion-wear-workwear",
}
SHOP_EDIT_NAMES = tuple(SHOP_EDIT_SLUGS)


def normalize_shop_edit_names(names: list[str] | None) -> list[str]:
    """Return a stable, deduplicated list of valid Shop Edits names."""
    values = [str(value).strip().lower() for value in (names or [])]
    invalid = [value for value in values if value not in SHOP_EDIT_SLUGS]
    if invalid:
        raise ValueError(f"Unknown Shop Edit category: {invalid[0]}")
    return list(dict.fromkeys(values))
