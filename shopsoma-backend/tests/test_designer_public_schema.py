"""Public response contract; runnable without a database via unittest discovery."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from pydantic import ValidationError
from app.schemas.vendor import DesignerResponse

class DesignerPublicSchemaTests(unittest.TestCase):
    def record(self, **fields):
        return SimpleNamespace(id=uuid4(), business_name='Studio', logo_url=None,
            total_products=0, total_orders=0, created_at=datetime.now(timezone.utc), **fields)

    def test_existing_records_keep_compatible_defaults(self):
        result=DesignerResponse.model_validate(self.record())
        self.assertIsNone(result.business_description)
        self.assertFalse(result.is_featured_storefront)

    def test_serializes_only_public_brand_fields(self):
        result=DesignerResponse.model_validate(self.record(business_description='Crafted locally',
            featured_storefront_image_url='https://example.com/campaign.jpg', is_featured_storefront=True,
            bank_account_number='private', email='private@example.com')).model_dump()
        self.assertEqual(result['business_description'], 'Crafted locally')
        self.assertTrue(result['is_featured_storefront'])
        self.assertNotIn('bank_account_number',result)
        self.assertNotIn('email',result)

    def test_invalid_vendor_id_is_rejected(self):
        record=self.record(); record.id='invalid'
        with self.assertRaises(ValidationError): DesignerResponse.model_validate(record)
