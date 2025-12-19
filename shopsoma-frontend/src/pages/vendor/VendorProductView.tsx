import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit2, Loader2, Shirt, Package, DollarSign, Tag, Calendar, Eye, Trash2, Copy } from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import DeleteProductModal from '../../components/vendor/DeleteProductModal';
import { ROUTES } from '../../config/constants';
import { productService } from '../../services/productService';
import type { Product } from '../../types';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';

function formatPrice(price: number) {
  return `$${price.toLocaleString()}`;
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const yy = String(d.getFullYear());
  return `${mm}/${dd}/${yy}`;
}

export default function VendorProductView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toasts, hideToast, error, success } = useToast();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

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

  const getStatusColor = (status?: string) => {
    switch (status?.toLowerCase()) {
      case 'approved':
        return 'text-[#19984B] bg-[#E8F7EF]';
      case 'pending':
        return 'text-yellow-700 bg-yellow-50';
      case 'rejected':
        return 'text-red-700 bg-red-50';
      case 'draft':
        return 'text-gray-700 bg-gray-100';
      default:
        return 'text-gray-700 bg-gray-100';
    }
  };

  const handleDeleteConfirm = async () => {
    if (!product) return;

    try {
      setIsDeleting(true);
      await productService.deleteProduct(product.id);

      success('Product deleted successfully', 'Deleted');
      setDeleteModalOpen(false);

      // Navigate back to products list
      setTimeout(() => {
        navigate(ROUTES.VENDOR_PRODUCTS);
      }, 1000);
    } catch (err: any) {
      console.error('Failed to delete product', err);
      error(
        err.response?.data?.detail || 'Failed to delete product',
        'Delete Failed'
      );
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDuplicate = async () => {
    if (!product) return;

    try {
      const duplicated = await productService.duplicateProduct(product.id);
      success(
        'Product duplicated successfully. Redirecting to edit...',
        'Product Duplicated'
      );

      // Navigate to edit the duplicated product
      setTimeout(() => {
        navigate(`${ROUTES.VENDOR_PRODUCTS}/${duplicated.id}/edit`);
      }, 1500);
    } catch (err: any) {
      console.error('Failed to duplicate product', err);
      error(
        err.response?.data?.detail || 'Failed to duplicate product',
        'Duplication Failed'
      );
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)]">
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
    <div className="min-h-screen bg-[var(--color-page-bg)]">
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <DeleteProductModal
        product={product}
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={handleDeleteConfirm}
        isDeleting={isDeleting}
      />
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
                <h1 className="text-3xl font-semibold text-gray-900">{product.title}</h1>
                <p className="text-sm text-gray-600 mt-1">View product details</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/${product.id}/edit`)}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#105E53] text-white px-5 py-2.5 text-sm font-medium hover:bg-[#0c4c45] transition"
            >
              <Edit2 className="h-4 w-4" />
              Edit Product
            </button>
          </div>

          {/* Content */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Main Content - Left Side */}
            <div className="lg:col-span-2 space-y-6">
              {/* Product Image */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900">Product Images</h2>
                </div>
                <div className="p-6">
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                    {product.images && product.images.length > 0 ? (
                      product.images.map((img, index) => (
                        <div key={index} className="aspect-square rounded-lg overflow-hidden border border-gray-200">
                          <img
                            src={img.thumbnail_url || img.image_url}
                            alt={img.alt_text || `Product image ${index + 1}`}
                            className="w-full h-full object-cover"
                          />
                        </div>
                      ))
                    ) : (
                      <div className="aspect-square rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-center text-gray-400">
                        <Shirt className="h-16 w-16" />
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Product Details */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900">Product Details</h2>
                </div>
                <div className="p-6 space-y-6">
                  {/* Description */}
                  <div>
                    <h3 className="text-sm font-semibold text-gray-700 mb-2">Description</h3>
                    <p className="text-sm text-gray-600 whitespace-pre-wrap">
                      {product.description || 'No description provided'}
                    </p>
                  </div>

                  {/* Fabric & Materials */}
                  {product.fabric_composition && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 mb-2">Fabric & Materials</h3>
                      <p className="text-sm text-gray-600 whitespace-pre-wrap">
                        {product.fabric_composition}
                      </p>
                    </div>
                  )}

                  {/* Care Instructions */}
                  {product.care_instructions && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 mb-2">Care Instructions</h3>
                      <p className="text-sm text-gray-600 whitespace-pre-wrap">
                        {product.care_instructions}
                      </p>
                    </div>
                  )}

                  {/* Made to Order */}
                  {product.made_to_order && (
                    <div>
                      <span className="inline-flex items-center gap-2 px-3 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full">
                        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                          <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 11H9v-2h2v2zm0-4H9V5h2v4z"/>
                        </svg>
                        MADE TO ORDER
                        {product.made_to_order_timeline && ` • ${product.made_to_order_timeline}`}
                      </span>
                    </div>
                  )}

                  {/* Size Guide */}
                  {product.size_guide && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 mb-2">Size Guide</h3>
                      <div className="text-sm text-gray-600">
                        {product.size_guide.title && <p className="font-medium">{product.size_guide.title}</p>}
                        {product.size_guide.subtitle && <p className="text-xs text-gray-500 mt-1">{product.size_guide.subtitle}</p>}
                        {product.size_guide.notes && <p className="mt-2">{product.size_guide.notes}</p>}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Variations */}
              {product.variations && product.variations.length > 0 && (
                <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                  <div className="px-6 py-4 border-b border-gray-200">
                    <h2 className="text-lg font-semibold text-gray-900">Product Variations</h2>
                  </div>
                  <div className="p-6">
                    <div className="space-y-4">
                      {product.variations.map((variation, index) => (
                        <div key={variation.id || index} className="border border-gray-200 rounded-lg p-4">
                          <div className="flex items-start justify-between mb-3">
                            <div>
                              <h4 className="font-medium text-gray-900">{variation.title || `Variation ${index + 1}`}</h4>
                              {variation.type && (
                                <p className="text-sm text-gray-600 mt-1">Type: {variation.type}</p>
                              )}
                            </div>
                            {variation.price && (
                              <div className="text-right">
                                <div className="text-lg font-semibold text-gray-900">
                                  {formatPrice(variation.price)}
                                </div>
                                {variation.sale_price && variation.sale_price < variation.price && (
                                  <div className="text-sm text-gray-500 line-through">
                                    {formatPrice(variation.sale_price)}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>

                          {/* Size Stocks */}
                          {variation.size_stocks && variation.size_stocks.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {variation.size_stocks.map((sizeStock, sizeIdx) => (
                                <span key={sizeIdx} className="inline-flex items-center gap-2 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-xs font-medium">
                                  {sizeStock.size}: {sizeStock.stock} in stock
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Sidebar - Right Side */}
            <div className="space-y-6">
              {/* Status & Info */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900">Product Info</h2>
                </div>
                <div className="p-6 space-y-4">
                  {/* Status */}
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-700">Status</span>
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getStatusColor(product.moderation_status)}`}>
                      {product.moderation_status || 'Draft'}
                    </span>
                  </div>

                  {/* Rejection Reason - Only show if product is rejected */}
                  {product.moderation_status === 'rejected' && product.moderation_notes && (
                    <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                      <div className="flex items-start gap-2">
                        <div className="flex-shrink-0 mt-0.5">
                          <svg className="h-5 w-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                          </svg>
                        </div>
                        <div className="flex-1">
                          <h4 className="text-sm font-semibold text-red-900 mb-1">Product Rejected</h4>
                          <p className="text-sm text-red-800 whitespace-pre-wrap">{product.moderation_notes}</p>
                          <p className="text-xs text-red-700 mt-2">
                            Please address the issues above and resubmit your product for review.
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Price */}
                  <div className="flex items-center justify-between pt-4 border-t border-gray-200">
                    <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                      <DollarSign className="h-4 w-4" />
                      Base Price
                    </span>
                    <span className="text-lg font-semibold text-gray-900">
                      {formatPrice(product.base_price)}
                    </span>
                  </div>

                  {/* Compare Price */}
                  {product.compare_at_price && product.compare_at_price > product.base_price && (
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-gray-700">Compare At</span>
                      <span className="text-sm text-gray-500 line-through">
                        {formatPrice(product.compare_at_price)}
                      </span>
                    </div>
                  )}

                  {/* Stock */}
                  <div className="flex items-center justify-between pt-4 border-t border-gray-200">
                    <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                      <Package className="h-4 w-4" />
                      Total Stock
                    </span>
                    <span className="text-sm font-semibold text-gray-900">
                      {product.total_stock ?? product.inventory_quantity ?? 0}
                    </span>
                  </div>

                  {/* Category */}
                  {product.category_name && (
                    <div className="flex items-center justify-between pt-4 border-t border-gray-200">
                      <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                        <Tag className="h-4 w-4" />
                        Category
                      </span>
                      <span className="text-sm text-gray-900">{product.category_name}</span>
                    </div>
                  )}

                  {/* Created Date */}
                  <div className="flex items-center justify-between pt-4 border-t border-gray-200">
                    <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                      <Calendar className="h-4 w-4" />
                      Created
                    </span>
                    <span className="text-sm text-gray-900">{formatDate(product.created_at)}</span>
                  </div>

                  {/* Views */}
                  {product.views_count !== undefined && (
                    <div className="flex items-center justify-between pt-4 border-t border-gray-200">
                      <span className="text-sm font-medium text-gray-700 flex items-center gap-2">
                        <Eye className="h-4 w-4" />
                        Views
                      </span>
                      <span className="text-sm text-gray-900">{product.views_count}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Quick Actions */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900">Quick Actions</h2>
                </div>
                <div className="p-6 space-y-3">
                  <button
                    type="button"
                    onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/${product.id}/edit`)}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-[#105E53] text-white px-4 py-2.5 text-sm font-medium hover:bg-[#0c4c45] transition"
                  >
                    <Edit2 className="h-4 w-4" />
                    Edit Product
                  </button>
                  <button
                    type="button"
                    onClick={handleDuplicate}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white text-gray-700 px-4 py-2.5 text-sm font-medium hover:bg-gray-50 transition"
                  >
                    <Copy className="h-4 w-4" />
                    Duplicate Product
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteModalOpen(true)}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg border border-red-300 bg-white text-red-700 px-4 py-2.5 text-sm font-medium hover:bg-red-50 transition"
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete Product
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(ROUTES.VENDOR_PRODUCTS)}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white text-gray-700 px-4 py-2.5 text-sm font-medium hover:bg-gray-50 transition"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    Back to Products
                  </button>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
