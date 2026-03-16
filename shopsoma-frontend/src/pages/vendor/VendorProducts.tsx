import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import DeleteProductModal from '../../components/vendor/DeleteProductModal';
import BulkUploadModal from '../../components/vendor/BulkUploadModal';
import ToastContainer from '../../components/ui/ToastContainer';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useVendor } from '../../context/VendorContext';
import { useToast } from '../../hooks/useToast';
import { productService } from '../../services/productService';
import type { Product } from '../../types';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion } from '../../utils/pricing';
import { Eye, PencilLine, Shirt, Search, Loader2, ArrowUpDown, Filter, Trash2, Copy, Upload } from 'lucide-react';

type GroupBy = 'all' | 'collections';

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const yy = String(d.getFullYear());
  return `${mm}/${dd}/${yy}`;
}

export default function VendorProducts() {
  const navigate = useNavigate();
  const { vendorProfile, isLoading: vendorLoading } = useVendor();
  const { toasts, hideToast, success, error } = useToast();
  const { currentCurrency, setCurrency, exchangeRates, fetchExchangeRate } = useCurrencyStore();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [groupBy, setGroupBy] = useState<GroupBy>('all');
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [productToDelete, setProductToDelete] = useState<Product | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [bulkUploadOpen, setBulkUploadOpen] = useState(false);

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  const loadProducts = useCallback(async () => {
    if (!vendorProfile?.id) {
      console.log('Vendor profile not loaded yet, skipping product fetch');
      return;
    }
    try {
      setLoading(true);
      console.log('Fetching products for vendor:', vendorProfile.id);
      const res = await productService.getVendorProducts(vendorProfile.id, {
        page_size: 100, // Backend max is 100
      });
      console.log('Products fetched:', res);
      console.log('Products array:', res.products);
      console.log('Products count:', res.products?.length || 0);
      setProducts(res.products || []);
    } catch (err: any) {
      console.error('Failed to load vendor products', err);
      console.error('Error response:', err.response);
      console.error('Error data:', err.response?.data);
      console.error('Error detail:', err.response?.data?.detail);

      // Format validation error for display
      if (err.response?.data?.detail && Array.isArray(err.response.data.detail)) {
        console.error('Validation errors:');
        err.response.data.detail.forEach((error: any, index: number) => {
          console.error(`  ${index + 1}. ${error.loc?.join('.')}: ${error.msg}`);
        });
      }
    } finally {
      setLoading(false);
    }
  }, [vendorProfile?.id]);

  useEffect(() => {
    loadProducts();
  }, [loadProducts]);

  const filteredProducts = useMemo(() => {
    let list = [...products];
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter((p) => p.title.toLowerCase().includes(q));
    }
    return list;
  }, [products, search]);

  // Group products by collection
  const productsByCollection = useMemo(() => {
    const grouped: Record<string, Product[]> = {};
    filteredProducts.forEach((product) => {
      const collectionName = product.collection_name || 'Uncategorized';
      if (!grouped[collectionName]) {
        grouped[collectionName] = [];
      }
      grouped[collectionName].push(product);
    });
    return grouped;
  }, [filteredProducts]);

  const allCount = products.length;
  const collectionsCount = Object.keys(productsByCollection).length;

  const renderStatusBadge = (p: Product) => {
    const qty = p.total_stock ?? p.inventory_quantity ?? 0;
    const lowStock = (p.total_stock ?? p.inventory_quantity ?? 0) < 5;

    // Priority: Show rejection first, then low stock, then approval status
    let label: string;
    let color: string;

    if (p.moderation_status === 'rejected') {
      label = 'Rejected';
      color = 'text-red-700 bg-red-100';
    } else if (p.made_to_order) {
      label = 'Made to Order';
      color = 'text-sky-700 bg-sky-50';
    } else if (lowStock) {
      label = 'Low Stock';
      color = 'text-[#19984B] bg-[#E8F7EF]';
    } else if (qty > 0) {
      label = 'Ready to Ship';
      color = 'text-[#19984B] bg-[#E8F7EF]';
    } else if (p.moderation_status === 'approved') {
      label = 'Approved';
      color = 'text-[#19984B] bg-[#E8F7EF]';
    } else {
      label = 'Pending';
      color = 'text-amber-700 bg-amber-100';
    }

    return (
      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${color}`}>
        {label}
      </span>
    );
  };

  const getStockLabel = (p: Product) => {
    const qty = p.total_stock ?? p.inventory_quantity ?? 0;
    if (p.made_to_order) {
      return p.made_to_order_timeline
        ? `Made to Order • ${p.made_to_order_timeline}`
        : 'Made to Order';
    }
    if (qty <= 0) {
      return 'Out of Stock';
    }
    if (qty < 5) {
      return `Low Stock • ${qty} left`;
    }
    return `Ready to Ship • ${qty} in stock`;
  };

  const getImage = (p: Product) => {
    return p.images?.[0]?.thumbnail_url || p.images?.[0]?.image_url || '';
  };

  const handleDeleteClick = (product: Product) => {
    setProductToDelete(product);
    setDeleteModalOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!productToDelete) return;

    try {
      setIsDeleting(true);
      await productService.deleteProduct(productToDelete.id);

      // Remove from local state
      setProducts(prev => prev.filter(p => p.id !== productToDelete.id));

      success('Product deleted successfully', 'Deleted');
      setDeleteModalOpen(false);
      setProductToDelete(null);
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

  const handleDuplicate = async (product: Product) => {
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

  const formatDisplayPrice = (amount: number, currency?: Product['currency']) => {
    return formatPriceWithConversion(
      amount,
      currency || 'NGN',
      currentCurrency,
      exchangeRates
    );
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)]">
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <DeleteProductModal
        product={productToDelete!}
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={handleDeleteConfirm}
        isDeleting={isDeleting}
      />
      <BulkUploadModal
        isOpen={bulkUploadOpen}
        onClose={() => setBulkUploadOpen(false)}
        onUploaded={(count) => {
          success(`Uploaded ${count} product${count === 1 ? '' : 's'} successfully.`);
          loadProducts();
        }}
      />
      <div className="flex">
        <VendorSidebar activePrimary="products" />

        <main className="flex-1 p-8">
          {/* Header */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <h1 className="text-3xl font-semibold text-gray-900">Product Management</h1>
              <div className="flex items-center gap-3">
                <CurrencySwitcher value={currentCurrency} onChange={setCurrency} />
                <div className="relative">
                  <Search className="h-5 w-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Search"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-64 rounded-lg border border-gray-300 bg-white pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20"
                  />
                </div>
                <button
                  type="button"
                  className="p-2.5 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 transition"
                  title="Filter"
                >
                  <Filter className="h-5 w-5 text-gray-600" />
                </button>
                <button
                  type="button"
                  className="p-2.5 rounded-lg border border-gray-300 bg-white hover:bg-gray-50 transition"
                  title="Sort"
                >
                  <ArrowUpDown className="h-5 w-5 text-gray-600" />
                </button>
                <button
                  type="button"
                  onClick={() => setBulkUploadOpen(true)}
                  className="inline-flex items-center justify-center rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition whitespace-nowrap gap-2"
                >
                  <Upload className="h-4 w-4" />
                  Bulk Upload
                </button>
                <button
                  type="button"
                  onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/new`)}
                  className="inline-flex items-center justify-center rounded-lg bg-[#105E53] text-white px-5 py-2.5 text-sm font-medium hover:bg-[#0c4c45] transition whitespace-nowrap"
                >
                  + Add New Product
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-600">Group by:</span>
              <button
                type="button"
                onClick={() => setGroupBy('all')}
                className={`px-3 py-1.5 rounded-md transition ${
                  groupBy === 'all'
                    ? 'text-gray-900 font-medium bg-white shadow-sm'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                All ({allCount})
              </button>
              <button
                type="button"
                onClick={() => setGroupBy('collections')}
                className={`px-3 py-1.5 rounded-md transition ${
                  groupBy === 'collections'
                    ? 'text-gray-900 font-medium bg-white shadow-sm'
                    : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                Collections ({collectionsCount})
              </button>
            </div>
          </div>

          {/* Products Display */}
          {loading || vendorLoading ? (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="flex items-center justify-center py-20 text-gray-600 gap-3">
                <Loader2 className="h-6 w-6 animate-spin" />
                <span className="text-sm">Loading products...</span>
              </div>
            </div>
          ) : filteredProducts.length === 0 ? (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-20 text-center">
                <Shirt className="h-16 w-16 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-600 text-sm">No products found.</p>
              </div>
            </div>
          ) : groupBy === 'collections' ? (
            // Collections View
            <div className="space-y-6">
              {Object.entries(productsByCollection).map(([collectionName, collectionProducts]) => (
                <div key={collectionName} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                  {/* Collection Header */}
                  <div className="bg-gray-50 px-6 py-4 border-b border-gray-200">
                    <h3 className="text-base font-semibold text-gray-900 text-center">
                      {collectionName} ({collectionProducts.length})
                    </h3>
                  </div>

                  {/* Collection Products Table */}
                  <table className="w-full">
                    <thead className="bg-gray-50 border-b border-gray-200">
                      <tr>
                        <th className="px-6 py-4 text-left">
                          <div className="flex items-center gap-2">
                            <Shirt className="h-4 w-4 text-gray-400" />
                          </div>
                        </th>
                        <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Product Name
                        </th>
                        <th className="px-6 py-4 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Price
                        </th>
                        <th className="px-6 py-4 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Last Edited
                        </th>
                        <th className="px-6 py-4 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Fulfillment
                        </th>
                        <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200">
                      {collectionProducts.map((product) => {
                        const stockLabel = getStockLabel(product);
                        const img = getImage(product);
                        return (
                          <tr key={product.id} className="hover:bg-gray-50 transition">
                            <td className="px-6 py-4">
                              {img ? (
                                <img
                                  src={img}
                                  alt={product.title}
                                  className="h-14 w-14 rounded-lg object-cover border border-gray-200"
                                />
                              ) : (
                                <div className="h-14 w-14 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-center text-gray-400">
                                  <Shirt className="h-7 w-7" />
                                </div>
                              )}
                            </td>
                            <td className="px-6 py-4">
                              <div className="text-sm font-medium text-gray-900">{product.title}</div>
                            </td>
                            <td className="px-6 py-4 text-center">
                              {renderStatusBadge(product)}
                            </td>
                            <td className="px-6 py-4 text-center">
                              <div className="text-sm font-medium text-gray-900">
                                {formatDisplayPrice(product.base_price, product.currency)}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-center">
                              <div className="text-sm text-gray-600">{formatDate(product.created_at)}</div>
                            </td>
                            <td className="px-6 py-4 text-center">
                              <div className={`text-sm font-medium ${product.made_to_order ? 'text-sky-700' : 'text-[#19984B]'}`}>{stockLabel}</div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center justify-end gap-1">
                                <button
                                  type="button"
                                  className="p-2 hover:bg-gray-100 rounded-lg transition text-gray-600 hover:text-[#105E53]"
                                  aria-label="View"
                                  title="View product"
                                  onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/${product.id}/view`)}
                                >
                                  <Eye className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  className="p-2 hover:bg-gray-100 rounded-lg transition text-gray-600 hover:text-[#105E53]"
                                  aria-label="Edit"
                                  title="Edit product"
                                  onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/${product.id}/edit`)}
                                >
                                  <PencilLine className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  className="p-2 hover:bg-gray-100 rounded-lg transition text-gray-600 hover:text-blue-600"
                                  aria-label="Duplicate"
                                  title="Duplicate product"
                                  onClick={() => handleDuplicate(product)}
                                >
                                  <Copy className="h-4 w-4" />
                                </button>
                                <button
                                  type="button"
                                  className="p-2 hover:bg-red-50 rounded-lg transition text-gray-600 hover:text-red-600"
                                  aria-label="Delete"
                                  title="Delete product"
                                  onClick={() => handleDeleteClick(product)}
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
              ))}
            </div>
          ) : (
            // All Products View
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-6 py-4 text-left">
                      <div className="flex items-center gap-2">
                        <Shirt className="h-4 w-4 text-gray-400" />
                      </div>
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Product Name
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Approval Status
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Price
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Fulfillment
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Date Created
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filteredProducts.map((product) => {
                    const stockLabel = getStockLabel(product);
                    const img = getImage(product);
                    return (
                      <tr key={product.id} className="hover:bg-gray-50 transition">
                        <td className="px-6 py-4">
                          {img ? (
                            <img
                              src={img}
                              alt={product.title}
                              className="h-14 w-14 rounded-lg object-cover border border-gray-200"
                            />
                          ) : (
                            <div className="h-14 w-14 rounded-lg border border-gray-200 bg-gray-50 flex items-center justify-center text-gray-400">
                              <Shirt className="h-7 w-7" />
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="text-sm font-medium text-gray-900">{product.title}</div>
                        </td>
                        <td className="px-6 py-4">
                          {renderStatusBadge(product)}
                        </td>
                        <td className="px-6 py-4">
                          <div className="text-sm font-medium text-gray-900">
                            {formatDisplayPrice(product.base_price, product.currency)}
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <div className={`text-sm font-medium ${product.made_to_order ? 'text-sky-700' : 'text-[#19984B]'}`}>{stockLabel}</div>
                        </td>
                        <td className="px-6 py-4">
                          <div className="text-sm text-gray-600">{formatDate(product.created_at)}</div>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              type="button"
                              className="p-2 hover:bg-gray-100 rounded-lg transition text-gray-600 hover:text-[#105E53]"
                              aria-label="View"
                              title="View product"
                              onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/${product.id}/view`)}
                            >
                              <Eye className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              className="p-2 hover:bg-gray-100 rounded-lg transition text-gray-600 hover:text-[#105E53]"
                              aria-label="Edit"
                              title="Edit product"
                              onClick={() => navigate(`${ROUTES.VENDOR_PRODUCTS}/${product.id}/edit`)}
                            >
                              <PencilLine className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              className="p-2 hover:bg-gray-100 rounded-lg transition text-gray-600 hover:text-blue-600"
                              aria-label="Duplicate"
                              title="Duplicate product"
                              onClick={() => handleDuplicate(product)}
                            >
                              <Copy className="h-4 w-4" />
                            </button>
                            <button
                              type="button"
                              className="p-2 hover:bg-red-50 rounded-lg transition text-gray-600 hover:text-red-600"
                              aria-label="Delete"
                              title="Delete product"
                              onClick={() => handleDeleteClick(product)}
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
        </main>
      </div>
    </div>
  );
}
