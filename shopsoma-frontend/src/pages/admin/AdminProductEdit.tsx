import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Loader2 } from 'lucide-react';
import { ROUTES } from '../../config/constants';
import { productService } from '../../services/productService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import type { Product } from '../../types';

export default function AdminProductEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toasts, hideToast, error, success, warning } = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [product, setProduct] = useState<Product | null>(null);

  // Form state - Basic Info
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState('');

  // Form state - Pricing
  const [basePrice, setBasePrice] = useState('');
  const [comparePrice, setComparePrice] = useState('');

  // Form state - Inventory
  const [totalStock, setTotalStock] = useState('');
  const [inventoryQuantity, setInventoryQuantity] = useState('');

  // Form state - Status
  const [status, setStatus] = useState<'draft' | 'active' | 'inactive' | 'archived'>('draft');
  const [moderationStatus, setModerationStatus] = useState<'pending' | 'approved' | 'rejected'>('pending');
  const [isFeatured, setIsFeatured] = useState(false);

  useEffect(() => {
    const fetchProduct = async () => {
      if (!id) {
        error('Product ID is required', 'Error');
        navigate(ROUTES.ADMIN_PRODUCTS);
        return;
      }

      try {
        setLoading(true);
        const data = await productService.getProduct(id);
        setProduct(data);

        // Pre-populate form fields
        setTitle(data.title);
        setDescription(data.description || '');
        setCategoryId(data.category_id || '');
        setBasePrice(data.base_price.toString());
        setComparePrice(data.compare_at_price?.toString() || '');
        setTotalStock(data.total_stock?.toString() || '0');
        setInventoryQuantity(data.inventory_quantity?.toString() || '0');
        setStatus(data.status);
        setModerationStatus(data.moderation_status);
        setIsFeatured(data.is_featured || false);
      } catch (err: any) {
        console.error('Failed to load product', err);
        error(
          err.response?.data?.detail || 'Failed to load product',
          'Error'
        );
        navigate(ROUTES.ADMIN_PRODUCTS);
      } finally {
        setLoading(false);
      }
    };

    fetchProduct();
  }, [id, navigate, error]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!product || !id) return;

    // Validation
    if (!title.trim()) {
      warning('Product title is required');
      return;
    }

    if (!basePrice || parseFloat(basePrice) <= 0) {
      warning('Please enter a valid base price');
      return;
    }

    try {
      setSaving(true);

      const updateData: Partial<Product> = {
        title: title.trim(),
        description: description.trim(),
        category_id: categoryId.trim() || undefined,
        base_price: parseFloat(basePrice),
        compare_at_price: comparePrice ? parseFloat(comparePrice) : undefined,
        total_stock: totalStock ? parseInt(totalStock) : 0,
        inventory_quantity: inventoryQuantity ? parseInt(inventoryQuantity) : 0,
        status,
        moderation_status: moderationStatus,
        is_featured: isFeatured,
      };

      await productService.updateProduct(id, updateData as any);

      success(
        'Product has been updated successfully!',
        'Product Updated'
      );

      // Navigate back to products list after short delay
      setTimeout(() => {
        navigate(ROUTES.ADMIN_PRODUCTS);
      }, 1500);
    } catch (err: any) {
      console.error('Failed to update product', err);
      error(
        err.response?.data?.detail || 'Failed to update product',
        'Update Failed'
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="flex items-center gap-3 text-gray-600">
          <Loader2 className="h-6 w-6 animate-spin" />
          <span>Loading product...</span>
        </div>
      </div>
    );
  }

  if (!product) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <ToastContainer toasts={toasts} onClose={hideToast} />

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-6">
          <button
            onClick={() => navigate(ROUTES.ADMIN_PRODUCTS)}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-4"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Products
          </button>

          <div>
            <h1 className="text-3xl font-semibold text-gray-900">Edit Product</h1>
            <p className="text-sm text-gray-600 mt-1">{product.title}</p>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Basic Information */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Basic Information</h2>
            </div>

            <div className="p-6 space-y-6">
              {/* Product Title */}
              <div>
                <label htmlFor="title" className="block text-sm font-medium text-gray-700 mb-2">
                  Product Title *
                </label>
                <input
                  id="title"
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                  placeholder="Enter product title"
                  required
                />
              </div>

              {/* Description */}
              <div>
                <label htmlFor="description" className="block text-sm font-medium text-gray-700 mb-2">
                  Description
                </label>
                <textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={6}
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                  placeholder="Enter product description"
                />
              </div>

              {/* Category */}
              <div>
                <label htmlFor="categoryId" className="block text-sm font-medium text-gray-700 mb-2">
                  Category ID
                </label>
                <input
                  id="categoryId"
                  type="text"
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                  placeholder={product.category_name ? `Current: ${product.category_name}` : 'Paste category UUID'}
                />
              </div>
            </div>
          </div>

          {/* Pricing */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Pricing</h2>
            </div>

            <div className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label htmlFor="basePrice" className="block text-sm font-medium text-gray-700 mb-2">
                    Base Price ($) *
                  </label>
                  <input
                    id="basePrice"
                    type="number"
                    step="0.01"
                    min="0"
                    value={basePrice}
                    onChange={(e) => setBasePrice(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    placeholder="0.00"
                    required
                  />
                </div>

                <div>
                  <label htmlFor="comparePrice" className="block text-sm font-medium text-gray-700 mb-2">
                    Compare At Price ($)
                  </label>
                  <input
                    id="comparePrice"
                    type="number"
                    step="0.01"
                    min="0"
                    value={comparePrice}
                    onChange={(e) => setComparePrice(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    placeholder="0.00"
                  />
                  <p className="text-xs text-gray-500 mt-1">Original price before discount</p>
                </div>
              </div>
            </div>
          </div>

          {/* Inventory */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Inventory</h2>
            </div>

            <div className="p-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label htmlFor="totalStock" className="block text-sm font-medium text-gray-700 mb-2">
                    Total Stock
                  </label>
                  <input
                    id="totalStock"
                    type="number"
                    min="0"
                    value={totalStock}
                    onChange={(e) => setTotalStock(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    placeholder="0"
                  />
                </div>

                <div>
                  <label htmlFor="inventoryQuantity" className="block text-sm font-medium text-gray-700 mb-2">
                    Inventory Quantity
                  </label>
                  <input
                    id="inventoryQuantity"
                    type="number"
                    min="0"
                    value={inventoryQuantity}
                    onChange={(e) => setInventoryQuantity(e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                    placeholder="0"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Product Status & Settings */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">Status & Settings</h2>
            </div>

            <div className="p-6 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Product Status */}
                <div>
                  <label htmlFor="status" className="block text-sm font-medium text-gray-700 mb-2">
                    Product Status
                  </label>
                  <select
                    id="status"
                    value={status}
                    onChange={(e) => setStatus(e.target.value as any)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                  >
                    <option value="draft">Draft</option>
                    <option value="active">Active</option>
                    <option value="inactive">Inactive</option>
                    <option value="archived">Archived</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">Product visibility status</p>
                </div>

                {/* Moderation Status */}
                <div>
                  <label htmlFor="moderationStatus" className="block text-sm font-medium text-gray-700 mb-2">
                    Moderation Status
                  </label>
                  <select
                    id="moderationStatus"
                    value={moderationStatus}
                    onChange={(e) => setModerationStatus(e.target.value as any)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20"
                  >
                    <option value="pending">Pending Review</option>
                    <option value="approved">Approved</option>
                    <option value="rejected">Rejected</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">Admin moderation status</p>
                </div>
              </div>

              {/* Featured Product */}
              <div className="flex items-start">
                <div className="flex items-center h-5">
                  <input
                    id="isFeatured"
                    type="checkbox"
                    checked={isFeatured}
                    onChange={(e) => setIsFeatured(e.target.checked)}
                    className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                  />
                </div>
                <div className="ml-3">
                  <label htmlFor="isFeatured" className="text-sm font-medium text-gray-700">
                    Featured Product
                  </label>
                  <p className="text-xs text-gray-500">Display this product in featured sections</p>
                </div>
              </div>
            </div>
          </div>

          {/* Product Images Info */}
          {product.images && product.images.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">Product Images</h2>
              </div>

              <div className="p-6">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {product.images.map((img, idx) => {
                    const imageUrl = img.image_url || img.thumbnail_url || '/images/placeholder-product.svg';
                    return (
                    <div key={idx} className="relative aspect-square rounded-lg overflow-hidden border border-gray-200">
                      <img
                        src={imageUrl}
                        alt={`Product ${idx + 1}`}
                        className="w-full h-full object-cover"
                      />
                      {img.is_primary && (
                        <div className="absolute top-2 left-2 bg-blue-600 text-white text-xs px-2 py-1 rounded">
                          Primary
                        </div>
                      )}
                    </div>
                    );
                  })}
                </div>
                <p className="text-xs text-gray-500 mt-3">
                  Note: Image management (upload/delete) requires using the vendor product management interface or contacting the vendor directly.
                </p>
              </div>
            </div>
          )}

          {/* Moderation Notes */}
          {product.moderation_notes && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
              <div className="px-6 py-4 border-b border-gray-200">
                <h2 className="text-lg font-semibold text-gray-900">Moderation Notes</h2>
              </div>

              <div className="p-6">
                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{product.moderation_notes}</p>
                </div>
              </div>
            </div>
          )}

          {/* Form Footer */}
          <div className="flex items-center justify-between bg-white rounded-xl border border-gray-200 shadow-sm px-6 py-4">
            <p className="text-sm text-gray-500">
              Product ID: {product.id}
            </p>

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => navigate(ROUTES.ADMIN_PRODUCTS)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving Changes...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save Changes
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
