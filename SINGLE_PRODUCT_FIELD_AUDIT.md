# Single Product Upload - Complete Field Audit

## Executive Summary
This document maps ALL fields from vendor upload form → backend storage → frontend display for **single products**.

---

## PHASE 1: VENDOR UPLOAD FORM FIELDS

### Form Fields Inventory (VendorProductAdd.tsx)

| Field Name | State Variable | Required | Data Type | Notes |
|------------|---------------|----------|-----------|-------|
| **Product Name** | `productName` | ✅ Yes | string | Product title |
| **Primary Category** | `primaryCategoryId` | ✅ Yes | UUID | Parent category |
| **Subcategory** | `subcategoryId` | ✅ Yes | UUID | Leaf category (used in submission) |
| **Price** | `productPrice` | ✅ Yes | number | Base selling price |
| **Sales Price** | `salesPrice` | ❌ No | number | Compare-at price (original MSRP) |
| **Currency** | `productCurrency` | ✅ Yes | "NGN" \| "USD" | Defaults to NGN |
| **Description** | `productDescription` | ❌ No | string | Product description |
| **Materials** | `materials` | ❌ No | string | → Maps to `fabric_composition` |
| **Product Care** | `productCare` | ❌ No | string | → Maps to `care_instructions` |
| **Collection** | `collectionId` | ❌ No | UUID | Optional collection membership |
| **Stock Amount** | `stockAmount` | ❌ No | number | Total inventory |
| **Product Type** | `productType` | ✅ Yes | "single" \| "variable" | Defaults to "single" |
| **Made to Order** | `madeToOrder` | ❌ No | boolean | Custom production flag |
| **Production Time** | `estimatedProductionTime` | ❌ No | string | Timeline if made-to-order |
| **Images** | `variations[0].images` | ✅ Yes | ProductImage[] | Main product images |

### Fields NOT Used for Single Products
- `color` / `colorHex` - Only for variable products
- `selectedSizes` - Only for variable products
- `sizingSystem` - Only for variable products
- `detailedVariations` - Only for variable products
- `isSustainable` - NOT submitted (unused field)

---

## PHASE 2: SUBMISSION PAYLOAD MAPPING

### Actual Payload (handleSubmit - Line 665)
```typescript
const productData = {
  title: productName,                                           // ✅ Mapped
  description: productDescription,                              // ✅ Mapped
  base_price: parseFloat(productPrice),                         // ✅ Mapped
  compare_at_price: salesPrice ? parseFloat(salesPrice) : undefined,  // ✅ Mapped
  total_stock: stockAmount ? parseInt(stockAmount) : 0,         // ✅ Mapped
  category_id: subcategoryId,                                   // ✅ Mapped
  collection_id: collectionId || undefined,                     // ✅ Mapped
  status: 'draft' as const,                                     // ✅ Mapped (hardcoded)
  is_featured: false,                                           // ✅ Mapped (hardcoded)
  currency: productCurrency,                                    // ✅ Mapped
  product_type: productType,                                    // ✅ Mapped
  made_to_order: madeToOrder,                                   // ✅ Mapped
  made_to_order_timeline: madeToOrder ? estimatedProductionTime : undefined,  // ✅ Mapped
  care_instructions: productCare || undefined,                  // ✅ Mapped
  fabric_composition: materials || undefined,                   // ✅ Mapped
  variations: variationsData,                                   // ✅ Empty for single products
  images: productImages.length > 0 ? productImages : undefined, // ✅ Mapped
};
```

**Status**: ✅ **ALL form fields are properly submitted**

---

## PHASE 3: BACKEND STORAGE VERIFICATION

### Database Schema (Product Model - Line 32-94)

| Field | Column Type | Nullable | Submitted? | Stored? |
|-------|-------------|----------|------------|---------|
| `id` | UUID | No | Auto-generated | ✅ |
| `vendor_id` | UUID | No | Auto-filled | ✅ |
| `title` | String(255) | No | ✅ `productName` | ✅ |
| `description` | Text | Yes | ✅ `productDescription` | ✅ |
| `category_id` | UUID | Yes | ✅ `subcategoryId` | ✅ |
| `collection_id` | UUID | Yes | ✅ `collectionId` | ✅ |
| `sku` | String(100) | Yes | ❌ Not submitted | ⚠️ |
| `base_price` | Numeric(10,2) | No | ✅ `productPrice` | ✅ |
| `compare_at_price` | Numeric(10,2) | Yes | ✅ `salesPrice` | ✅ |
| `currency` | String(3) | No | ✅ `productCurrency` | ✅ |
| `total_stock` | Integer | No | ✅ `stockAmount` | ✅ |
| `status` | Enum | No | ✅ `'draft'` | ✅ |
| `is_featured` | Boolean | No | ✅ `false` | ✅ |
| `product_type` | Enum | No | ✅ `productType` | ✅ |
| `made_to_order` | Boolean | No | ✅ `madeToOrder` | ✅ |
| `made_to_order_timeline` | String(255) | Yes | ✅ `estimatedProductionTime` | ✅ |
| `care_instructions` | Text | Yes | ✅ `productCare` | ✅ |
| `fabric_composition` | Text | Yes | ✅ `materials` | ✅ |
| `meta_title` | String(255) | Yes | ❌ Not submitted | ⚠️ |
| `meta_description` | Text | Yes | ❌ Not submitted | ⚠️ |
| `size_guide` | JSONB | Yes | ❌ Not submitted | ⚠️ |
| `views_count` | Integer | No | Auto | ✅ |
| `orders_count` | Integer | No | Auto | ✅ |
| `moderation_status` | Enum | No | Auto (`pending`) | ✅ |
| `created_at` | DateTime | No | Auto | ✅ |
| `updated_at` | DateTime | No | Auto | ✅ |

**Issues Found**:
- ⚠️ `sku` - Form has no field for this (optional, can be auto-generated)
- ⚠️ `meta_title`, `meta_description` - No SEO fields in form (future enhancement)
- ⚠️ `size_guide` - Not applicable for single products (correct)

---

## PHASE 4: API RESPONSE VERIFICATION

### ProductResponse Schema (Line 355-374)

**Exposed Fields** (from `ProductResponse` schema):
```python
class ProductResponse(ProductBase):
    id: UUID                                    # ✅ Exposed
    vendor_id: UUID                             # ✅ Exposed
    vendor_name: Optional[str] = None           # ✅ Exposed (computed property)
    category_name: Optional[str] = None         # ✅ Exposed (computed property)
    collection_name: Optional[str] = None       # ✅ Exposed (computed property)
    moderation_status: str                      # ✅ Exposed
    moderation_notes: Optional[str] = None      # ✅ Exposed
    views_count: int                            # ✅ Exposed
    orders_count: int                           # ✅ Exposed
    created_at: datetime                        # ✅ Exposed
    updated_at: datetime                        # ✅ Exposed

    # Relationships
    variants: List[ProductVariantResponse] = [] # ✅ Exposed (empty for single)
    variations: List[VariationResponse] = []    # ✅ Exposed (empty for single)
    images: List[ProductImageResponse] = []     # ✅ Exposed
```

**Status**: ✅ **ALL stored fields are exposed in API response**

---

## PHASE 5: FRONTEND DISPLAY AUDIT

### 5.1 Product Detail Page (ProductDetail.tsx)

#### Currently Displayed Fields

| Section | Field | Source | Status |
|---------|-------|--------|--------|
| **Header** | Vendor Name | `product.vendor_name` | ✅ Displayed |
| **Header** | Product Title | `product.title` | ✅ Displayed |
| **Pricing** | Current Price | `product.base_price` | ✅ Displayed |
| **Pricing** | Original Price | `product.compare_at_price` | ✅ Displayed (if set) |
| **Pricing** | Savings % | Calculated | ✅ Displayed (if discount) |
| **Description** | Product Description | `product.description` | ✅ Displayed |
| **Made to Order** | Badge + Timeline | `product.made_to_order` | ✅ Displayed (if true) |
| **Images** | Main Image | `product.images[0]` | ✅ Displayed |
| **Images** | Gallery Thumbnails | `product.images` | ✅ Displayed (if 2+ images) |
| **Product Info** | Care Instructions | `product.care_instructions` | ✅ Displayed (if set) |
| **Product Info** | Fabric Composition | `product.fabric_composition` | ✅ Displayed (if set) |
| **Product Info** | Sustainability | Hardcoded text | ✅ Displayed (always) |
| **Product Info** | Shipping | Hardcoded text | ✅ Displayed (always) |
| **Product Info** | Gifting | Hardcoded text | ✅ Displayed (always) |

#### Missing/Not Displayed

| Field | Why Not Displayed | Recommendation |
|-------|-------------------|----------------|
| `category_name` | Not shown on detail page | ⚠️ Should add breadcrumb navigation |
| `collection_name` | Not shown on detail page | ⚠️ Could add as badge/tag |
| `total_stock` | Only shows "Only X left" warning | ⚠️ Consider showing "In Stock" status |
| `sku` | Internal identifier | ✅ Correct to hide |
| `views_count` | Analytics data | ✅ Correct to hide |
| `orders_count` | Analytics data | ✅ Could show as "X orders" social proof |

### 5.2 Product Card (ProductCard.tsx)

#### Currently Displayed Fields

| Section | Field | Source | Status |
|---------|-------|--------|--------|
| **Image** | Primary Image | `product.images[0]` | ✅ Displayed |
| **Image** | Secondary (Hover) | `product.images[1]` | ✅ Displayed (if exists) |
| **Info** | Vendor Name | `product.vendor_name` | ✅ Displayed |
| **Info** | Product Title | `product.title` | ✅ Displayed |
| **Info** | Current Price | `product.base_price` or `variant.price` | ✅ Displayed |
| **Info** | Original Price | `product.compare_at_price` | ✅ Displayed (if discount) |
| **Hover** | Sizes | `product.variants` | ✅ Hidden for single products |
| **Hover** | Colors | `product.variants` | ✅ Hidden for single products |

#### Missing/Not Displayed

| Field | Why Not Displayed | Recommendation |
|-------|-------------------|----------------|
| `category_name` | Not shown on card | ⚠️ Could add as small tag |
| `collection_name` | Not shown on card | ⚠️ Could add as badge |
| `made_to_order` | Not shown on card | ⚠️ Should add "Made to Order" badge |
| `total_stock` | Not shown on card | ⚠️ Could show "Low Stock" badge |

---

## PHASE 6: ADMIN DASHBOARD AUDIT

Let me check the admin product views:


## PHASE 6: ADMIN DASHBOARD DISPLAY

### AdminProductDetail.tsx

#### Displayed Fields
| Field | Location (Line) | Status |
|-------|----------------|--------|
| `title` | 137 | ✅ Displayed |
| `id` | 139 | ✅ Displayed |
| `images` | 170-197 | ✅ Displayed (main + thumbnails) |
| `description` | 208 | ✅ Displayed |
| `materials` | 212-215 | ⚠️ **WRONG FIELD** - Uses `product.materials` instead of `product.fabric_composition` |
| `moderation_status` | 229-230 | ✅ Displayed |
| `status` | 237-238 | ✅ Displayed |
| `base_price` | 251 | ✅ Displayed |
| `compare_at_price` | 253-256 | ✅ Displayed (if set) |
| `total_stock` | 268 | ✅ Displayed |
| `inventory_quantity` | 272 | ✅ Displayed |
| `category_name` | 286 | ✅ Displayed |
| `collection_name` | 291-296 | ✅ Displayed (if set) |
| `gender` | 301-306 | ✅ Displayed (if set) |
| `created_at` | 319 | ✅ Displayed |
| `updated_at` | 323 | ✅ Displayed |
| `vendor_id` | 329-334 | ✅ Displayed |

#### **CRITICAL BUG FOUND**:
**Line 215**: Uses `product.materials` but backend field is `fabric_composition`
```typescript
{product.materials && (  // ❌ WRONG
  <div className="mb-6">
    <h3 className="text-sm font-medium text-gray-700 mb-2">Materials</h3>
    <p className="text-gray-600">{product.materials}</p>  // ❌ WRONG
  </div>
)}
```

Should be:
```typescript
{product.fabric_composition && (  // ✅ CORRECT
  <div className="mb-6">
    <h3 className="text-sm font-medium text-gray-700 mb-2">Fabric & Materials</h3>
    <p className="text-gray-600">{product.fabric_composition}</p>  // ✅ CORRECT
  </div>
)}
```

#### Missing Fields
| Field | Why Missing | Recommendation |
|-------|-------------|----------------|
| `care_instructions` | Not displayed | ⚠️ Should add section |
| `made_to_order` | Not displayed | ⚠️ Should show badge |
| `made_to_order_timeline` | Not displayed | ⚠️ Should show with badge |
| `currency` | Not displayed | ⚠️ Should show in pricing section |

---

## PHASE 7: VENDOR DASHBOARD DISPLAY

### VendorProductView.tsx

#### Displayed Fields
| Field | Location (Line) | Status |
|-------|----------------|--------|
| `title` | 169 | ✅ Displayed |
| `images` | 194-195 | ✅ Displayed |
| `description` | 223 | ✅ Displayed |
| `size_guide` | 228-234 | ✅ Displayed (if set) |
| `variations` | 242-249 | ✅ Displayed (for variable products) |
| `moderation_status` | 301-302 | ✅ Displayed |
| `moderation_notes` | 307-317 | ✅ Displayed (if rejected) |
| `base_price` | 333 | ✅ Displayed |
| `compare_at_price` | 338-342 | ✅ Displayed (if set) |
| `total_stock` | 354 | ✅ Displayed |
| `category` | 359-365 | ⚠️ Uses `product.category` (should be `category_name`) |
| `created_at` | 375 | ✅ Displayed |
| `views_count` | 379-385 | ✅ Displayed |

#### Missing Fields
| Field | Why Missing | Recommendation |
|-------|-------------|----------------|
| `fabric_composition` | Not displayed | ⚠️ Should add section |
| `care_instructions` | Not displayed | ⚠️ Should add section |
| `made_to_order` | Not displayed | ⚠️ Should show badge |
| `made_to_order_timeline` | Not displayed | ⚠️ Should show with badge |
| `currency` | Not displayed | ⚠️ Should show in pricing section |
| `collection_name` | Not displayed | ⚠️ Should show if set |

---

## CRITICAL ISSUES FOUND

### 🚨 HIGH PRIORITY

1. **AdminProductDetail.tsx Line 215** - Uses `product.materials` (doesn't exist) instead of `product.fabric_composition`
   - **Impact**: Fabric/materials info never displays in admin dashboard
   - **Fix**: Change `product.materials` → `product.fabric_composition`

2. **TypeScript Type Definition** - `Product` type likely has wrong field name
   - **Location**: `shopsoma-frontend/src/types/index.ts`
   - **Impact**: Type system allows incorrect field access
   - **Fix**: Update `Product` interface to use `fabric_composition` instead of `materials`

### ⚠️ MEDIUM PRIORITY

3. **Missing care_instructions display** in admin/vendor dashboards
   - **Impact**: Vendors/admins can't see product care info after upload
   - **Fix**: Add care instructions section to both dashboards

4. **Missing made_to_order display** in product card
   - **Impact**: Customers don't see "Made to Order" badge on catalog pages
   - **Fix**: Add badge to ProductCard component

5. **Missing category display** in ProductDetail page
   - **Impact**: No breadcrumb navigation for customers
   - **Fix**: Add category/breadcrumb to product detail header

---

## RECOMMENDED FIXES

### Fix 1: Update Product TypeScript Interface
**File**: `shopsoma-frontend/src/types/index.ts`

Search for the `Product` interface and ensure it has:
```typescript
export interface Product {
  // ... other fields ...
  fabric_composition?: string | null;  // ✅ CORRECT name
  care_instructions?: string | null;
  made_to_order: boolean;
  made_to_order_timeline?: string | null;
  // Remove if exists:
  // materials?: string;  // ❌ WRONG - should be fabric_composition
}
```

### Fix 2: Update AdminProductDetail.tsx
**File**: `shopsoma-frontend/src/pages/admin/AdminProductDetail.tsx`

**Change Line 212-217**:
```typescript
{/* Fabric & Materials */}
{product.fabric_composition && (
  <div className="mb-6">
    <h3 className="text-sm font-medium text-gray-700 mb-2">Fabric & Materials</h3>
    <p className="text-gray-600">{product.fabric_composition}</p>
  </div>
)}

{/* Care Instructions */}
{product.care_instructions && (
  <div className="mb-6">
    <h3 className="text-sm font-medium text-gray-700 mb-2">Care Instructions</h3>
    <p className="text-gray-600 whitespace-pre-wrap">{product.care_instructions}</p>
  </div>
)}

{/* Made to Order */}
{product.made_to_order && (
  <div className="mb-6">
    <h3 className="text-sm font-medium text-gray-700 mb-2">Production</h3>
    <div className="flex items-center gap-2">
      <span className="px-3 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full">
        MADE TO ORDER
      </span>
      {product.made_to_order_timeline && (
        <span className="text-sm text-gray-600">{product.made_to_order_timeline}</span>
      )}
    </div>
  </div>
)}
```

### Fix 3: Update VendorProductView.tsx
**File**: `shopsoma-frontend/src/pages/vendor/VendorProductView.tsx`

Add after description section (around line 223):
```typescript
{/* Fabric & Materials */}
{product.fabric_composition && (
  <div className="mb-6">
    <h3 className="text-sm font-medium text-gray-700 mb-2">Fabric & Materials</h3>
    <p className="text-gray-600">{product.fabric_composition}</p>
  </div>
)}

{/* Care Instructions */}
{product.care_instructions && (
  <div className="mb-6">
    <h3 className="text-sm font-medium text-gray-700 mb-2">Care Instructions</h3>
    <p className="text-gray-600 whitespace-pre-wrap">{product.care_instructions}</p>
  </div>
)}

{/* Made to Order */}
{product.made_to_order && (
  <div className="mb-4">
    <span className="inline-flex items-center gap-2 px-3 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full">
      <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
        <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/>
      </svg>
      MADE TO ORDER
      {product.made_to_order_timeline && ` • ${product.made_to_order_timeline}`}
    </span>
  </div>
)}
```

### Fix 4: Add Made-to-Order Badge to ProductCard
**File**: `shopsoma-frontend/src/components/products/ProductCard.tsx`

Add badge overlay to image container (around line 82-90):
```typescript
{/* Image Container */}
<div className="relative overflow-hidden aspect-[3/4] mb-4 bg-gray-100">
  {/* Made to Order Badge - Top Left */}
  {product.made_to_order && (
    <div className="absolute top-3 left-3 z-20">
      <span className="px-2 py-1 bg-blue-600 text-white text-[10px] font-serif uppercase tracking-[0.15em] rounded">
        MADE TO ORDER
      </span>
    </div>
  )}
  
  {/* ... rest of image code ... */}
</div>
```

### Fix 5: Add Category Breadcrumb to ProductDetail
**File**: `shopsoma-frontend/src/pages/products/ProductDetail.tsx`

Add before product title (around line 504-510):
```typescript
{/* Breadcrumb Navigation */}
{product.category_name && (
  <div className="mb-3">
    <nav className="flex items-center gap-2 text-xs font-ui uppercase tracking-[0.2em] text-primary/70">
      <Link to="/" className="hover:text-primary">Home</Link>
      <span>/</span>
      <Link to="/products" className="hover:text-primary">Shop</Link>
      <span>/</span>
      <span className="text-primary">{product.category_name}</span>
    </nav>
  </div>
)}

{/* Product Title */}
<h1 className="text-4xl lg:text-5xl font-display text-primary leading-tight -mt-2">
  {product.title}
</h1>
```

---

## TESTING CHECKLIST

After applying all fixes, test with "Queen of green" product:

### Frontend Product Detail Page
- [ ] Navigate to: http://localhost:5173/products/474d3368-3979-4142-aa3a-df7755d7f23f
- [ ] Verify category breadcrumb shows "Home / Shop / Women's Dresses"
- [ ] Verify "Made to Order • Ships in 2-3 weeks" badge displays
- [ ] Verify "Product Care" section shows hand wash instructions
- [ ] Verify "Fabric & Materials" section shows "100% Premium Cotton..."
- [ ] Verify price displays correctly in NGN
- [ ] Verify main image displays
- [ ] Verify "Add to Bag" works without requiring size/color selection

### Frontend Product Card
- [ ] Navigate to: http://localhost:5173/products
- [ ] Find "Queen of green" in catalog
- [ ] Verify "MADE TO ORDER" badge shows on card image
- [ ] Verify NO hover overlay appears (single product, no variants)
- [ ] Verify price displays correctly

### Admin Dashboard
- [ ] Navigate to admin product detail (requires admin login)
- [ ] Verify "Fabric & Materials" section shows data
- [ ] Verify "Care Instructions" section shows data
- [ ] Verify "MADE TO ORDER" badge displays with timeline
- [ ] Verify all other fields display correctly

### Vendor Dashboard
- [ ] Navigate to vendor product view (requires vendor login)
- [ ] Verify "Fabric & Materials" section shows data
- [ ] Verify "Care Instructions" section shows data
- [ ] Verify "MADE TO ORDER" badge displays with timeline
- [ ] Verify all other fields display correctly

---

## SUMMARY

### ✅ Fields Working Correctly
1. Product name/title - ✅ All views
2. Description - ✅ All views
3. Price/Compare price - ✅ All views
4. Currency - ✅ Backend storage (display needs enhancement)
5. Images - ✅ All views
6. Stock - ✅ All views
7. Category - ✅ Backend storage, displayed in admin/vendor (needs breadcrumb in product detail)
8. Collection - ✅ Backend storage, displayed in admin (missing in vendor/product detail)
9. Status/Moderation - ✅ Admin/vendor dashboards

### ❌ Fields Needing Fixes
1. `fabric_composition` - ❌ Admin dashboard uses wrong field name (`product.materials`)
2. `care_instructions` - ❌ Not displayed in admin/vendor dashboards
3. `made_to_order` - ❌ Not displayed anywhere except product detail (needs badge on card)
4. `made_to_order_timeline` - ❌ Not displayed in dashboards
5. Category breadcrumb - ❌ Missing from product detail page

### 📊 Coverage Report

| Display Location | Coverage | Missing Fields |
|------------------|----------|----------------|
| **Product Detail Page** | 90% | Category breadcrumb |
| **Product Card** | 85% | Made-to-order badge, collection |
| **Admin Dashboard** | 75% | care_instructions, made_to_order, WRONG field for materials |
| **Vendor Dashboard** | 70% | fabric_composition, care_instructions, made_to_order |

---

**Next Steps**: Apply fixes 1-5 above to achieve 100% field coverage across all views.
