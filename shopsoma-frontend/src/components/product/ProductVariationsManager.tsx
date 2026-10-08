import React, { useState, useEffect } from 'react';
import {
  Edit2,
  Trash2,
  Plus,
  Check,
  X,
  AlertCircle,
  Loader2,
  Palette,
  Image as ImageIcon,
  Layers,
  ArrowLeft,
  Upload,
} from 'lucide-react';
import type { Variation, ProductImage } from '../../types';
import api from '../../services/api';
import { productService } from '../../services/productService';
import { adminService } from '../../services/adminService';
import { normalizeProductImageUrl } from '../../utils/productImages';

export interface ProductVariationsManagerProps {
  productId: string;
  initialVariations?: Variation[];
  productImages?: ProductImage[];
  basePrice?: number;
  compareAtPrice?: number;
  currency?: string;
  isAdmin?: boolean;
  onVariationsUpdated?: (variations: Variation[]) => void;
}

const STANDARD_SIZES = [
  'XXS',
  'XS',
  'S',
  'M',
  'L',
  'XL',
  'XXL',
  'XXXL',
  'One/Size',
] as const;

export default function ProductVariationsManager({
  productId,
  initialVariations = [],
  productImages = [],
  basePrice = 0,
  compareAtPrice,
  currency = 'NGN',
  isAdmin = false,
  onVariationsUpdated,
}: ProductVariationsManagerProps) {
  const [variations, setVariations] = useState<Variation[]>(initialVariations);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Selected variation for editing
  const [selectedVariationId, setSelectedVariationId] = useState<string | null>(null);

  // Edit form state
  const [editTitle, setEditTitle] = useState('');
  const [editColorHex, setEditColorHex] = useState('#000000');
  const [editIsActive, setEditIsActive] = useState(true);
  const [editInheritsPrice, setEditInheritsPrice] = useState(true);
  const [editPrice, setEditPrice] = useState('');
  const [editInheritsSalePrice, setEditInheritsSalePrice] = useState(true);
  const [editSalePrice, setEditSalePrice] = useState('');
  const [editSizes, setEditSizes] = useState<Array<{ id?: string; size: string; stock: number }>>([]);
  const [editImages, setEditImages] = useState<string[]>([]);

  // Add nested size state inside editor
  const [newSizeName, setNewSizeName] = useState('M');
  const [newSizeStock, setNewSizeStock] = useState('10');

  // Image selector modal state
  const [isImagePickerOpen, setIsImagePickerOpen] = useState(false);
  const [isUploadingImage, setIsUploadingImage] = useState(false);

  // Delete confirmation modal state
  const [deletingVariation, setDeletingVariation] = useState<Variation | null>(null);

  // Accent styling based on role
  const primaryBg = isAdmin ? 'bg-blue-600 hover:bg-blue-700' : 'bg-[#105E53] hover:bg-[#0c4c45]';
  const primaryText = isAdmin ? 'text-blue-600' : 'text-[#105E53]';
  const primaryBorder = isAdmin ? 'border-blue-600' : 'border-[#105E53]';
  const primaryRing = isAdmin ? 'focus:ring-blue-500' : 'focus:ring-[#105E53]';

  useEffect(() => {
    if (initialVariations && initialVariations.length > 0) {
      setVariations(initialVariations);
    } else if (productId) {
      loadVariations();
    }
  }, [productId, initialVariations]);

  // Load variations from server
  const loadVariations = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      const data = isAdmin
        ? await adminService.getProductVariations(productId)
        : await productService.getVariations(productId);
      setVariations(data || []);
      if (onVariationsUpdated) {
        onVariationsUpdated(data || []);
      }
    } catch (err: any) {
      console.error('Failed to load variations', err);
      setErrorMsg(err.response?.data?.detail || 'Failed to load variations');
    } finally {
      setLoading(false);
    }
  };

  // Select a variation to edit
  const startEditing = (variation: Variation) => {
    setSelectedVariationId(variation.id || null);
    setEditTitle(variation.title);
    setEditColorHex(variation.color_hex || '#000000');
    setEditIsActive(variation.is_active ?? true);
    setEditInheritsPrice(variation.inherits_price ?? true);
    setEditPrice(variation.price !== undefined && variation.price !== null ? variation.price.toString() : '');
    setEditInheritsSalePrice(variation.inherits_sale_price ?? true);
    setEditSalePrice(variation.sale_price !== undefined && variation.sale_price !== null ? variation.sale_price.toString() : '');
    setEditSizes(
      (variation.size_stocks || []).map((s) => ({
        id: s.id,
        size: s.size,
        stock: s.stock,
      }))
    );
    setEditImages([...(variation.images || [])]);
    setErrorMsg(null);
    setSuccessMsg(null);
  };

  const cancelEditing = () => {
    setSelectedVariationId(null);
    setErrorMsg(null);
  };

  // Nested sizes management in editor
  const handleAddSize = () => {
    if (!newSizeName.trim()) return;
    const stockVal = parseInt(newSizeStock, 10);
    if (isNaN(stockVal) || stockVal < 0) {
      setErrorMsg('Stock quantity cannot be negative.');
      return;
    }
    const normalizedNew = newSizeName.trim().toUpperCase();
    if (editSizes.some((s) => s.size.trim().toUpperCase() === normalizedNew)) {
      setErrorMsg(`Size "${newSizeName}" already exists for this variation.`);
      return;
    }
    setEditSizes([...editSizes, { size: newSizeName.trim(), stock: stockVal }]);
    setNewSizeStock('10');
    setErrorMsg(null);
  };

  const handleRemoveSize = (index: number) => {
    setEditSizes(editSizes.filter((_, idx) => idx !== index));
  };

  const handleStockChange = (index: number, val: string) => {
    const parsed = parseInt(val, 10);
    setEditSizes(
      editSizes.map((s, idx) => (idx === index ? { ...s, stock: isNaN(parsed) ? 0 : parsed } : s))
    );
  };

  // Image actions scoped strictly to this variation
  const handleToggleVariationImage = (imageUrl: string) => {
    if (editImages.includes(imageUrl)) {
      setEditImages(editImages.filter((url) => url !== imageUrl));
    } else {
      setEditImages([...editImages, imageUrl]);
    }
  };

  const handleUploadVariationImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    const file = files[0];

    try {
      setIsUploadingImage(true);
      setErrorMsg(null);

      // Upload to server
      const uploadRes = await productService.uploadImage(file);
      const imageUrl = uploadRes.original;

      // Add to product gallery as a non-primary image so backend validation accepts ownership
      if (isAdmin) {
        await api.post(`/admin/products/${productId}/images`, {
          image_url: imageUrl,
          thumbnail_url: uploadRes.thumbnail,
          alt_text: `${editTitle || 'Variation'} image`,
          is_primary: false,
          storage_keys: uploadRes.storage_keys,
        });
      } else {
        await productService.addProductImage(productId, {
          image_url: imageUrl,
          thumbnail_url: uploadRes.thumbnail,
          alt_text: `${editTitle || 'Variation'} image`,
          is_primary: false,
          storage_keys: uploadRes.storage_keys,
        });
      }

      // Associate with this variation
      setEditImages((prev) => [...prev, imageUrl]);
      setSuccessMsg('Image uploaded and added to variation preview. Click "Save Variation Changes" below to save.');
    } catch (err: any) {
      console.error('Failed to upload variation image', err);
      setErrorMsg(err.response?.data?.detail || 'Failed to upload variation image.');
    } finally {
      setIsUploadingImage(false);
      if (e.target) e.target.value = '';
    }
  };

  // Save selected variation
  const handleSaveVariation = async () => {
    if (!selectedVariationId) return;

    if (!editTitle.trim()) {
      setErrorMsg('Variation title is required.');
      return;
    }

    let parsedPrice: number | undefined = undefined;
    if (!editInheritsPrice) {
      parsedPrice = parseFloat(editPrice);
      if (isNaN(parsedPrice) || parsedPrice <= 0) {
        setErrorMsg('Custom price must be greater than 0.');
        return;
      }
      if (parsedPrice > 999999.99) {
        setErrorMsg('Price cannot exceed 999,999.99.');
        return;
      }
    }

    let parsedSalePrice: number | undefined = undefined;
    if (!editInheritsSalePrice && editSalePrice) {
      parsedSalePrice = parseFloat(editSalePrice);
      if (isNaN(parsedSalePrice) || parsedSalePrice <= 0) {
        setErrorMsg('Sale price must be greater than 0.');
        return;
      }
      const regularPrice = parsedPrice !== undefined ? parsedPrice : basePrice;
      if (parsedSalePrice >= regularPrice) {
        setErrorMsg('Sale price must be less than regular price.');
        return;
      }
    }

    // Validate size stock values
    for (const s of editSizes) {
      if (s.stock < 0) {
        setErrorMsg(`Stock for size ${s.size} cannot be negative.`);
        return;
      }
    }

    try {
      setSaving(true);
      setErrorMsg(null);
      setSuccessMsg(null);

      const payload = {
        title: editTitle.trim(),
        type: 'color',
        color_hex: editColorHex,
        price: editInheritsPrice ? undefined : parsedPrice,
        sale_price: editInheritsSalePrice ? undefined : parsedSalePrice,
        inherits_price: editInheritsPrice,
        inherits_sale_price: editInheritsSalePrice,
        is_active: editIsActive,
        images: editImages,
        sizes: editSizes.map((s) => ({
          size: s.size,
          stock: s.stock,
        })),
      };

      const updated = isAdmin
        ? await adminService.updateProductVariation(productId, selectedVariationId, payload)
        : await productService.updateVariation(productId, selectedVariationId, payload);

      setSuccessMsg(`Variation "${updated.title}" saved successfully.`);

      // Update in local state preserving stable identity
      const updatedList = variations.map((v) => (v.id === selectedVariationId ? updated : v));
      setVariations(updatedList);
      if (onVariationsUpdated) {
        onVariationsUpdated(updatedList);
      }

      // Exit edit view after brief confirmation
      setTimeout(() => {
        setSelectedVariationId(null);
        setSuccessMsg(null);
      }, 1200);
    } catch (err: any) {
      console.error('Failed to save variation', err);
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map((d: any) => d.msg).join(', ') : 'Failed to save variation.');
      setErrorMsg(msg);
    } finally {
      setSaving(false);
    }
  };

  // Delete variation
  const handleDeleteVariation = async () => {
    if (!deletingVariation || !deletingVariation.id) return;

    try {
      setSaving(true);
      setErrorMsg(null);

      if (isAdmin) {
        await adminService.deleteProductVariation(productId, deletingVariation.id);
      } else {
        await productService.deleteVariation(productId, deletingVariation.id);
      }

      const remaining = variations.filter((v) => v.id !== deletingVariation.id);
      setVariations(remaining);
      if (onVariationsUpdated) {
        onVariationsUpdated(remaining);
      }

      setDeletingVariation(null);
      setSuccessMsg(`Variation "${deletingVariation.title}" deleted.`);
      setTimeout(() => setSuccessMsg(null), 2500);
    } catch (err: any) {
      console.error('Failed to delete variation', err);
      setErrorMsg(err.response?.data?.detail || 'Failed to delete variation.');
    } finally {
      setSaving(false);
    }
  };

  const selectedVariation = variations.find((v) => v.id === selectedVariationId);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden" data-testid="product-variations-manager">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg ${isAdmin ? 'bg-blue-50 text-blue-600' : 'bg-emerald-50 text-[#105E53]'}`}>
            <Layers className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Product Variations</h2>
            <p className="text-xs text-gray-500 mt-0.5">
              Manage color options, variation-specific images, pricing overrides, and size stock.
            </p>
          </div>
        </div>
      </div>

      {/* Global Alerts */}
      <div className="px-6 pt-4">
        {errorMsg && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3.5 flex items-start gap-2.5 text-sm text-red-700" role="alert">
            <AlertCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
            <div className="flex-1">
              <strong className="font-semibold">Error:</strong> {errorMsg}
            </div>
            <button type="button" onClick={() => setErrorMsg(null)} className="text-red-400 hover:text-red-600">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {successMsg && (
          <div className="mb-4 bg-emerald-50 border border-emerald-200 rounded-lg p-3.5 flex items-start gap-2.5 text-sm text-emerald-800" role="status">
            <Check className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
            <div className="flex-1 font-medium">{successMsg}</div>
            <button type="button" onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-600">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>

      {/* Body Content */}
      <div className="p-6">
        {selectedVariation ? (
          /* ================================================================= */
          /* Selected Variation Editing View                                    */
          /* ================================================================= */
          <div className="space-y-6" data-testid="selected-variation-editor">
            {/* Navigation back and Identity Header */}
            <div className="flex items-center justify-between pb-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={cancelEditing}
                  className="p-1.5 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition"
                  title="Back to variations list"
                  aria-label="Back to variations list"
                >
                  <ArrowLeft className="h-5 w-5" />
                </button>
                <div>
                  <h3 className="text-base font-semibold text-gray-900">
                    Editing Variation: <span className={primaryText}>{selectedVariation.title}</span>
                  </h3>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500">
                    <span className="font-mono bg-gray-100 px-2 py-0.5 rounded text-[11px] text-gray-600">
                      Stable ID: {selectedVariation.id}
                    </span>
                    <span>•</span>
                    <span className="text-gray-500">ID preserved across saves</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={cancelEditing}
                  disabled={saving}
                  className="px-3.5 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveVariation}
                  disabled={saving}
                  className={`inline-flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium text-white ${primaryBg} rounded-lg transition disabled:opacity-50`}
                >
                  {saving ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Check className="h-4 w-4" />
                      Save Variation
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Basic Info (Title, Color, Active) */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <label htmlFor="varTitle" className="block text-xs font-medium text-gray-700 mb-1.5">
                  Variation Title / Color Name *
                </label>
                <input
                  id="varTitle"
                  type="text"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  className={`w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm focus:outline-none ${primaryBorder} ${primaryRing}`}
                  placeholder="e.g., Crimson Red, Navy Blue"
                  required
                />
              </div>

              <div>
                <label htmlFor="varColorHex" className="block text-xs font-medium text-gray-700 mb-1.5">
                  Color Swatch / Hex
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    id="varColorPicker"
                    value={editColorHex || '#000000'}
                    onChange={(e) => setEditColorHex(e.target.value)}
                    className="w-10 h-9 p-1 border border-gray-300 rounded cursor-pointer"
                    aria-label="Color picker"
                  />
                  <input
                    id="varColorHex"
                    type="text"
                    value={editColorHex}
                    onChange={(e) => setEditColorHex(e.target.value)}
                    className={`flex-1 rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm font-mono focus:outline-none ${primaryBorder} ${primaryRing}`}
                    placeholder="#FFFFFF"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1.5">
                  Availability Status
                </label>
                <div className="flex items-center h-[38px] px-3.5 bg-white border border-gray-300 rounded-lg">
                  <label className="relative inline-flex items-center cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={editIsActive}
                      onChange={(e) => setEditIsActive(e.target.checked)}
                      className="sr-only peer"
                      aria-label="Variation active state"
                    />
                    <div className="relative w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[#105E53]"></div>
                    <span className="ml-3 text-xs sm:text-sm text-gray-700 font-medium">
                      {editIsActive ? 'Active (Purchasable)' : 'Inactive (Hidden)'}
                    </span>
                  </label>
                </div>
              </div>
            </div>

            {/* Pricing Section */}
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-4">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-gray-600">
                Pricing Settings
              </h4>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="varPrice" className="text-xs font-medium text-gray-700">
                      Regular Price ({currency})
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editInheritsPrice}
                        onChange={(e) => setEditInheritsPrice(e.target.checked)}
                        className="rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                      />
                      <span>Inherit product base price ({currency.length > 1 ? `${currency} ` : currency}{basePrice})</span>
                    </label>
                  </div>
                  <input
                    id="varPrice"
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={editInheritsPrice ? basePrice : editPrice}
                    onChange={(e) => setEditPrice(e.target.value)}
                    disabled={editInheritsPrice}
                    className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                    placeholder="Enter custom regular price"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="varSalePrice" className="text-xs font-medium text-gray-700">
                      Sale Price ({currency})
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editInheritsSalePrice}
                        onChange={(e) => setEditInheritsSalePrice(e.target.checked)}
                        className="rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                      />
                      <span>Inherit product compare price</span>
                    </label>
                  </div>
                  <input
                    id="varSalePrice"
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={editInheritsSalePrice ? (compareAtPrice || '') : editSalePrice}
                    onChange={(e) => setEditSalePrice(e.target.value)}
                    disabled={editInheritsSalePrice}
                    className="w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                    placeholder="Optional sale price"
                  />
                </div>
              </div>
            </div>

            {/* Nested Sizes & Inventory */}
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">Size Stock Inventory</h4>
                  <p className="text-xs text-gray-500">Configure size stock counts specifically for this color variation.</p>
                </div>
              </div>

              {/* Add Size row */}
              <div className="p-4 bg-white border-b border-gray-100 flex flex-wrap items-end gap-3">
                <div>
                  <label htmlFor="newSizeSelect" className="block text-xs font-medium text-gray-600 mb-1">
                    Size
                  </label>
                  <select
                    id="newSizeSelect"
                    value={newSizeName}
                    onChange={(e) => setNewSizeName(e.target.value)}
                    className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm"
                  >
                    {STANDARD_SIZES.map((sz) => (
                      <option key={sz} value={sz}>
                        {sz}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label htmlFor="newSizeStockInput" className="block text-xs font-medium text-gray-600 mb-1">
                    Stock Quantity
                  </label>
                  <input
                    id="newSizeStockInput"
                    type="number"
                    min="0"
                    value={newSizeStock}
                    onChange={(e) => setNewSizeStock(e.target.value)}
                    className="w-28 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm"
                    placeholder="0"
                  />
                </div>

                <button
                  type="button"
                  onClick={handleAddSize}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white ${primaryBg} rounded-lg transition`}
                >
                  <Plus className="h-4 w-4" />
                  Add Size
                </button>
              </div>

              {/* Sizes table */}
              {editSizes.length > 0 ? (
                <div className="divide-y divide-gray-100">
                  {editSizes.map((s, idx) => (
                    <div key={s.id || idx} className="px-4 py-3 flex items-center justify-between hover:bg-gray-50 transition">
                      <div className="flex items-center gap-3">
                        <span className="w-16 font-semibold text-sm text-gray-800 bg-gray-100 px-2 py-1 rounded text-center">
                          {s.size}
                        </span>
                        {s.id && (
                          <span className="text-[11px] font-mono text-gray-400">
                            ID: {s.id.slice(0, 8)}...
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-4">
                        <div className="flex items-center gap-2">
                          <label htmlFor={`stock-${idx}`} className="text-xs text-gray-500">Stock:</label>
                          <input
                            id={`stock-${idx}`}
                            type="number"
                            min="0"
                            value={s.stock}
                            onChange={(e) => handleStockChange(idx, e.target.value)}
                            className="w-24 rounded border border-gray-300 px-2.5 py-1 text-sm text-right font-medium"
                          />
                        </div>

                        <button
                          type="button"
                          onClick={() => handleRemoveSize(idx)}
                          className="text-red-500 hover:text-red-700 p-1 hover:bg-red-50 rounded"
                          title="Remove size"
                          aria-label={`Remove size ${s.size}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-6 text-center text-sm text-gray-500">
                  No sizes added to this variation yet. Add a size above.
                </div>
              )}
            </div>

            {/* Variation-Specific Images */}
            <div className="border border-gray-200 rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-3 border-b border-gray-200 flex items-center justify-between">
                <div>
                  <h4 className="text-sm font-semibold text-gray-900">Variation-Specific Images</h4>
                  <p className="text-xs text-gray-500">
                    Images scoped strictly to this variation. Changing these does not alter the product gallery or other variations.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setIsImagePickerOpen(true)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                  >
                    <ImageIcon className="h-3.5 w-3.5" />
                    Select from Product Images
                  </button>

                  <label className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white ${primaryBg} rounded-lg cursor-pointer transition`}>
                    {isUploadingImage ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
                    <span>Upload New</span>
                    <input
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={handleUploadVariationImage}
                      disabled={isUploadingImage}
                    />
                  </label>
                </div>
              </div>

              <div className="p-4">
                {editImages.length > 0 ? (
                  <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3">
                    {editImages.map((imgUrl, idx) => (
                      <div key={idx} className="group relative aspect-square rounded-lg border border-gray-200 overflow-hidden bg-gray-50">
                        <img
                          src={normalizeProductImageUrl(imgUrl)}
                          alt={`Variation ${idx + 1}`}
                          className="w-full h-full object-cover"
                        />
                        <button
                          type="button"
                          onClick={() => handleToggleVariationImage(imgUrl)}
                          className="absolute top-1.5 right-1.5 p-1 bg-red-600 text-white rounded-full opacity-0 group-hover:opacity-100 transition shadow hover:bg-red-700"
                          title="Remove image from variation"
                          aria-label="Remove image from variation"
                        >
                          <X className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-6 text-sm text-gray-500">
                    <ImageIcon className="h-8 w-8 mx-auto text-gray-300 mb-1" />
                    No variation-specific images selected. Select from product images or upload above.
                  </div>
                )}
              </div>
            </div>

            {/* Bottom inline feedback alerts */}
            {errorMsg && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3.5 flex items-start gap-2.5 text-sm text-red-700" role="alert">
                <AlertCircle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                <div className="flex-1">
                  <strong className="font-semibold">Error:</strong> {errorMsg}
                </div>
                <button type="button" onClick={() => setErrorMsg(null)} className="text-red-400 hover:text-red-600">
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {successMsg && (
              <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3.5 flex items-start gap-2.5 text-sm text-emerald-800" role="status">
                <Check className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
                <div className="flex-1 font-medium">{successMsg}</div>
                <button type="button" onClick={() => setSuccessMsg(null)} className="text-emerald-400 hover:text-emerald-600">
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}

            {/* Bottom Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
              <button
                type="button"
                onClick={cancelEditing}
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveVariation}
                disabled={saving}
                className={`inline-flex items-center gap-2 px-5 py-2 text-sm font-medium text-white ${primaryBg} rounded-lg transition disabled:opacity-50`}
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4" />
                    Save Variation Changes
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          /* ================================================================= */
          /* Variations Listing View                                            */
          /* ================================================================= */
          <div>
            {loading ? (
              <div className="flex items-center justify-center py-12 text-gray-500 gap-2">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Loading product variations...</span>
              </div>
            ) : variations.length > 0 ? (
              <div className="divide-y divide-gray-200">
                {variations.map((v) => {
                  const sizeStocks = v.size_stocks || [];
                  const totalStock = sizeStocks.reduce((sum, s) => sum + (s.stock || 0), 0);
                  const firstImage = v.images && v.images.length > 0 ? v.images[0] : null;

                  return (
                    <div
                      key={v.id}
                      className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-gray-50 p-3 rounded-lg transition"
                      data-testid={`variation-row-${v.id}`}
                    >
                      {/* Left: Thumbnail & Details */}
                      <div className="flex items-center gap-3.5">
                        <div className="w-14 h-14 rounded-lg border border-gray-200 overflow-hidden bg-gray-100 shrink-0 flex items-center justify-center">
                          {firstImage ? (
                            <img
                              src={normalizeProductImageUrl(firstImage)}
                              alt={v.title}
                              className="w-full h-full object-cover"
                            />
                          ) : (
                            <div
                              className="w-full h-full flex items-center justify-center"
                              style={{ backgroundColor: v.color_hex || '#e5e7eb' }}
                            >
                              <Palette className="h-5 w-5 text-white/80 drop-shadow" />
                            </div>
                          )}
                        </div>

                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-gray-900 text-sm">{v.title}</span>
                            {v.color_hex && (
                              <span
                                className="inline-block w-3.5 h-3.5 rounded-full border border-gray-300"
                                style={{ backgroundColor: v.color_hex }}
                                title={v.color_hex}
                              />
                            )}
                            <span
                              className={`px-2 py-0.5 text-[11px] font-medium rounded-full ${
                                v.is_active !== false
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : 'bg-gray-100 text-gray-600'
                              }`}
                            >
                              {v.is_active !== false ? 'Active' : 'Inactive'}
                            </span>
                          </div>

                          <div className="flex flex-wrap items-center gap-2 mt-1 text-xs text-gray-500">
                            <span className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-[10px] text-gray-600">
                              ID: {v.id ? v.id.slice(0, 8) : 'N/A'}...
                            </span>
                            <span>•</span>
                            <span>
                              {v.price !== undefined && v.price !== null
                                ? `${currency.length > 1 ? `${currency} ` : currency}${v.price}`
                                : `Base price (${currency.length > 1 ? `${currency} ` : currency}${basePrice})`}
                            </span>
                            {v.sale_price !== undefined && v.sale_price !== null && (
                              <span className="text-emerald-600 font-medium">
                                (Sale: {currency.length > 1 ? `${currency} ` : currency}{v.sale_price})
                              </span>
                            )}
                            <span>•</span>
                            <span className="font-medium text-gray-700">
                              Total Stock: {totalStock}
                            </span>
                          </div>

                          {/* Sizes chips */}
                          {sizeStocks.length > 0 && (
                            <div className="flex flex-wrap items-center gap-1.5 mt-2">
                              {sizeStocks.map((s, idx) => (
                                <span
                                  key={s.id || idx}
                                  className="inline-flex items-center gap-1 bg-white border border-gray-200 px-2 py-0.5 rounded text-[11px] text-gray-700"
                                >
                                  <span className="font-semibold">{s.size}:</span>
                                  <span>{s.stock}</span>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Right: Actions */}
                      <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                        <button
                          type="button"
                          onClick={() => startEditing(v)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition shadow-sm"
                          data-testid={`edit-variation-${v.id}`}
                        >
                          <Edit2 className="h-3.5 w-3.5 text-gray-500" />
                          <span>Edit Variation</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => setDeletingVariation(v)}
                          className="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition"
                          title="Delete variation"
                          aria-label={`Delete variation ${v.title}`}
                          data-testid={`delete-variation-${v.id}`}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-10 text-gray-500">
                <Layers className="h-10 w-10 mx-auto text-gray-300 mb-2" />
                <p className="text-sm font-medium text-gray-700">No variations configured for this product.</p>
                <p className="text-xs text-gray-500 mt-1">
                  Variations are defined during product creation or through bulk uploads.
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* =================================================================== */}
      {/* Product Image Selection Modal                                       */}
      {/* =================================================================== */}
      {isImagePickerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-900">Select Variation Images</h3>
                <p className="text-xs text-gray-500">Pick from existing images attached to this product.</p>
              </div>
              <button
                type="button"
                onClick={() => setIsImagePickerOpen(false)}
                className="text-gray-400 hover:text-gray-600 p-1"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1">
              {productImages.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  {productImages.map((img) => {
                    const isSelected = editImages.includes(img.image_url);
                    return (
                      <div
                        key={img.id}
                        onClick={() => handleToggleVariationImage(img.image_url)}
                        className={`group relative aspect-square rounded-lg border overflow-hidden cursor-pointer transition ${
                          isSelected
                            ? 'border-[#105E53] ring-2 ring-[#105E53]'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        <img
                          src={normalizeProductImageUrl(img.thumbnail_url || img.image_url)}
                          alt="Product option"
                          className="w-full h-full object-cover"
                        />
                        <div
                          className={`absolute top-2 right-2 rounded-full p-1 transition ${
                            isSelected ? 'bg-[#105E53] text-white' : 'bg-black/40 text-transparent'
                          }`}
                        >
                          <Check className="h-4 w-4" />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-10 text-gray-500 text-sm">
                  No images in the product gallery to choose from. Upload an image above.
                </div>
              )}
            </div>

            <div className="px-6 py-3 bg-gray-50 border-t border-gray-200 flex justify-end">
              <button
                type="button"
                onClick={() => setIsImagePickerOpen(false)}
                className={`px-4 py-2 text-sm font-medium text-white ${primaryBg} rounded-lg transition`}
              >
                Done ({editImages.length} selected)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* Delete Confirmation Modal                                           */}
      {/* =================================================================== */}
      {deletingVariation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center gap-3 text-red-600">
              <div className="p-2 bg-red-50 rounded-full">
                <Trash2 className="h-6 w-6" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900">Delete Variation</h3>
            </div>

            <p className="text-sm text-gray-600">
              Are you sure you want to delete the variation{' '}
              <strong className="text-gray-900 font-semibold">"{deletingVariation.title}"</strong>?
              Untouched variations and the product gallery will not be changed.
            </p>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setDeletingVariation(null)}
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteVariation}
                disabled={saving}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg transition disabled:opacity-50"
              >
                {saving && <Loader2 className="h-4 w-4 animate-spin" />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
