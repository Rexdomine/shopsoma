import { useState, useEffect, useMemo } from 'react';
import { Plus, Edit2, Trash2, Loader2, AlertCircle, Check, X, Sparkles } from 'lucide-react';
import type { ProductVariant } from '../../types';
import { productService } from '../../services/productService';
import { adminService } from '../../services/adminService';

export interface ProductSizeOptionsManagerProps {
  productId: string;
  initialVariants?: ProductVariant[];
  basePrice?: number;
  currency?: string;
  madeToOrder?: boolean;
  isAdmin?: boolean;
  onVariantsUpdated?: (variants: ProductVariant[]) => void;
}

const PRESET_SIZING_SYSTEMS = {
  'One/Size': ['One/Size'],
  'US Sizing': ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'],
  'UK Sizing': ['4', '6', '8', '10', '12', '14', '16', '18', '20', '22'],
  'EU Sizing': ['32', '34', '36', '38', '40', '42', '44', '46', '48', '50'],
} as const;

type SizingSystem = keyof typeof PRESET_SIZING_SYSTEMS | 'Custom';

export default function ProductSizeOptionsManager({
  productId,
  initialVariants = [],
  basePrice = 0,
  currency = '£',
  madeToOrder = false,
  isAdmin = false,
  onVariantsUpdated,
}: ProductSizeOptionsManagerProps) {
  const [variants, setVariants] = useState<ProductVariant[]>(initialVariants);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Add modal state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedSystem, setSelectedSystem] = useState<SizingSystem>('US Sizing');
  const [newSize, setNewSize] = useState('');
  const [newStock, setNewStock] = useState('10');
  const [newPrice, setNewPrice] = useState(basePrice > 0 ? basePrice.toString() : '');
  const [newIsAvailable, setNewIsAvailable] = useState(true);

  // Edit modal state
  const [editingVariant, setEditingVariant] = useState<ProductVariant | null>(null);
  const [editSize, setEditSize] = useState('');
  const [editStock, setEditStock] = useState('0');
  const [editPrice, setEditPrice] = useState('');
  const [editIsAvailable, setEditIsAvailable] = useState(true);

  // Delete modal state
  const [deletingVariant, setDeletingVariant] = useState<ProductVariant | null>(null);

  // Color styles depending on isAdmin
  const primaryBg = isAdmin ? 'bg-blue-600 hover:bg-blue-700' : 'bg-[#105E53] hover:bg-[#0c4c45]';
  const primaryText = isAdmin ? 'text-blue-600' : 'text-[#105E53]';
  const primaryBorder = isAdmin ? 'border-blue-600' : 'border-[#105E53]';
  const primaryRing = isAdmin ? 'focus:ring-blue-500' : 'focus:ring-[#105E53]';

  useEffect(() => {
    if (initialVariants && initialVariants.length > 0) {
      setVariants(initialVariants);
    }
  }, [initialVariants]);

  // Set default price when basePrice changes and modal opens
  useEffect(() => {
    if (basePrice > 0 && !newPrice) {
      setNewPrice(basePrice.toString());
    }
  }, [basePrice, newPrice]);

  const existingSizeLabels = useMemo(() => {
    return new Set(
      variants
        .map((v) => (v.size || '').trim().toLowerCase())
        .filter(Boolean)
    );
  }, [variants]);

  const fetchVariants = async () => {
    try {
      setLoading(true);
      setErrorMsg(null);
      let updatedVariants: ProductVariant[] = [];
      if (isAdmin) {
        updatedVariants = await adminService.getProductVariants(productId);
      } else {
        updatedVariants = await productService.getProductVariants(productId);
      }
      setVariants(updatedVariants);
      onVariantsUpdated?.(updatedVariants);
    } catch (err: any) {
      console.error('Failed to reload variants:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenAddModal = () => {
    setNewSize('');
    setNewStock(madeToOrder ? '0' : '10');
    setNewPrice(basePrice > 0 ? basePrice.toString() : '');
    setNewIsAvailable(true);
    setSelectedSystem('US Sizing');
    setErrorMsg(null);
    setSuccessMsg(null);
    setIsAddModalOpen(true);
  };

  const handleOpenEditModal = (variant: ProductVariant) => {
    setEditingVariant(variant);
    setEditSize(variant.size || 'One/Size');
    setEditStock((variant.stock ?? 0).toString());
    setEditPrice((variant.price ?? basePrice).toString());
    setEditIsAvailable(variant.is_available ?? true);
    setErrorMsg(null);
    setSuccessMsg(null);
  };

  const handleCreateVariant = async (e: React.FormEvent) => {
    e.preventDefault();
    const sizeName = newSize.trim();
    if (!sizeName) {
      setErrorMsg('Please enter or select a size name');
      return;
    }

    if (existingSizeLabels.has(sizeName.toLowerCase())) {
      setErrorMsg(`Size option "${sizeName}" already exists for this product.`);
      return;
    }

    const parsedStock = madeToOrder ? 0 : parseInt(newStock, 10);
    if (!madeToOrder && (isNaN(parsedStock) || parsedStock < 0)) {
      setErrorMsg('Stock quantity must be a non-negative number');
      return;
    }

    const parsedPrice = newPrice ? parseFloat(newPrice) : basePrice;
    if (isNaN(parsedPrice) || parsedPrice <= 0) {
      setErrorMsg('Price must be greater than 0');
      return;
    }

    try {
      setActionLoading(true);
      setErrorMsg(null);

      const payload = {
        size: sizeName,
        stock: parsedStock,
        price: parsedPrice,
        is_available: newIsAvailable,
      };

      if (isAdmin) {
        await adminService.createProductVariant(productId, payload);
      } else {
        await productService.createVariant(productId, payload);
      }

      setSuccessMsg(`Size "${sizeName}" added successfully.`);
      setIsAddModalOpen(false);
      await fetchVariants();
    } catch (err: any) {
      console.error('Error creating size variant:', err);
      const detail = err.response?.data?.detail;
      setErrorMsg(typeof detail === 'string' ? detail : 'Failed to create size option.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleUpdateVariant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingVariant) return;

    const sizeName = editSize.trim();
    if (!sizeName) {
      setErrorMsg('Size name cannot be empty');
      return;
    }

    // Check duplicate if size was changed
    if (
      sizeName.toLowerCase() !== (editingVariant.size || '').toLowerCase() &&
      existingSizeLabels.has(sizeName.toLowerCase())
    ) {
      setErrorMsg(`Size option "${sizeName}" already exists for this product.`);
      return;
    }

    const parsedStock = madeToOrder ? 0 : parseInt(editStock, 10);
    if (!madeToOrder && (isNaN(parsedStock) || parsedStock < 0)) {
      setErrorMsg('Stock quantity must be a non-negative number');
      return;
    }

    const parsedPrice = editPrice ? parseFloat(editPrice) : basePrice;
    if (isNaN(parsedPrice) || parsedPrice <= 0) {
      setErrorMsg('Price must be greater than 0');
      return;
    }

    try {
      setActionLoading(true);
      setErrorMsg(null);

      const payload = {
        size: sizeName,
        stock: parsedStock,
        price: parsedPrice,
        is_available: editIsAvailable,
      };

      if (isAdmin) {
        await adminService.updateProductVariant(productId, editingVariant.id, payload);
      } else {
        await productService.updateVariant(productId, editingVariant.id, payload);
      }

      setSuccessMsg(`Size option "${sizeName}" updated successfully.`);
      setEditingVariant(null);
      await fetchVariants();
    } catch (err: any) {
      console.error('Error updating size variant:', err);
      const detail = err.response?.data?.detail;
      setErrorMsg(typeof detail === 'string' ? detail : 'Failed to update size option.');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeleteVariant = async () => {
    if (!deletingVariant) return;

    try {
      setActionLoading(true);
      setErrorMsg(null);

      if (isAdmin) {
        await adminService.deleteProductVariant(productId, deletingVariant.id);
      } else {
        await productService.deleteVariant(productId, deletingVariant.id);
      }

      setSuccessMsg(`Size option "${deletingVariant.size || 'One/Size'}" removed.`);
      setDeletingVariant(null);
      await fetchVariants();
    } catch (err: any) {
      console.error('Error deleting size variant:', err);
      const detail = err.response?.data?.detail;
      setErrorMsg(typeof detail === 'string' ? detail : 'Failed to delete size option.');
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <span>Size Options & Inventory</span>
            {variants.length > 0 && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                {variants.length} {variants.length === 1 ? 'size' : 'sizes'}
              </span>
            )}
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Manage available size variants, individual stock counts, and price overrides.
          </p>
        </div>

        <button
          type="button"
          onClick={handleOpenAddModal}
          className={`inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white rounded-lg transition shadow-sm ${primaryBg}`}
        >
          <Plus className="h-4 w-4" />
          <span>Add Size Option</span>
        </button>
      </div>

      {/* Messages */}
      <div className="px-6 pt-4">
        {errorMsg && (
          <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-700 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
            <div className="flex-1">{errorMsg}</div>
            <button
              type="button"
              onClick={() => setErrorMsg(null)}
              className="text-red-400 hover:text-red-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {successMsg && (
          <div className="mb-4 bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-xs text-emerald-800 flex items-start gap-2">
            <Check className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
            <div className="flex-1">{successMsg}</div>
            <button
              type="button"
              onClick={() => setSuccessMsg(null)}
              className="text-emerald-400 hover:text-emerald-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {madeToOrder && (
          <div className="mb-4 bg-amber-50 border border-amber-200 rounded-lg p-3 text-xs text-amber-800 flex items-start gap-2">
            <Sparkles className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <strong>Made to Order Product:</strong> Stock counts are managed on demand and display as available for custom fabrication.
            </div>
          </div>
        )}
      </div>

      {/* Body: Variants List */}
      <div className="p-6 pt-2">
        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center text-gray-500">
            <Loader2 className="h-6 w-6 animate-spin text-gray-400 mb-2" />
            <p className="text-xs">Loading size options...</p>
          </div>
        ) : variants.length === 0 ? (
          <div className="py-10 text-center border-2 border-dashed border-gray-200 rounded-xl bg-gray-50/50">
            <div className="w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-3 text-gray-400">
              <Plus className="h-6 w-6" />
            </div>
            <h3 className="text-sm font-semibold text-gray-800 mb-1">No Size Options Configured</h3>
            <p className="text-xs text-gray-500 max-w-sm mx-auto mb-4">
              Add standard or custom size options (e.g. S, M, L, XL, or One/Size) to let customers pick their fit.
            </p>
            <button
              type="button"
              onClick={handleOpenAddModal}
              className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white rounded-lg transition shadow-sm ${primaryBg}`}
            >
              <Plus className="h-4 w-4" />
              <span>Add First Size Option</span>
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-gray-200 text-gray-500 bg-gray-50/80">
                  <th className="py-3 px-4 font-semibold">Size Option</th>
                  <th className="py-3 px-4 font-semibold">Stock</th>
                  <th className="py-3 px-4 font-semibold">Price</th>
                  <th className="py-3 px-4 font-semibold">Status</th>
                  <th className="py-3 px-4 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {variants.map((variant) => {
                  const sizeLabel = variant.size || 'One/Size';
                  const isAvailable = variant.is_available ?? true;
                  const stockCount = variant.stock ?? 0;
                  const price = variant.price ?? basePrice;

                  return (
                    <tr key={variant.id} className="hover:bg-gray-50/60 transition">
                      {/* Size */}
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-2">
                          <span className="inline-flex items-center justify-center min-w-[32px] h-8 px-2.5 rounded-lg bg-gray-100 border border-gray-200 font-bold text-gray-900 text-xs shadow-xs">
                            {sizeLabel}
                          </span>
                          {variant.color && (
                            <span className="text-[11px] text-gray-500">
                              ({variant.color})
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Stock */}
                      <td className="py-3.5 px-4">
                        {madeToOrder ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-100 text-amber-800">
                            Made to Order
                          </span>
                        ) : stockCount <= 0 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-red-100 text-red-700">
                            Out of Stock (0)
                          </span>
                        ) : stockCount <= 5 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-yellow-100 text-yellow-800">
                            Low Stock ({stockCount})
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-100 text-emerald-800">
                            {stockCount} in stock
                          </span>
                        )}
                      </td>

                      {/* Price */}
                      <td className="py-3.5 px-4">
                        <div className="font-medium text-gray-900">
                          {currency}{Number(price).toFixed(2)}
                          {variant.compare_at_price && Number(variant.compare_at_price) > Number(price) && (
                            <span className="ml-1.5 text-gray-400 line-through text-[11px]">
                              {currency}{Number(variant.compare_at_price).toFixed(2)}
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Status */}
                      <td className="py-3.5 px-4">
                        {isAvailable ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700 font-medium">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-gray-400 font-medium">
                            <span className="w-1.5 h-1.5 rounded-full bg-gray-300" />
                            Disabled
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => handleOpenEditModal(variant)}
                            className="p-1.5 text-gray-500 hover:text-gray-900 rounded-md hover:bg-gray-100 transition"
                            title="Edit size option"
                            aria-label={`Edit size ${sizeLabel}`}
                          >
                            <Edit2 className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => setDeletingVariant(variant)}
                            className="p-1.5 text-red-500 hover:text-red-700 rounded-md hover:bg-red-50 transition"
                            title="Delete size option"
                            aria-label={`Delete size ${sizeLabel}`}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* ADD SIZE MODAL */}
      {/* ========================================================================= */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-900">Add Size Option</h3>
                <p className="text-xs text-gray-500">Pick a preset or enter a custom size label</p>
              </div>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 p-1 rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleCreateVariant} className="p-6 space-y-4">
              {/* Presets system tabs */}
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1.5">
                  Sizing System Preset
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-1.5">
                  {(['US Sizing', 'UK Sizing', 'EU Sizing', 'One/Size', 'Custom'] as const).map((sys) => (
                    <button
                      key={sys}
                      type="button"
                      onClick={() => {
                        setSelectedSystem(sys);
                        if (sys === 'One/Size') {
                          setNewSize('One/Size');
                        }
                      }}
                      className={`px-2.5 py-1.5 text-xs font-medium rounded-lg border transition text-center ${
                        selectedSystem === sys
                          ? `${primaryBorder} ${primaryText} bg-gray-50 font-semibold ring-1 ${primaryRing}`
                          : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      {sys}
                    </button>
                  ))}
                </div>
              </div>

              {/* Preset Chips */}
              {selectedSystem !== 'Custom' && (
                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">
                    Select {selectedSystem} Option:
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {PRESET_SIZING_SYSTEMS[selectedSystem].map((sizeOpt) => {
                      const alreadyAdded = existingSizeLabels.has(sizeOpt.toLowerCase());
                      const isSelected = newSize === sizeOpt;

                      return (
                        <button
                          key={sizeOpt}
                          type="button"
                          disabled={alreadyAdded}
                          onClick={() => setNewSize(sizeOpt)}
                          className={`px-3 py-1.5 text-xs rounded-lg border transition font-medium ${
                            alreadyAdded
                              ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed line-through'
                              : isSelected
                              ? `${primaryBg} text-white border-transparent shadow-xs font-semibold`
                              : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'
                          }`}
                        >
                          {sizeOpt}
                        </button>
                      );
                    })}
                  </div>
                  {existingSizeLabels.has(newSize.toLowerCase()) && (
                    <p className="text-[11px] text-red-500 mt-1">This size is already configured for this product.</p>
                  )}
                </div>
              )}

              {/* Custom Size input (or if Custom selected) */}
              <div>
                <label htmlFor="newSizeInput" className="block text-xs font-semibold text-gray-700 mb-1">
                  Size Label *
                </label>
                <input
                  id="newSizeInput"
                  type="text"
                  value={newSize}
                  onChange={(e) => setNewSize(e.target.value)}
                  placeholder="e.g. S, M, XL, 38, One/Size"
                  required
                  className={`w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none ${primaryRing} focus:ring-2`}
                />
              </div>

              {/* Stock and Price row */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="newStockInput" className="block text-xs font-semibold text-gray-700 mb-1">
                    Stock Quantity *
                  </label>
                  <input
                    id="newStockInput"
                    type="number"
                    min="0"
                    step="1"
                    disabled={madeToOrder}
                    value={madeToOrder ? '0' : newStock}
                    onChange={(e) => setNewStock(e.target.value)}
                    required={!madeToOrder}
                    className={`w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none ${primaryRing} focus:ring-2 disabled:bg-gray-100 disabled:text-gray-400`}
                  />
                  {madeToOrder && (
                    <p className="text-[11px] text-gray-400 mt-0.5">Fixed to 0 (Made to order)</p>
                  )}
                </div>

                <div>
                  <label htmlFor="newPriceInput" className="block text-xs font-semibold text-gray-700 mb-1">
                    Price ({currency}) *
                  </label>
                  <input
                    id="newPriceInput"
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={newPrice}
                    onChange={(e) => setNewPrice(e.target.value)}
                    required
                    placeholder="Defaults to base price"
                    className={`w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none ${primaryRing} focus:ring-2`}
                  />
                </div>
              </div>

              {/* Availability */}
              <div className="flex items-center gap-2 pt-1">
                <input
                  id="newIsAvailable"
                  type="checkbox"
                  checked={newIsAvailable}
                  onChange={(e) => setNewIsAvailable(e.target.checked)}
                  className={`rounded text-[#105E53] ${primaryRing}`}
                />
                <label htmlFor="newIsAvailable" className="text-xs text-gray-700 cursor-pointer font-medium">
                  Available for purchase
                </label>
              </div>

              {/* Modal footer */}
              <div className="pt-4 border-t border-gray-100 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsAddModalOpen(false)}
                  disabled={actionLoading}
                  className="px-4 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !newSize.trim()}
                  className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white rounded-lg transition shadow-sm disabled:opacity-50 ${primaryBg}`}
                >
                  {actionLoading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Adding...</span>
                    </>
                  ) : (
                    <span>Add Size Option</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* EDIT SIZE MODAL */}
      {/* ========================================================================= */}
      {editingVariant && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-gray-900">Edit Size Option</h3>
                <p className="text-xs text-gray-500">Update size label, stock count, and price</p>
              </div>
              <button
                type="button"
                onClick={() => setEditingVariant(null)}
                className="text-gray-400 hover:text-gray-600 p-1 rounded-lg"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleUpdateVariant} className="p-6 space-y-4">
              <div>
                <label htmlFor="editSizeInput" className="block text-xs font-semibold text-gray-700 mb-1">
                  Size Label *
                </label>
                <input
                  id="editSizeInput"
                  type="text"
                  value={editSize}
                  onChange={(e) => setEditSize(e.target.value)}
                  placeholder="e.g. S, M, XL, 38, One/Size"
                  required
                  className={`w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none ${primaryRing} focus:ring-2`}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="editStockInput" className="block text-xs font-semibold text-gray-700 mb-1">
                    Stock Quantity *
                  </label>
                  <input
                    id="editStockInput"
                    type="number"
                    min="0"
                    step="1"
                    disabled={madeToOrder}
                    value={madeToOrder ? '0' : editStock}
                    onChange={(e) => setEditStock(e.target.value)}
                    required={!madeToOrder}
                    className={`w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none ${primaryRing} focus:ring-2 disabled:bg-gray-100 disabled:text-gray-400`}
                  />
                  {madeToOrder && (
                    <p className="text-[11px] text-gray-400 mt-0.5">Fixed to 0 (Made to order)</p>
                  )}
                </div>

                <div>
                  <label htmlFor="editPriceInput" className="block text-xs font-semibold text-gray-700 mb-1">
                    Price ({currency}) *
                  </label>
                  <input
                    id="editPriceInput"
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={editPrice}
                    onChange={(e) => setEditPrice(e.target.value)}
                    required
                    className={`w-full rounded-lg border border-gray-300 bg-white px-3.5 py-2 text-xs text-gray-900 focus:outline-none ${primaryRing} focus:ring-2`}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  id="editIsAvailable"
                  type="checkbox"
                  checked={editIsAvailable}
                  onChange={(e) => setEditIsAvailable(e.target.checked)}
                  className={`rounded text-[#105E53] ${primaryRing}`}
                />
                <label htmlFor="editIsAvailable" className="text-xs text-gray-700 cursor-pointer font-medium">
                  Available for purchase
                </label>
              </div>

              <div className="pt-4 border-t border-gray-100 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setEditingVariant(null)}
                  disabled={actionLoading}
                  className="px-4 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading || !editSize.trim()}
                  className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white rounded-lg transition shadow-sm disabled:opacity-50 ${primaryBg}`}
                >
                  {actionLoading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Saving...</span>
                    </>
                  ) : (
                    <span>Save Changes</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* DELETE CONFIRMATION MODAL */}
      {/* ========================================================================= */}
      {deletingVariant && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full overflow-hidden p-6 animate-in fade-in zoom-in-95 duration-150">
            <div className="w-10 h-10 rounded-full bg-red-100 text-red-600 flex items-center justify-center mx-auto mb-3">
              <Trash2 className="h-5 w-5" />
            </div>
            <h3 className="text-sm font-semibold text-gray-900 text-center mb-1">
              Delete Size Option
            </h3>
            <p className="text-xs text-gray-500 text-center mb-5">
              Are you sure you want to remove size <span className="font-semibold text-gray-800">"{deletingVariant.size || 'One/Size'}"</span>? This will permanently delete its stock and inventory configuration.
            </p>

            <div className="flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setDeletingVariant(null)}
                disabled={actionLoading}
                className="flex-1 px-4 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteVariant}
                disabled={actionLoading}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg transition shadow-sm disabled:opacity-50"
              >
                {actionLoading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <span>Delete Size</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
