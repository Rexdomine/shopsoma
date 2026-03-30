import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, CheckCircle, XCircle, Eye, Package, AlertCircle, Edit2, Trash2 } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { adminService } from '../../services/adminService';
import { ROUTES } from '../../config/constants';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion } from '../../utils/pricing';

interface Product {
  id: string;
  title: string;
  description: string;
  sku: string;
  base_price: number;
  compare_at_price: number | null;
  currency?: 'NGN' | 'USD';
  inventory_quantity: number;
  total_stock: number;
  made_to_order: boolean;
  made_to_order_timeline?: string | null;
  status: 'draft' | 'active' | 'inactive' | 'archived';
  is_featured: boolean;
  moderation_status: 'pending' | 'approved' | 'rejected';
  moderated_at: string | null;
  moderation_notes: string | null;
  views_count: number;
  orders_count: number;
  vendor: {
    id: string;
    business_name: string;
  };
  created_at: string;
  updated_at: string;
}

export default function AdminProducts() {
  const navigate = useNavigate();
  const { currentCurrency, setCurrency, exchangeRates, fetchExchangeRate } = useCurrencyStore();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [moderationFilter, setModerationFilter] = useState<string>('pending');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [featureLoadingId, setFeatureLoadingId] = useState<string | null>(null);
  const [rejectModal, setRejectModal] = useState<Product | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectionNotes, setRejectionNotes] = useState('');
  const [approvalModal, setApprovalModal] = useState<Product | null>(null);
  const [approvalNotes, setApprovalNotes] = useState('');
  const [deleteModal, setDeleteModal] = useState<Product | null>(null);

  const pageSize = 20;

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  useEffect(() => {
    loadProducts();
  }, [page, moderationFilter, statusFilter, search]);

  const loadProducts = async () => {
    try {
      setLoading(true);

      const filters: any = {
        page,
        page_size: pageSize,
        search: search || undefined,
      };

      if (moderationFilter !== 'all') filters.moderation_status = moderationFilter;
      if (statusFilter !== 'all') filters.status = statusFilter;

      const response = await adminService.listProducts(filters);
      setProducts(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err: any) {
      showMessage('error', err.message || 'Failed to load products');
    } finally {
      setLoading(false);
    }
  };

  const handleApproveProduct = async () => {
    if (!approvalModal) return;

    try {
      setActionLoading(approvalModal.id);
      await adminService.approveProduct(approvalModal.id, approvalNotes || undefined);
      showMessage('success', `Product "${approvalModal.title}" approved successfully. Vendor has been notified.`);
      setApprovalModal(null);
      setApprovalNotes('');
      loadProducts();
    } catch (err: any) {
      showMessage('error', err?.response?.data?.detail || err.message || 'Failed to approve product');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRejectProduct = async () => {
    if (!rejectModal || !rejectionReason.trim()) {
      showMessage('error', 'Rejection reason is required');
      return;
    }

    if (rejectionReason.length < 10) {
      showMessage('error', 'Rejection reason must be at least 10 characters');
      return;
    }

    try {
      setActionLoading(rejectModal.id);
      await adminService.rejectProduct(rejectModal.id, rejectionReason, rejectionNotes || undefined);
      showMessage('success', `Product "${rejectModal.title}" rejected. Vendor has been notified.`);
      setRejectModal(null);
      setRejectionReason('');
      setRejectionNotes('');
      loadProducts();
    } catch (err: any) {
      showMessage('error', err?.response?.data?.detail || err.message || 'Failed to reject product');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteProduct = async () => {
    if (!deleteModal) return;

    try {
      setActionLoading(deleteModal.id);
      await adminService.deleteProduct(deleteModal.id);
      showMessage('success', `Product "${deleteModal.title}" has been deleted successfully.`);
      setDeleteModal(null);
      loadProducts();
    } catch (err: any) {
      showMessage('error', err?.response?.data?.detail || err.message || 'Failed to delete product');
    } finally {
      setActionLoading(null);
    }
  };

  const handleViewProduct = (productId: string) => {
    navigate(`${ROUTES.ADMIN_PRODUCTS}/${productId}`);
  };

  const handleEditProduct = (productId: string) => {
    navigate(`${ROUTES.ADMIN_PRODUCTS}/${productId}/edit`);
  };

  const handleFeatureToggle = async (product: Product) => {
    const nextValue = !product.is_featured;
    try {
      setFeatureLoadingId(product.id);
      await adminService.updateProductFeatured(product.id, nextValue);
      setProducts((prev) =>
        prev.map((item) =>
          item.id === product.id ? { ...item, is_featured: nextValue } : item
        )
      );
      showMessage('success', `"${product.title}" featured status updated.`);
    } catch (err: any) {
      showMessage('error', err?.response?.data?.detail || err.message || 'Failed to update featured status');
    } finally {
      setFeatureLoadingId(null);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatDisplayPrice = (amount: number, currency?: Product['currency']) => {
    return formatPriceWithConversion(
      amount,
      currency || 'NGN',
      currentCurrency,
      exchangeRates
    );
  };

  const renderStockCell = (product: Product) => {
    if (product.made_to_order) {
      return (
        <div>
          <p className="text-sm font-medium text-blue-700">Made to Order</p>
          {product.made_to_order_timeline && (
            <p className="text-xs text-gray-500">{product.made_to_order_timeline}</p>
          )}
        </div>
      );
    }

    return <p className="text-sm text-gray-900">{product.total_stock}</p>;
  };

  const getModerationBadge = (status: string) => {
    switch (status) {
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle className="w-3 h-3" />
            Approved
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <XCircle className="w-3 h-3" />
            Rejected
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
            <AlertCircle className="w-3 h-3" />
            Pending
          </span>
        );
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return (
          <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800">
            Active
          </span>
        );
      case 'inactive':
        return (
          <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-gray-100 text-gray-800">
            Inactive
          </span>
        );
      case 'archived':
        return (
          <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800">
            Archived
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-1 rounded text-xs font-medium bg-blue-100 text-blue-800">
            Draft
          </span>
        );
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex">
      <AdminSidebar activeSection="products" />

      <main className="flex-1 p-8 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-display text-gray-900 mb-2">Product Management</h1>
            <p className="text-gray-600 font-ui">Review and moderate vendor products</p>
          </div>
          <CurrencySwitcher value={currentCurrency} onChange={setCurrency} />
        </div>

        {/* Message */}
        {message && (
          <div
            className={`p-4 rounded-lg ${
              message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
            }`}
          >
            {message.text}
          </div>
        )}

        {/* Filters */}
        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Search by product title or SKU..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Filter Row */}
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Moderation Status</label>
              <select
                value={moderationFilter}
                onChange={(e) => {
                  setModerationFilter(e.target.value);
                  setPage(1);
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="all">All Moderation Statuses</option>
                <option value="pending">Pending Review</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>

            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Product Status</label>
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setPage(1);
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="all">All Product Statuses</option>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
                <option value="archived">Archived</option>
              </select>
            </div>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white rounded-lg border border-gray-200 p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <Package className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Products</p>
                <p className="text-2xl font-semibold text-gray-900">{total}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Products Table */}
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Product
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Vendor
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Price
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Stock
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Moderation
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Feature Product
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Created
                  </th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {loading ? (
                  <tr>
                    <td colSpan={9} className="px-6 py-12 text-center text-gray-500">
                      Loading products...
                    </td>
                  </tr>
                ) : products.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-6 py-12 text-center text-gray-500">
                      No products found
                    </td>
                  </tr>
                ) : (
                  products.map((product) => (
                    <tr key={product.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4">
                        <div className="flex items-start gap-3">
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-gray-900 truncate">{product.title}</p>
                            {product.sku && (
                              <p className="text-sm text-gray-500 mt-0.5">SKU: {product.sku}</p>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <p className="text-sm text-gray-900">{product.vendor.business_name}</p>
                      </td>
                      <td className="px-6 py-4">
                        <p className="text-sm text-gray-900">
                          {formatDisplayPrice(product.base_price, product.currency)}
                        </p>
                        {product.compare_at_price && (
                          <p className="text-xs text-gray-500 line-through">
                            {formatDisplayPrice(product.compare_at_price, product.currency)}
                          </p>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {renderStockCell(product)}
                      </td>
                      <td className="px-6 py-4">{getStatusBadge(product.status)}</td>
                      <td className="px-6 py-4">{getModerationBadge(product.moderation_status)}</td>
                      <td className="px-6 py-4">
                        <button
                          type="button"
                          onClick={() => handleFeatureToggle(product)}
                          disabled={product.moderation_status !== 'approved' || featureLoadingId === product.id}
                          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                            product.is_featured ? 'bg-emerald-600' : 'bg-gray-200'
                          } disabled:opacity-50`}
                          aria-label="Feature Product"
                          title={
                            product.moderation_status === 'approved'
                              ? 'Feature Product'
                              : 'Only approved products can be featured'
                          }
                        >
                          <span
                            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                              product.is_featured ? 'translate-x-6' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </td>
                      <td className="px-6 py-4">
                        <p className="text-sm text-gray-900">{formatDate(product.created_at)}</p>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          {/* View Button */}
                          <button
                            onClick={() => handleViewProduct(product.id)}
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 rounded-lg"
                            title="View Details"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>

                          {/* Edit Button */}
                          <button
                            onClick={() => handleEditProduct(product.id)}
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 hover:bg-blue-100 rounded-lg"
                            title="Edit Product"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>

                          {/* Delete Button */}
                          <button
                            onClick={() => setDeleteModal(product)}
                            disabled={actionLoading === product.id}
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-red-700 bg-red-50 border border-red-200 hover:bg-red-100 rounded-lg disabled:opacity-50"
                            title="Delete Product"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>

                          {/* Approve/Reject for pending products */}
                          {product.moderation_status === 'pending' && (
                            <>
                              <button
                                onClick={() => setApprovalModal(product)}
                                disabled={actionLoading === product.id}
                                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg disabled:opacity-50"
                                title="Approve Product"
                              >
                                <CheckCircle className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={() => setRejectModal(product)}
                                disabled={actionLoading === product.id}
                                className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
                                title="Reject Product"
                              >
                                <XCircle className="w-3.5 h-3.5" />
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-6 py-4 border-t border-gray-200 flex items-center justify-between">
              <div className="text-sm text-gray-700">
                Showing page {page} of {totalPages} ({total} total products)
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(page - 1)}
                  disabled={page === 1}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page === totalPages}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Approval Modal */}
      {approvalModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Approve Product</h3>
            <p className="text-gray-600">
              Are you sure you want to approve "<strong>{approvalModal.title}</strong>"? The vendor will be
              notified via email.
            </p>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Approval Notes (Optional)
              </label>
              <textarea
                value={approvalNotes}
                onChange={(e) => setApprovalNotes(e.target.value)}
                placeholder="Add any notes for the vendor..."
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-green-500 focus:border-transparent"
              />
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setApprovalModal(null);
                  setApprovalNotes('');
                }}
                disabled={actionLoading === approvalModal.id}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleApproveProduct}
                disabled={actionLoading === approvalModal.id}
                className="px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 rounded-lg disabled:opacity-50"
              >
                {actionLoading === approvalModal.id ? 'Approving...' : 'Approve Product'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rejection Modal */}
      {rejectModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-lg w-full p-6 space-y-4">
            <h3 className="text-lg font-semibold text-gray-900">Reject Product</h3>
            <p className="text-gray-600">
              Please provide a reason for rejecting "<strong>{rejectModal.title}</strong>". The vendor will
              receive this reason via email.
            </p>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Rejection Reason <span className="text-red-500">*</span>
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Explain why this product cannot be approved (minimum 10 characters)..."
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1">
                {rejectionReason.length}/10 characters minimum
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Additional Notes (Optional)
              </label>
              <textarea
                value={rejectionNotes}
                onChange={(e) => setRejectionNotes(e.target.value)}
                placeholder="Add any additional guidance or suggestions..."
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-red-500 focus:border-transparent"
              />
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setRejectModal(null);
                  setRejectionReason('');
                  setRejectionNotes('');
                }}
                disabled={actionLoading === rejectModal.id}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectProduct}
                disabled={actionLoading === rejectModal.id || rejectionReason.length < 10}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
              >
                {actionLoading === rejectModal.id ? 'Rejecting...' : 'Reject Product'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-lg w-full p-6 space-y-4">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                  <Trash2 className="w-5 h-5 text-red-600" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-gray-900 mb-1">Delete Product</h3>
                <p className="text-sm text-gray-600">
                  Are you sure you want to delete <strong>"{deleteModal.title}"</strong>? This action will permanently remove the product from the marketplace.
                </p>
              </div>
            </div>

            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-800">
                <strong>Warning:</strong> This action cannot be undone. The product will be permanently deleted from the system.
              </p>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteModal(null)}
                disabled={actionLoading === deleteModal.id}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteProduct}
                disabled={actionLoading === deleteModal.id}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
              >
                {actionLoading === deleteModal.id ? 'Deleting...' : 'Delete Product'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
