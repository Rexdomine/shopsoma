from app.services.shop_edits import normalize_shop_edit_names


def test_shop_edit_names_are_deduplicated_and_stable():
    assert normalize_shop_edit_names(["Party", "casual", "party"]) == ["party", "casual"]


def test_shop_edit_names_reject_unknown_categories():
    try:
        normalize_shop_edit_names(["seasonal"])
    except ValueError as exc:
        assert "Unknown Shop Edit category" in str(exc)
    else:
        raise AssertionError("unknown category must be rejected")
