import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Save, Loader2 } from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { ROUTES } from '../../config/constants';
import { productService } from '../../services/productService';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import type { Product } from '../../types';

export default function VendorProductEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toasts, hideToast, error, success, warning } = useToast();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [product, setProduct] = useState<Product | null>(null);

  // Form state
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [basePrice, setBasePrice] = useState('');
  const [comparePrice, setComparePrice] = useState('');
  const [stock, setStock] = useState('');
  const [status, setStatus] = useState<'draft' | 'active' | 'inactive' | 'archived'>('draft');

  useEffect(() => {
    const fetchProduct = async () => {
      if (!id) {
        error('Product ID is required', 'Error');
        navigate(ROUTES.VENDOR_PRODUCTS);
        return;
      }

      try {
        setLoading(true);
        const data = await productService.getProduct(id);
        setProduct(data);

        // Pre-populate form fields
        setTitle(data.title);
        setDescription(data.description || '');
        setBasePrice(data.base_price.toString());
        setComparePrice(data.compare_at_price?.toString() || '');
        setStock(data.total_stock?.toString() || '0');
        setStatus(data.status);
      } catch (err: any) {
        console.error('Failed to load product', err);
        error(
          err.response?.data?.detail || 'Failed to load product',
          'Error'
        );
        navigate(ROUTES.VENDOR_PRODUCTS);
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
        base_price: parseFloat(basePrice),
        compare_at_price: comparePrice ? parseFloat(comparePrice) : undefined,
        total_stock: stock ? parseInt(stock) : 0,
        status,
      };

      await productService.updateProduct(id, updateData as any);

      success(
        'Your product has been updated successfully!',
        'Product Updated'
      );

      // Navigate back to products list after short delay
      setTimeout(() => {
        navigate(ROUTES.VENDOR_PRODUCTS);
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
      <div className="min-h-screen bg-[#F9FAFB]">
        <div className="flex">
          <VendorSidebar activePrimary="products" />
          <main className="flex-1 p-8">
            <div className="flex items-center justify-center py-20 text-gray-600 gap-3">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="text-sm">Loading product...</span>
            </div>
          </main>
        </div>
      </div>
    );
  }

  if (!product) {
    return null;
  }

  return (
    <div className="min-h-screen bg-[#F9FAFB]">
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <div className="flex">
        <VendorSidebar activePrimary="products" />

        <main className="flex-1 p-8">
          {/* Header */}
          <div className="mb-6 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                className="p-2 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 transition"
                title="Back to products"
              >
                <ArrowLeft className="h-5 w-5 text-gray-600" />
              </button>
              <div>
                <h1 className="text-3xl font-semibold text-gray-900">Edit Product</h1>
                <p className="text-sm text-gray-600 mt-1">{product.title}</p>
              </div>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="max-w-4xl">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
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
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
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
                    className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    placeholder="Enter product description"
                  />
                </div>

                {/* Pricing Row */}
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
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="0.00"
                      required
                    />
                  </div>

                  <div>
                    <label htmlFor="comparePrice" className="block text-sm font-medium text-gray-700 mb-2">
                      Compare at Price ($)
                    </label>
                    <input
                      id="comparePrice"
                      type="number"
                      step="0.01"
                      min="0"
                      value={comparePrice}
                      onChange={(e) => setComparePrice(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="0.00"
                    />
                  </div>
                </div>

                {/* Stock and Status Row */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label htmlFor="stock" className="block text-sm font-medium text-gray-700 mb-2">
                      Total Stock
                    </label>
                    <input
                      id="stock"
                      type="number"
                      min="0"
                      value={stock}
                      onChange={(e) => setStock(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                      placeholder="0"
                    />
                  </div>

                  <div>
                    <label htmlFor="status" className="block text-sm font-medium text-gray-700 mb-2">
                      Status
                    </label>
                    <select
                      id="status"
                      value={status}
                      onChange={(e) => setStatus(e.target.value as any)}
                      className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                    >
                      <option value="draft">Draft</option>
                      <option value="active">Active</option>
                      <option value="inactive">Inactive</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>
                </div>

                {/* Info Note */}
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <p className="text-sm text-blue-800">
                    <strong>Note:</strong> This is a simplified editing interface. For advanced edits (images, variations, categories),
                    please create a new product or contact support.
                  </p>
                </div>
              </div>
            </div>

            {/* Action Buttons */}
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                disabled={saving}
                className="px-5 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 text-sm font-medium text-white bg-[#105E53] rounded-lg hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save Changes
                  </>
                )}
              </button>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
