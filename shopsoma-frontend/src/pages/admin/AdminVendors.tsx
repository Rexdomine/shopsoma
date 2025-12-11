import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Eye, Check, X, AlertCircle, CheckCircle, Store, TrendingUp, Package, ShoppingBag, RotateCcw, Trash2 } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { adminService, type VendorListItem } from '../../services/adminService';

export default function AdminVendors() {
  const navigate = useNavigate();
  const [vendors, setVendors] = useState<VendorListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [approvedFilter, setApprovedFilter] = useState<string>('all');
  const [kycFilter, setKycFilter] = useState<string>('all');
  const [onboardingFilter, setOnboardingFilter] = useState<string>('all');
  const [storeStatusFilter, setStoreStatusFilter] = useState<string>('all');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const pageSize = 20;

  useEffect(() => {
    loadVendors();
  }, [page, approvedFilter, kycFilter, onboardingFilter, storeStatusFilter, search]);

  const loadVendors = async () => {
    try {
      setLoading(true);
      const filters: any = {
        page,
        page_size: pageSize,
        search: search || undefined,
      };

      if (approvedFilter !== 'all') {
        filters.approved = approvedFilter === 'approved';
      }

      if (kycFilter !== 'all') {
        filters.kyc_status = kycFilter;
      }

      if (onboardingFilter === 'incomplete') {
        filters.is_onboarding = true;
      } else if (onboardingFilter === 'complete') {
        filters.is_onboarding = false;
      }

      const response = await adminService.listVendors(filters);

      setVendors(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (error: any) {
      console.error('Failed to load vendors:', error);
      showMessage('error', 'Failed to load vendors');
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const handleRestoreStore = async (vendorId: string, businessName: string) => {
    if (!window.confirm(`Are you sure you want to restore ${businessName}'s store?`)) {
      return;
    }

    try {
      await adminService.restoreVendorStore(vendorId);
      showMessage('success', `Store restored successfully for ${businessName}`);
      loadVendors();
    } catch (error: any) {
      console.error('Failed to restore store:', error);
      showMessage('error', error?.response?.data?.detail || 'Failed to restore store');
    }
  };

  const filteredVendors = vendors.filter((vendor) => {
    if (storeStatusFilter === 'deleted') {
      return !!vendor.store_deleted_at;
    } else if (storeStatusFilter === 'paused') {
      return !vendor.store_deleted_at && !vendor.store_active;
    } else if (storeStatusFilter === 'active') {
      return !vendor.store_deleted_at && vendor.store_active;
    }
    return true;
  });

  const getKYCBadge = (kycStatus?: string) => {
    switch (kycStatus) {
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-600">
            Pending
          </span>
        );
      case 'submitted':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700">
            Submitted
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">
            <CheckCircle className="w-3 h-3" />
            Approved
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
            <AlertCircle className="w-3 h-3" />
            Rejected
          </span>
        );
      default:
        return <span className="text-xs text-gray-400">-</span>;
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  return (
    <div className="min-h-screen bg-[#F9FAFB] flex">
      <AdminSidebar activeSection="vendors" />

      <main className="flex-1 p-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-display text-gray-900 mb-2">Vendors</h1>
          <p className="text-gray-600 font-ui">Manage vendor accounts and monitor onboarding status</p>
        </div>

        {/* Message */}
        {message && (
          <div
            className={`rounded-xl p-4 flex items-center gap-3 ${
              message.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-800'
                : 'bg-red-50 border border-red-200 text-red-800'
            }`}
          >
            {message.type === 'success' ? (
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
            )}
            <p className="text-sm font-medium">{message.text}</p>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Total Vendors</p>
                <p className="text-2xl font-display text-gray-900 mt-1">{total}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-[#105E53]/10 flex items-center justify-center">
                <Store className="w-6 h-6 text-[#105E53]" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Products</p>
                <p className="text-2xl font-display text-gray-900 mt-1">
                  {vendors.reduce((sum, v) => sum + v.total_products, 0)}
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-blue-100 flex items-center justify-center">
                <Package className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Orders</p>
                <p className="text-2xl font-display text-gray-900 mt-1">
                  {vendors.reduce((sum, v) => sum + v.total_orders, 0)}
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-purple-100 flex items-center justify-center">
                <ShoppingBag className="w-6 h-6 text-purple-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Total Revenue</p>
                <p className="text-2xl font-display text-gray-900 mt-1">
                  {formatCurrency(vendors.reduce((sum, v) => sum + v.total_revenue, 0))}
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-green-100 flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            {/* Search */}
            <div className="relative md:col-span-2">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by name, email, or business..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui"
              />
            </div>

            {/* Approved Filter */}
            <select
              value={approvedFilter}
              onChange={(e) => {
                setApprovedFilter(e.target.value);
                setPage(1);
              }}
              className="px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui bg-gray-50"
            >
              <option value="all">All Status</option>
              <option value="approved">Approved</option>
              <option value="pending">Pending Approval</option>
            </select>

            {/* Onboarding Filter */}
            <select
              value={onboardingFilter}
              onChange={(e) => {
                setOnboardingFilter(e.target.value);
                setPage(1);
              }}
              className="px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui bg-gray-50"
            >
              <option value="all">All Onboarding</option>
              <option value="incomplete">Incomplete</option>
              <option value="complete">Complete</option>
            </select>

            {/* Store Status Filter */}
            <select
              value={storeStatusFilter}
              onChange={(e) => {
                setStoreStatusFilter(e.target.value);
                setPage(1);
              }}
              className="px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui bg-gray-50"
            >
              <option value="all">All Stores</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="deleted">Deleted</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-gray-600 font-ui">
            Showing {filteredVendors.length} of {total} vendors
          </div>
        </div>

        {/* Vendors table */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-12 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#105E53] mx-auto"></div>
              <p className="mt-4 text-gray-600 font-ui">Loading vendors...</p>
            </div>
          ) : filteredVendors.length === 0 ? (
            <div className="p-12 text-center">
              <Store className="w-16 h-16 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-600 font-ui">No vendors found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Business
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Store
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      KYC
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Onboarding
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Metrics
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {filteredVendors.map((vendor) => (
                    <tr key={vendor.id} className="hover:bg-gray-50 transition">
                      <td className="px-6 py-4">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">{vendor.business_name}</p>
                          <p className="text-xs text-gray-500">{vendor.email}</p>
                          <p className="text-xs text-gray-400 mt-0.5">{vendor.full_name}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        {vendor.approved ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">
                            <CheckCircle className="w-3 h-3" />
                            Approved
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
                            Pending
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        {vendor.store_deleted_at ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">
                            <Trash2 className="w-3 h-3" />
                            Deleted
                          </span>
                        ) : vendor.store_active ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700">
                            <CheckCircle className="w-3 h-3" />
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-700">
                            Paused
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">{getKYCBadge(vendor.kyc_status)}</td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <div className="flex items-center gap-1">
                            {vendor.brand_info_completed ? (
                              <Check className="w-4 h-4 text-green-600" />
                            ) : (
                              <X className="w-4 h-4 text-red-400" />
                            )}
                            <span className="text-xs text-gray-600">Brand</span>
                          </div>
                          <div className="flex items-center gap-1">
                            {vendor.payout_info_completed ? (
                              <Check className="w-4 h-4 text-green-600" />
                            ) : (
                              <X className="w-4 h-4 text-red-400" />
                            )}
                            <span className="text-xs text-gray-600">Payout</span>
                          </div>
                        </div>
                        {vendor.is_onboarding && (
                          <span className="inline-block mt-1 px-2 py-0.5 rounded text-xs bg-amber-50 text-amber-700 border border-amber-200">
                            In Progress
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-xs space-y-0.5">
                          <div className="flex items-center gap-2 text-gray-600">
                            <Package className="w-3 h-3" />
                            <span>{vendor.total_products} products</span>
                          </div>
                          <div className="flex items-center gap-2 text-gray-600">
                            <ShoppingBag className="w-3 h-3" />
                            <span>{vendor.total_orders} orders</span>
                          </div>
                          <div className="text-gray-900 font-medium">
                            {formatCurrency(vendor.total_revenue)}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          {vendor.store_deleted_at && (
                            <button
                              onClick={() => handleRestoreStore(vendor.id, vendor.business_name)}
                              className="p-2 text-green-600 hover:text-green-700 hover:bg-green-50 rounded-lg transition"
                              title="Restore store"
                            >
                              <RotateCcw className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => navigate(`/admin/vendors/${vendor.id}`)}
                            className="p-2 text-gray-600 hover:text-[#105E53] hover:bg-gray-100 rounded-lg transition"
                            title="View details"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Previous
            </button>
            <span className="px-4 py-2 text-sm text-gray-600 font-ui">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Next
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
