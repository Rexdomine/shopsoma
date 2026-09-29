"""Request validation must match the persisted bank-name column limit."""
import pytest
from pydantic import ValidationError

from app.api.v1.vendor_payment_methods import PaymentMethodCreate
from app.schemas.vendor import VendorPayoutInfoUpdate


@pytest.mark.parametrize('schema', [PaymentMethodCreate, VendorPayoutInfoUpdate])
@pytest.mark.parametrize('bank_name', ['Providus Bank', 'B' * 100])
def test_bank_name_within_limit(schema, bank_name):
    request = schema(bank_name=bank_name, account_type='Savings',
                     account_number='1234567890', account_holder='Test Vendor')
    assert request.bank_name == bank_name


@pytest.mark.parametrize('schema', [PaymentMethodCreate, VendorPayoutInfoUpdate])
def test_bank_name_over_limit(schema):
    with pytest.raises(ValidationError) as exc:
        schema(bank_name='B' * 101, account_type='Savings',
               account_number='1234567890', account_holder='Test Vendor')
    assert exc.value.errors()[0]['loc'] == ('bank_name',)
    assert exc.value.errors()[0]['type'] == 'string_too_long'
