"""
Unit tests for Product CRUD API endpoints
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestProductCreate:
    """Test product creation endpoint"""

    @pytest.mark.asyncio
    async def test_create_product_success(self, client: AsyncClient, vendor_user):
        """Test successful product creation"""
        product_data = {
            "title": "African Print Dress",
            "description": "Beautiful handmade dress with traditional African prints",
            "base_price": 75.50,
            "total_stock": 50,
            "status": "draft"
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == product_data["title"]
        assert float(data["base_price"]) == product_data["base_price"]
        assert data["vendor_id"] == str(vendor_user["vendor"].id)
        assert data["status"] == "draft"
        assert data["moderation_status"] == "pending"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_product_defaults_to_non_public_state_even_if_vendor_submits_active(
        self,
        client: AsyncClient,
        vendor_user,
    ):
        """New vendor products should not become storefront-visible on creation."""
        response = await client.post(
            "/api/v1/products",
            json={
                "title": "Queued Product",
                "base_price": 120.00,
                "status": "active",
            },
            headers=vendor_user["headers"],
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert data["moderation_status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_product_with_variants(self, client: AsyncClient, vendor_user):
        """Test product creation with variants"""
        product_data = {
            "title": "Ankara Dress",
            "description": "Available in multiple sizes and colors",
            "base_price": 85.00,
            "variants": [
                {
                    "size": "M",
                    "color": "Red",
                    "color_hex": "#FF0000",
                    "price": 85.00,
                    "stock": 10
                },
                {
                    "size": "L",
                    "color": "Blue",
                    "color_hex": "#0000FF",
                    "price": 90.00,
                    "stock": 15
                }
            ]
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["variants"]) == 2
        assert data["variants"][0]["size"] == "M"
        assert data["variants"][1]["size"] == "L"

    @pytest.mark.asyncio
    async def test_create_product_with_images(self, client: AsyncClient, vendor_user):
        """Test product creation with images"""
        product_data = {
            "title": "Test Product",
            "base_price": 50.00,
            "images": [
                {
                    "image_url": "https://example.com/image1.jpg",
                    "alt_text": "Front view",
                    "is_primary": True,
                    "display_order": 0
                },
                {
                    "image_url": "https://example.com/image2.jpg",
                    "alt_text": "Back view",
                    "display_order": 1
                }
            ]
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["images"]) == 2
        assert data["images"][0]["is_primary"] is True

    @pytest.mark.asyncio
    async def test_create_product_invalid_price(self, client: AsyncClient, vendor_user):
        """Test product creation with invalid price"""
        product_data = {
            "title": "Test Product",
            "base_price": -10.00  # Invalid negative price
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 422  # Validation error


class TestVendorProductView:
    """Test vendor product view endpoint"""

    @pytest.mark.asyncio
    async def test_vendor_can_view_own_product(
        self,
        client: AsyncClient,
        vendor_user,
        sample_product
    ):
        response = await client.get(
            f"/api/v1/vendor/products/{sample_product.id}",
            headers=vendor_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_product.id)
        assert data["vendor_id"] == str(vendor_user["vendor"].id)

    @pytest.mark.asyncio
    async def test_vendor_can_list_pending_products(
        self,
        client: AsyncClient,
        vendor_user,
        db_session: AsyncSession,
    ):
        """Vendor dashboard should retain access to pending products."""
        from app.models.product import Product, ProductStatus, ModerationStatus
        import uuid

        pending_product = Product(
            id=uuid.uuid4(),
            vendor_id=vendor_user["vendor"].id,
            title="Pending Vendor Product",
            base_price=70.00,
            total_stock=4,
            status=ProductStatus.DRAFT,
            moderation_status=ModerationStatus.PENDING,
        )
        db_session.add(pending_product)
        await db_session.commit()

        response = await client.get(
            "/api/v1/vendor/products",
            headers=vendor_user["headers"],
        )

        assert response.status_code == 200
        data = response.json()
        returned_ids = {item["id"] for item in data["products"]}
        assert str(pending_product.id) in returned_ids

    @pytest.mark.asyncio
    async def test_create_product_unauthorized(self, client: AsyncClient):
        """Test product creation without authentication"""
        product_data = {
            "title": "Test Product",
            "base_price": 50.00
        }

        response = await client.post("/api/v1/products", json=product_data)
        assert response.status_code == 403  # HTTPBearer returns 403 for missing auth

    @pytest.mark.asyncio
    async def test_create_product_as_customer(self, client: AsyncClient, customer_user):
        """Test product creation as customer (should fail)"""
        product_data = {
            "title": "Test Product",
            "base_price": 50.00
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=customer_user["headers"]
        )

        assert response.status_code == 403


class TestProductList:
    """Test product listing endpoint"""

    @pytest.mark.asyncio
    async def test_list_products_public(self, client: AsyncClient, sample_product):
        """Test public product listing"""
        response = await client.get("/api/v1/products")

        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert "total" in data
        assert "page" in data
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_products_public_excludes_unapproved_products(
        self,
        client: AsyncClient,
        vendor_user,
        db_session: AsyncSession,
    ):
        """Pending moderation products must not appear on storefront listings."""
        from app.models.product import Product, ProductStatus, ModerationStatus
        import uuid

        hidden_product = Product(
            id=uuid.uuid4(),
            vendor_id=vendor_user["vendor"].id,
            title="Pending Storefront Product",
            base_price=89.00,
            total_stock=2,
            status=ProductStatus.ACTIVE,
            moderation_status=ModerationStatus.PENDING,
        )
        db_session.add(hidden_product)
        await db_session.commit()

        response = await client.get("/api/v1/products")

        assert response.status_code == 200
        data = response.json()
        returned_ids = {item["id"] for item in data["products"]}
        assert str(hidden_product.id) not in returned_ids

    @pytest.mark.asyncio
    async def test_list_products_with_search(self, client: AsyncClient, sample_product):
        """Test product search"""
        response = await client.get("/api/v1/products?search=Test")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert "Test" in data["products"][0]["title"]

    @pytest.mark.asyncio
    async def test_list_products_with_price_filter(self, client: AsyncClient, sample_product):
        """Test price filtering"""
        response = await client.get("/api/v1/products?min_price=50&max_price=150")

        assert response.status_code == 200
        data = response.json()
        for product in data["products"]:
            assert 50 <= float(product["base_price"]) <= 150

    @pytest.mark.asyncio
    async def test_list_products_pagination(self, client: AsyncClient, sample_product):
        """Test pagination"""
        response = await client.get("/api/v1/products?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["products"]) <= 10

    @pytest.mark.asyncio
    async def test_list_products_sorting(self, client: AsyncClient, sample_product):
        """Test sorting"""
        response = await client.get("/api/v1/products?sort_by=base_price&sort_order=asc")

        assert response.status_code == 200
        data = response.json()
        if len(data["products"]) > 1:
            prices = [float(p["base_price"]) for p in data["products"]]
            assert prices == sorted(prices)

    @pytest.mark.asyncio
    async def test_list_products_with_parent_category_filter(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        vendor_user,
    ):
        """Test category filter includes products in child categories."""
        from app.models.category import Category
        from app.models.product import Product, ProductStatus, ModerationStatus
        import uuid

        parent_category = Category(
            id=uuid.uuid4(),
            name="Men",
            slug="men",
            description="Menswear root",
        )
        child_category = Category(
            id=uuid.uuid4(),
            name="Men's Shirts",
            slug="mens-shirts",
            parent_id=parent_category.id,
            description="Menswear shirts",
        )
        other_category = Category(
            id=uuid.uuid4(),
            name="Women",
            slug="women",
            description="Womenswear root",
        )
        db_session.add_all([parent_category, child_category, other_category])

        men_product = Product(
            id=uuid.uuid4(),
            vendor_id=vendor_user["vendor"].id,
            title="Men's Shirt",
            description="Test shirt",
            base_price=120.00,
            total_stock=10,
            status=ProductStatus.ACTIVE,
            moderation_status=ModerationStatus.APPROVED,
            category_id=child_category.id,
        )
        women_product = Product(
            id=uuid.uuid4(),
            vendor_id=vendor_user["vendor"].id,
            title="Women's Dress",
            description="Test dress",
            base_price=150.00,
            total_stock=5,
            status=ProductStatus.ACTIVE,
            moderation_status=ModerationStatus.APPROVED,
            category_id=other_category.id,
        )
        db_session.add_all([men_product, women_product])
        await db_session.commit()

        response = await client.get(f"/api/v1/products?category_id={parent_category.id}")

        assert response.status_code == 200
        data = response.json()
        product_titles = {product["title"] for product in data["products"]}
        assert "Men's Shirt" in product_titles
        assert "Women's Dress" not in product_titles


class TestProductRetrieve:
    """Test get single product endpoint"""

    @pytest.mark.asyncio
    async def test_get_product_success(self, client: AsyncClient, sample_product):
        """Test successful product retrieval"""
        response = await client.get(f"/api/v1/products/{sample_product.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_product.id)
        assert data["title"] == sample_product.title
        assert data["views_count"] == 1  # Should increment

    @pytest.mark.asyncio
    async def test_get_product_not_found(self, client: AsyncClient):
        """Test get non-existent product"""
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        response = await client.get(f"/api/v1/products/{fake_uuid}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_draft_product_as_public(self, client: AsyncClient, vendor_user, db_session: AsyncSession):
        """Test that public users cannot see draft products"""
        from app.models.product import Product, ProductStatus, ModerationStatus
        import uuid

        # Create draft product
        draft_product = Product(
            id=uuid.uuid4(),
            vendor_id=vendor_user["vendor"].id,
            title="Draft Product",
            base_price=50.00,
            status=ProductStatus.DRAFT,
            moderation_status=ModerationStatus.PENDING
        )
        db_session.add(draft_product)
        await db_session.commit()

        response = await client.get(f"/api/v1/products/{draft_product.id}")
        assert response.status_code == 404  # Should not be visible

    @pytest.mark.asyncio
    async def test_get_pending_active_product_as_public_returns_not_found(
        self,
        client: AsyncClient,
        vendor_user,
        db_session: AsyncSession,
    ):
        """Pending moderation should block direct public detail access even if status is active."""
        from app.models.product import Product, ProductStatus, ModerationStatus
        import uuid

        pending_product = Product(
            id=uuid.uuid4(),
            vendor_id=vendor_user["vendor"].id,
            title="Pending Detail Product",
            base_price=50.00,
            total_stock=3,
            status=ProductStatus.ACTIVE,
            moderation_status=ModerationStatus.PENDING,
        )
        db_session.add(pending_product)
        await db_session.commit()

        response = await client.get(f"/api/v1/products/{pending_product.id}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_approved_product_becomes_public_after_admin_approval(
        self,
        client: AsyncClient,
        vendor_user,
        admin_user,
    ):
        """Admin approval should be the transition that makes a product public."""
        create_response = await client.post(
            "/api/v1/products",
            json={
                "title": "Approval Flow Product",
                "base_price": 65.00,
            },
            headers=vendor_user["headers"],
        )
        assert create_response.status_code == 201
        created = create_response.json()
        product_id = created["id"]

        public_before = await client.get(f"/api/v1/products/{product_id}")
        assert public_before.status_code == 404

        approval_response = await client.put(
            f"/api/v1/admin/products/{product_id}/approve",
            json={"notes": "Approved for storefront"},
            headers=admin_user["headers"],
        )
        assert approval_response.status_code == 200

        public_after = await client.get(f"/api/v1/products/{product_id}")
        assert public_after.status_code == 200
        approved = public_after.json()
        assert approved["moderation_status"] == "approved"
        assert approved["status"] == "active"


class TestProductUpdate:
    """Test product update endpoint"""

    @pytest.mark.asyncio
    async def test_update_product_success(self, client: AsyncClient, vendor_user, sample_product):
        """Test successful product update"""
        update_data = {
            "title": "Updated Product Title",
            "base_price": 129.99
        }

        response = await client.put(
            f"/api/v1/products/{sample_product.id}",
            json=update_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == update_data["title"]
        assert float(data["base_price"]) == update_data["base_price"]

    @pytest.mark.asyncio
    async def test_update_product_unauthorized(self, client: AsyncClient, sample_product):
        """Test update without authentication"""
        update_data = {"title": "Updated Title"}

        response = await client.put(
            f"/api/v1/products/{sample_product.id}",
            json=update_data
        )

        assert response.status_code == 403  # HTTPBearer returns 403 for missing auth

    @pytest.mark.asyncio
    async def test_update_other_vendor_product(
        self,
        client: AsyncClient,
        vendor_user,
        sample_product,
        db_session: AsyncSession
    ):
        """Test that vendor cannot update another vendor's product"""
        from app.models.user import User, UserRole
        from app.models.vendor import Vendor, KYCStatus
        from app.core.security import get_password_hash, create_access_token
        import uuid

        # Create second vendor
        user2 = User(
            id=uuid.uuid4(),
            email="vendor2@test.com",
            hashed_password=get_password_hash("Pass123"),
            full_name="Vendor 2",
            role=UserRole.VENDOR,
            is_active=True
        )
        db_session.add(user2)
        await db_session.flush()

        vendor2 = Vendor(
            id=uuid.uuid4(),
            user_id=user2.id,
            business_name="Business 2",
            kyc_status=KYCStatus.APPROVED,
            approved=True
        )
        db_session.add(vendor2)
        await db_session.commit()

        token2 = create_access_token(
            data={"sub": str(user2.id), "email": user2.email, "role": user2.role.value}
        )

        # Try to update first vendor's product
        response = await client.put(
            f"/api/v1/products/{sample_product.id}",
            json={"title": "Hacked"},
            headers={"Authorization": f"Bearer {token2}"}
        )

        assert response.status_code == 403


class TestProductDelete:
    """Test product deletion endpoint"""

    @pytest.mark.asyncio
    async def test_delete_product_success(
        self,
        client: AsyncClient,
        vendor_user,
        sample_product,
        db_session: AsyncSession,
    ):
        """Test successful product deletion (soft delete)"""
        from app.models.product import Product, ProductStatus
        from sqlalchemy import select

        response = await client.delete(
            f"/api/v1/products/{sample_product.id}",
            headers=vendor_user["headers"]
        )

        assert response.status_code == 204

        # Verify product is archived in persistence and hidden from the public catalog
        archived_result = await db_session.execute(
            select(Product).where(Product.id == sample_product.id)
        )
        archived_product = archived_result.scalar_one()
        assert archived_product.status == ProductStatus.ARCHIVED

        public_response = await client.get(f"/api/v1/products/{sample_product.id}")
        assert public_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_product_unauthorized(self, client: AsyncClient, sample_product):
        """Test delete without authentication"""
        response = await client.delete(f"/api/v1/products/{sample_product.id}")
        assert response.status_code == 403  # HTTPBearer returns 403 for missing auth


class TestProductVariants:
    """Test product variant endpoints"""

    @pytest.mark.asyncio
    async def test_create_variant(self, client: AsyncClient, vendor_user, sample_product):
        """Test creating a product variant"""
        variant_data = {
            "size": "XL",
            "color": "Green",
            "color_hex": "#00FF00",
            "price": 105.00,
            "stock": 20
        }

        response = await client.post(
            f"/api/v1/products/{sample_product.id}/variants",
            json=variant_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 201
        data = response.json()
        assert data["size"] == "XL"
        assert data["color"] == "Green"
        assert float(data["price"]) == 105.00

    @pytest.mark.asyncio
    async def test_update_variant(
        self,
        client: AsyncClient,
        vendor_user,
        sample_product,
        db_session: AsyncSession
    ):
        """Test updating a variant"""
        from app.models.product import ProductVariant
        import uuid

        # Create variant
        variant = ProductVariant(
            id=uuid.uuid4(),
            product_id=sample_product.id,
            size="M",
            price=85.00,
            stock=10
        )
        db_session.add(variant)
        await db_session.commit()

        # Update variant
        update_data = {"stock": 25, "price": 90.00}

        response = await client.put(
            f"/api/v1/products/{sample_product.id}/variants/{variant.id}",
            json=update_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["stock"] == 25
        assert float(data["price"]) == 90.00

    @pytest.mark.asyncio
    async def test_delete_variant(
        self,
        client: AsyncClient,
        vendor_user,
        sample_product,
        db_session: AsyncSession
    ):
        """Test deleting a variant"""
        from app.models.product import ProductVariant
        import uuid

        variant = ProductVariant(
            id=uuid.uuid4(),
            product_id=sample_product.id,
            size="S",
            price=80.00,
            stock=5
        )
        db_session.add(variant)
        await db_session.commit()

        response = await client.delete(
            f"/api/v1/products/{sample_product.id}/variants/{variant.id}",
            headers=vendor_user["headers"]
        )

        assert response.status_code == 204


class TestProductImages:
    """Test product image endpoints"""

    @pytest.mark.asyncio
    async def test_create_image(self, client: AsyncClient, vendor_user, sample_product):
        """Test adding a product image"""
        image_data = {
            "image_url": "https://example.com/test.jpg",
            "alt_text": "Test image",
            "display_order": 0,
            "is_primary": True
        }

        response = await client.post(
            f"/api/v1/products/{sample_product.id}/images",
            json=image_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 201
        data = response.json()
        assert data["image_url"] == image_data["image_url"]
        assert data["is_primary"] is True

    @pytest.mark.asyncio
    async def test_delete_image(
        self,
        client: AsyncClient,
        vendor_user,
        sample_product,
        db_session: AsyncSession
    ):
        """Test deleting a product image"""
        from app.models.product import ProductImage
        import uuid

        image = ProductImage(
            id=uuid.uuid4(),
            product_id=sample_product.id,
            image_url="https://example.com/delete.jpg",
            display_order=0
        )
        db_session.add(image)
        await db_session.commit()

        response = await client.delete(
            f"/api/v1/products/{sample_product.id}/images/{image.id}",
            headers=vendor_user["headers"]
        )

        assert response.status_code == 204


class TestProductModeration:
    """Test admin moderation endpoints"""

    @pytest.mark.asyncio
    async def test_approve_product(
        self,
        client: AsyncClient,
        admin_user,
        sample_product
    ):
        """Test approving a product"""
        moderation_data = {
            "moderation_status": "approved",
            "moderation_notes": "Looks good!"
        }

        response = await client.patch(
            f"/api/v1/products/{sample_product.id}/moderation",
            json=moderation_data,
            headers=admin_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["moderation_status"] == "approved"
        assert data["moderation_notes"] == "Looks good!"

    @pytest.mark.asyncio
    async def test_reject_product(
        self,
        client: AsyncClient,
        admin_user,
        sample_product
    ):
        """Test rejecting a product"""
        moderation_data = {
            "moderation_status": "rejected",
            "moderation_notes": "Violates policy"
        }

        response = await client.patch(
            f"/api/v1/products/{sample_product.id}/moderation",
            json=moderation_data,
            headers=admin_user["headers"]
        )

        assert response.status_code == 200
        data = response.json()
        assert data["moderation_status"] == "rejected"

    @pytest.mark.asyncio
    async def test_moderate_as_vendor(
        self,
        client: AsyncClient,
        vendor_user,
        sample_product
    ):
        """Test that vendors cannot moderate products"""
        moderation_data = {
            "moderation_status": "approved"
        }

        response = await client.patch(
            f"/api/v1/products/{sample_product.id}/moderation",
            json=moderation_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 403


class TestProductValidation:
    """Test product validation"""

    @pytest.mark.asyncio
    async def test_invalid_title_length(self, client: AsyncClient, vendor_user):
        """Test product with too short title"""
        product_data = {
            "title": "AB",  # Too short (min 3 chars)
            "base_price": 50.00
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_status(self, client: AsyncClient, vendor_user):
        """Test product with invalid status"""
        product_data = {
            "title": "Test Product",
            "base_price": 50.00,
            "status": "invalid_status"
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_price_exceeds_max(self, client: AsyncClient, vendor_user):
        """Test product with price exceeding maximum"""
        product_data = {
            "title": "Expensive Product",
            "base_price": 9999999.99  # Exceeds max
        }

        response = await client.post(
            "/api/v1/products",
            json=product_data,
            headers=vendor_user["headers"]
        )

        assert response.status_code == 422
