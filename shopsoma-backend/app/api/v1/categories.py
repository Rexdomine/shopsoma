"""
Categories API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import uuid

from app.core.database import get_db
from app.models.category import Category
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])

# Static fallback category UUIDs from frontend categoryNavigation.ts mapped to canonical slugs
STATIC_CATEGORY_ID_TO_SLUG: dict[str, str] = {
    "27b5a940-610d-4243-a796-7e4c63b04060": "women",
    "b5be5460-0d0d-4302-a2ca-f4cfcd518135": "men",
    "b3bcadf9-1878-40eb-9d53-2c2258b3a11b": "women-tops",
    "f876f16a-5faf-4ed8-986d-29aae4a954bb": "women-dresses",
    "3c0a63b2-31d2-4c30-af12-e0a735153bf0": "women-bottoms",
    "33f58709-41f2-439f-a896-c67205fa5545": "women-accessories",
    "afbb0091-941c-4957-b279-6be4ba78019e": "women-shoes",
    "8c066c29-0f8c-4428-965c-50a5e60d4801": "women-activewear",
    "c484f266-dde6-48c8-a765-8b52c8c9a168": "women-outerwear",
    "dccb7e3d-7f6a-4365-8796-c1279fb6004a": "women-swimwear",
    "d9c26cfb-7081-4816-8a32-6a09346f8df4": "women-lingerie-pyjamas",
    "97a29754-0eb4-4b7f-9d11-aabfd18ce25c": "women-sets",
    "5da6b1c1-d254-4a8c-bbc4-aaa0fe4e88e9": "men-tops",
    "35d415ef-1a2c-40d1-928b-6802a7af51f0": "men-bottoms",
    "7031c4c5-487e-4c97-bac2-1897201e7653": "men-activewear",
    "19b773ce-c2ae-4f21-9657-b87743199e69": "men-sets",
    "e276d883-7fbb-4dfd-bbd2-ea1196024bfe": "men-shoes",
    "ecbb7abb-cb62-4158-9e94-793087056dc4": "men-accessories",
    "de14555d-789e-4278-9548-1bc2b6e7584c": "men-outerwear",
    "7e120d20-1b20-4df2-a39c-851f50a8d011": "women-lingerie-shapewear",
    "edcc6d13-fe39-46b4-8395-a1a7a1fbec0c": "women-lingerie-bras-bralettes",
    "61d8acda-1068-4410-af5c-15238638d232": "women-lingerie-panties-briefs",
    "7978b8d3-00c5-4df8-872d-0ec33fe07f4b": "women-lingerie-pyjamas-sleepwear",
    "0e40d900-945d-44d5-b0c4-c67f1680e60e": "women-lingerie-robes-loungewear",
    "97c93ea3-d96f-42bb-a8a4-daf9b87c3519": "women-lingerie-sets",
    "a10e7b41-2c10-4fa3-b41d-9e51c8a2b012": "women-sets-trouser-sets",
    "dc0899a8-4d1c-4b49-a6fa-ccb40e771bf8": "women-sets-skirt-sets",
    "316c0593-c568-4d5c-b0c9-9352d9738fa7": "women-sets-shorts-sets",
    "b3bcadf9-0001-40eb-9d53-2c2258b3a11b": "women-tops-t-shirts",
    "03742502-86c9-40d2-896c-76c59d5817ca": "women-tops-shirts",
    "85e89419-fd9b-4cf7-8170-ad008e84430e": "women-tops-blouses",
    "178d56cc-e0a6-45da-bc8e-38179c3b9abf": "women-tops-bodysuit",
    "090b0b8f-31af-40e7-8640-98af969cd80a": "women-tops-tank-tops",
    "f876f16a-0001-4ed8-986d-29aae4a954bb": "women-dresses-casual",
    "a5b3e223-869e-4bfe-a996-4877265a8349": "women-dresses-party",
    "4589287b-8448-4ba9-a9e0-8100ca1933f1": "women-dresses-formal",
    "a7da3ee3-1d34-4502-9568-cb211a697dd7": "women-dresses-beach-dresses",
    "3c0a63b2-0001-4c30-af12-e0a735153bf0": "women-bottoms-jeans",
    "bebc1c31-496e-4b3a-8829-06e923f66ebf": "women-bottoms-skirts",
    "05943b0b-0715-41f7-bdb5-69b73be84504": "women-bottoms-trousers",
    "7c57e631-9f22-4f04-a608-359bbb2ce568": "women-bottoms-shorts",
    "33f58709-0001-439f-a896-c67205fa5545": "women-accessories-jewellery",
    "d564e2ba-0f62-419b-a32a-27d28b506874": "women-accessories-bracelets",
    "6ee76a28-45bf-419d-b5b3-0b5067f54613": "women-accessories-earrings",
    "92c27ab4-934f-421d-8380-1c4d42e56655": "women-accessories-necklace",
    "5bc3b7c0-847d-4660-876b-49889f1df584": "women-accessories-rings",
    "9e3dbaa3-0107-46db-a890-c6b93332bd2c": "women-accessories-watches",
    "3cad246a-a535-4151-8d4d-01f02fe51573": "women-accessories-anklets",
    "ac3208b8-5edb-4b7e-8643-d667427cd757": "women-accessories-body-jewellery",
    "da500ff2-b7b5-4cd6-90ab-a1747a651898": "women-accessories-brooches",
    "dcc9bd0f-8087-4808-90ad-eec2bdc3e9a4": "women-accessories-bags",
    "d49dea09-8bfd-4879-ad0e-1ea39c7b4857": "women-accessories-belts",
    "3445dd70-c9e6-4c1c-8c10-aef19f905a2f": "women-accessories-sunglasses",
    "afbb0091-0001-4957-b279-6be4ba78019e": "women-shoes-flats",
    "38a48653-fab0-4e4d-b6ca-393f4e015483": "women-shoes-heels",
    "8c066c29-0001-4428-965c-50a5e60d4801": "women-activewear-tops",
    "0f85533f-a543-4f39-bb20-794084d08677": "women-activewear-bottoms",
    "0557f2ba-094e-4b45-a6bb-ccc50ab50d60": "women-activewear-accessories",
    "c484f266-0001-48c8-a765-8b52c8c9a168": "women-outerwear-jackets",
    "95b4270f-7f75-41e7-9057-ec10f89c5ed2": "women-outerwear-kaftan",
    "b72256e0-54d2-47df-970e-3054b906e80c": "women-outerwear-kimonos",
    "8a73aa47-178c-4697-860f-8c161cbf5f57": "women-outerwear-ponchos",
    "6c7f281c-c76f-4e9a-9c32-92a2dfb6ce81": "women-outerwear-hoodies-sweatshirts",
    "5da6b1c1-0001-4a8c-bbc4-aaa0fe4e88e9": "men-tops-t-shirts",
    "d455953e-07e0-41a3-8b56-b0be70003973": "men-tops-shirts",
    "35d415ef-0001-40d1-928b-6802a7af51f0": "men-bottoms-jeans",
    "dac785ff-a176-4dfc-8b47-4ab19c304e41": "men-bottoms-trousers",
    "ddafd36f-270e-4f83-b8c1-c8c77108c6e3": "men-bottoms-shorts",
    "7031c4c5-0001-4c97-bac2-1897201e7653": "men-activewear-tops",
    "8e61e3a1-e1b0-489e-82d4-3d8be39ef498": "men-activewear-bottoms",
    "0c8fc679-03ed-45fe-b8ac-8fea268448c0": "men-activewear-accessories",
    "19b773ce-0001-4f21-9657-b87743199e69": "men-sets-trouser-sets",
    "41f471ea-a301-4328-b26f-94c9326059c1": "men-sets-shorts-sets",
    "e276d883-0001-4dfd-bbd2-ea1196024bfe": "men-shoes-casual",
    "2b85366c-d5ff-4e82-94b8-538c6b824da6": "men-shoes-formal",
    "ecbb7abb-0001-4158-9e94-793087056dc4": "men-accessories-watches-jewellery",
    "38c93465-3023-4042-9a60-9dc6a1c18613": "men-accessories-wallets",
    "308c3de7-9d86-4110-8d2e-0f218d3925eb": "men-accessories-belts",
    "e535a202-53da-472a-aadb-78437f451387": "men-accessories-sunglasses",
    "bb4ed5d4-1acd-4d73-b0f2-a6cbe69afd53": "men-accessories-caps-hats",
    "de14555d-0001-4278-9548-1bc2b6e7584c": "men-outerwear-hoodies",
    "534333ee-98ad-4d19-81ed-7adcce68e7de": "men-outerwear-jackets",
}


async def resolve_category_by_id_or_static_slug(
    db: AsyncSession, category_id: uuid.UUID
) -> Optional[Category]:
    """Resolve a Category by its UUID, falling back to canonical slug if it is a known static frontend UUID."""
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if category is not None:
        return category

    fallback_slug = STATIC_CATEGORY_ID_TO_SLUG.get(str(category_id).lower())
    if fallback_slug:
        slug_result = await db.execute(
            select(Category).where(Category.slug == fallback_slug)
        )
        return slug_result.scalar_one_or_none()

    return None


@router.get("", response_model=List[CategoryResponse])
async def get_categories(
    db: AsyncSession = Depends(get_db),
    parent_id: Optional[str] = None,
    include_inactive: bool = False
):
    """
    Get all categories, optionally filtered by parent_id.

    - If parent_id is None: returns root categories (primary categories like Men, Women, Beauty)
    - If parent_id is provided: returns subcategories of that parent
    - If include_inactive is False: only returns active categories
    """
    query = select(Category)

    if parent_id:
        # Get subcategories of specific parent
        parent_uuid = uuid.UUID(parent_id)
        resolved_parent = await resolve_category_by_id_or_static_slug(db, parent_uuid)
        effective_parent_id = resolved_parent.id if resolved_parent else parent_uuid
        query = query.where(Category.parent_id == effective_parent_id)
    else:
        # Get root categories (no parent)
        query = query.where(Category.parent_id.is_(None))

    if not include_inactive:
        query = query.where(Category.is_active == True)

    query = query.order_by(Category.display_order, Category.name)

    result = await db.execute(query)
    categories = result.scalars().all()

    return categories


@router.get("/all", response_model=List[CategoryResponse])
async def get_all_categories(
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = False
):
    """
    Get all categories in a flat list (useful for product forms).
    """
    query = select(Category)

    if not include_inactive:
        query = query.where(Category.is_active == True)

    query = query.order_by(Category.parent_id.nulls_first(), Category.display_order, Category.name)

    result = await db.execute(query)
    categories = result.scalars().all()

    return categories


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a single category by ID"""
    result = await db.execute(
        select(Category).where(Category.id == uuid.UUID(category_id))
    )
    category = await resolve_category_by_id_or_static_slug(db, uuid.UUID(category_id))

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return category
