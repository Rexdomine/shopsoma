from app.services.shipping.manual_rates import manual_state_aliases


def test_manual_rate_matching_treats_fct_and_abuja_as_federal_capital_territory():
    expected = ("abuja", "fct", "federal capital territory")

    assert manual_state_aliases("FCT") == expected
    assert manual_state_aliases(" Abuja ") == expected
    assert manual_state_aliases("Federal Capital Territory") == expected


def test_manual_rate_matching_preserves_non_alias_state_normalization():
    assert manual_state_aliases(" Lagos ") == ("lagos",)
