# Product Type Selector - Implementation Guide ✅

**Date**: December 18, 2025
**Status**: Backend ✅ | Frontend ✅ (COMPLETE)

---

## COMPLETED: Backend Implementation

### 1. Database Changes ✅
- Added `ProductType` ENUM: `'SINGLE'`, `'VARIABLE'`
- Added `product_type` column to `products` table
- Default: `'SINGLE'`
- Migration applied successfully

### 2. Model Updates ✅
**File**: `app/models/product.py`

```python
class ProductType(str, enum.Enum):
    """Product type enum"""
    SINGLE = "single"  # Single product with base color/size
    VARIABLE = "variable"  # Variable product with variations

class Product(Base):
    # ...
    product_type = Column(SQLEnum(ProductType), default=ProductType.SINGLE, nullable=False, index=True)
```

### 3. Schema Updates ✅
**File**: `app/schemas/product.py`

```python
class ProductBase(BaseModel):
    # ...
    product_type: str = Field(default="single", pattern="^(single|variable)$", description="Product type: single or variable")
```

### 4. Frontend Types ✅
**File**: `src/types/index.ts`

```typescript
export interface Product {
  // ...
  product_type: 'single' | 'variable';
  // ...
}
```

---

## COMPLETED: Frontend Form Implementation ✅

### Files Modified
1. ✅ [src/pages/vendor/VendorProductAdd.tsx](shopsoma-frontend/src/pages/vendor/VendorProductAdd.tsx) - Product type selector added with conditional rendering

### Implementation Complete

#### Step 1: Add Product Type State

```typescript
const [productType, setProductType] = useState<'single' | 'variable'>('single');
```

#### Step 2: Add Product Type Selector UI

Add this near the top of the form, before product details:

```typescript
{/* Product Type Selector */}
<div className="bg-white p-6 rounded-lg shadow-sm border border-primary/10">
  <h2 className="text-xl font-display text-primary mb-4">Product Type</h2>

  <div className="space-y-4">
    {/* Radio Options */}
    <div className="flex gap-6">
      {/* Single Product Option */}
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="radio"
          name="productType"
          value="single"
          checked={productType === 'single'}
          onChange={(e) => setProductType(e.target.value as 'single' | 'variable')}
          className="mt-1"
        />
        <div>
          <div className="font-semibold text-primary">Single Product</div>
          <div className="text-sm text-primary/70">
            Standard product with base color and size
          </div>
        </div>
      </label>

      {/* Variable Product Option */}
      <label className="flex items-start gap-3 cursor-pointer">
        <input
          type="radio"
          name="productType"
          value="variable"
          checked={productType === 'variable'}
          onChange={(e) => setProductType(e.target.value as 'single' | 'variable')}
          className="mt-1"
        />
        <div>
          <div className="font-semibold text-primary">Variable Product</div>
          <div className="text-sm text-primary/70">
            Product with multiple color/size variations
          </div>
        </div>
      </label>
    </div>

    {/* Helper Text */}
    {productType === 'single' ? (
      <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-800">
        ℹ️ Single product: Use the fields below to set base color and size. Variations section will be disabled.
      </div>
    ) : (
      <div className="p-3 bg-purple-50 border border-purple-200 rounded text-sm text-purple-800">
        ℹ️ Variable product: Base color/size fields will be disabled. Use the Variations section below to set colors and sizes.
      </div>
    )}
  </div>
</div>
```

#### Step 3: Conditional Field Rendering

**For Base Color Field**:
```typescript
{/* Base Color - Only for Single Products */}
{productType === 'single' && (
  <div>
    <label className="block text-sm font-medium text-primary mb-2">
      Color
    </label>
    <div className="flex items-center gap-3">
      <input
        type="color"
        value={color}
        onChange={handleMainColorPickerChange}
        className="w-12 h-12 rounded border border-primary/30 cursor-pointer"
        disabled={productType === 'variable'}
      />
      <input
        type="text"
        value={colorHex}
        onChange={handleMainColorHexChange}
        placeholder="#000000"
        className="flex-1 px-4 py-2 border border-primary/30 rounded focus:outline-none focus:border-primary"
        disabled={productType === 'variable'}
      />
    </div>
  </div>
)}
```

**For Base Size Field** (if exists):
```typescript
{/* Base Size - Only for Single Products */}
{productType === 'single' && (
  <div>
    <label className="block text-sm font-medium text-primary mb-2">
      Size
    </label>
    <input
      type="text"
      value={baseSize}
      onChange={(e) => setBaseSize(e.target.value)}
      placeholder="e.g., M, L, XL"
      className="w-full px-4 py-2 border border-primary/30 rounded focus:outline-none focus:border-primary"
      disabled={productType === 'variable'}
    />
  </div>
)}
```

**For Variations Section**:
```typescript
{/* Product Variations - Only for Variable Products */}
{productType === 'variable' && (
  <div className="bg-white p-6 rounded-lg shadow-sm border border-primary/10">
    <h2 className="text-xl font-display text-primary mb-4">
      Product Variations
    </h2>

    {/* Helper Text */}
    <div className="mb-4 p-3 bg-purple-50 border border-purple-200 rounded text-sm text-purple-800">
      Add color variations with their respective sizes and stock levels.
    </div>

    {/* Existing variations UI */}
    {variations.map((variation, index) => (
      <div key={variation.id} className="mb-4 p-4 border border-primary/20 rounded">
        {/* Variation fields */}
      </div>
    ))}

    {/* Add Variation Button */}
    <button
      type="button"
      onClick={addVariation}
      className="px-4 py-2 bg-primary text-white rounded hover:bg-primary/90"
    >
      + Add Variation
    </button>
  </div>
)}

{/* Disabled Message for Single Products */}
{productType === 'single' && (
  <div className="bg-gray-50 p-6 rounded-lg border border-gray-300">
    <div className="text-center text-gray-600">
      <p className="font-semibold mb-2">Variations Disabled</p>
      <p className="text-sm">
        Variations are only available for Variable Products.
        Switch to "Variable Product" above to enable this section.
      </p>
    </div>
  </div>
)}
```

#### Step 4: Update Form Submission

Add `product_type` to the form data:

```typescript
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();

  const formData = {
    title,
    description,
    base_price: parseFloat(basePrice),
    // ... other fields
    product_type: productType,  // Add this

    // Only include variations if variable product
    ...(productType === 'variable' && {
      variations: variations.map(v => ({
        title: v.color,
        color_hex: v.colorHex,
        price: v.price ? parseFloat(v.price) : null,
        sizes: v.sizeStocks
      }))
    })
  };

  // Submit formData
};
```

#### Step 5: Form Validation

Add validation based on product type:

```typescript
const validateForm = () => {
  const errors: string[] = [];

  if (productType === 'single') {
    // Validate single product fields
    if (!color || !colorHex) {
      errors.push('Base color is required for single products');
    }
    // Add size validation if needed
  } else {
    // Validate variable product fields
    if (variations.length === 0) {
      errors.push('At least one variation is required for variable products');
    }

    variations.forEach((v, index) => {
      if (!v.color || !v.colorHex) {
        errors.push(`Variation ${index + 1}: Color is required`);
      }
      if (!v.sizeStocks || v.sizeStocks.length === 0) {
        errors.push(`Variation ${index + 1}: At least one size is required`);
      }
    });
  }

  return errors;
};
```

---

## Testing Steps

### 1. Create Single Product
1. Go to vendor dashboard → Add Product
2. Select "Single Product"
3. Verify:
   - ✅ Color picker is enabled
   - ✅ Size field is enabled (if exists)
   - ✅ Variations section is disabled/hidden
   - ✅ Helper text explains to use base fields

4. Fill in product details including base color/size
5. Submit form
6. Verify:
   - ✅ Product saved with `product_type: 'single'`
   - ✅ No variations created
   - ✅ Product displays correctly on frontend

### 2. Create Variable Product
1. Go to vendor dashboard → Add Product
2. Select "Variable Product"
3. Verify:
   - ✅ Color picker is disabled
   - ✅ Size field is disabled (if exists)
   - ✅ Variations section is enabled
   - ✅ Helper text explains to use variations

4. Add variations with colors and sizes
5. Submit form
6. Verify:
   - ✅ Product saved with `product_type: 'variable'`
   - ✅ Variations created correctly
   - ✅ Variants auto-generated from variations
   - ✅ Product displays correctly on frontend

### 3. Edit Existing Products
1. Open "Angel White" product for editing
2. Verify current `product_type` is selected
3. Try switching between Single/Variable
4. Verify appropriate fields enable/disable

---

## API Contract

### POST `/api/v1/vendor/products`

**Request Body**:
```json
{
  "title": "Test Product",
  "description": "Product description",
  "base_price": 100.00,
  "product_type": "variable",
  "variations": [
    {
      "title": "Red",
      "color_hex": "#FF0000",
      "price": null,
      "sizes": [
        {"size": "M", "stock": 10},
        {"size": "L", "stock": 5}
      ]
    }
  ]
}
```

**Response**: Standard ProductResponse with `product_type` field

---

## Database Update for Angel White

To set Angel White as a variable product:

```sql
UPDATE products
SET product_type = 'VARIABLE'
WHERE id = '9ac646a0-9cca-49f9-96cb-09382c1cf650';
```

---

## Summary

### Completed ✅
1. Backend Product model with `product_type` enum
2. Database migration applied
3. Pydantic schemas updated
4. Frontend TypeScript types updated
5. Product type selector UI added to VendorProductAdd form
6. Conditional field rendering implemented
7. Form submission updated to include `product_type`
8. TypeScript compilation verified (no errors)

### Implementation Details ✅

**Product Type Selector** (Lines 960-1021):
- Radio buttons for "Single Product" and "Variable Product"
- Dynamic border highlighting based on selection
- Contextual helper text (blue for single, purple for variable)
- Clear instructions for vendors

**Conditional Fields**:
- Color picker: Only visible for `productType === 'single'` (Lines 1313-1340)
- Sizing selector: Only visible for `productType === 'single'` (Lines 1342-1400)
- Variations section: Only visible for `productType === 'variable'` (Lines 1497-1566)
- Disabled state for single products with informative message (Lines 1567-1580)

**Form Submission** (Lines 676-680):
- `product_type` field added to productData
- `made_to_order` and `made_to_order_timeline` included
- `care_instructions` included
- Variations only sent when `productType === 'variable'`

### Benefits
- ✅ Clear separation between single and variable products
- ✅ Prevents confusion about which fields to use
- ✅ Better UX with contextual help text
- ✅ Proper validation based on product type
- ✅ Consistent data structure
- ✅ No TypeScript errors
- ✅ Removed redundant "Product Variations" toggle

---

**Status**: ✅ IMPLEMENTATION COMPLETE - Ready for Browser Testing
