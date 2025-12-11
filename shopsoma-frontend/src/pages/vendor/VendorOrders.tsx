import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import ToastContainer from '../../components/ui/ToastContainer';
import { useToast } from '../../hooks/useToast';
import { getVendorOrders, exportOrdersToCSV, type VendorOrder } from '../../services/orderService';
import { ROUTES } from '../../config/constants';
import { Search, Loader2, Filter, ArrowUpDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Download } from 'lucide-react';

function formatPrice(price: number) {
  return `$${price.toLocaleString()}`;
}

export default function VendorOrders() {
  const { toasts, hideToast } = useToast();
  const navigate = useNavigate();
  const [orders, setOrders] = useState<VendorOrder[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Calculate order stats
  const pendingCount = orders.filter((o) => o.status === 'pending' || o.status === 'processing').length;
  const completedCount = orders.filter((o) => o.status === 'delivered').length;

  useEffect(() => {
    fetchOrders();
  }, [currentPage, search]);

  const fetchOrders = async () => {
    try {
      setLoading(true);
      setError(null); // Clear previous errors
      const response = await getVendorOrders({
        page: currentPage,
        page_size: 20,
        search,
      });
      console.log('✅ Vendor orders response:', response);
      setOrders(response.orders || []);
      setTotal(response.total || 0);
      setTotalPages(response.total_pages || 1);
    } catch (err: any) {
      console.error('❌ Error fetching orders:', err);
      console.error('📋 Error status:', err.response?.status);
      console.error('📋 Error data:', err.response?.data);
      console.error('📋 Full error:', err);

      // Extract detailed error message
      let userMessage = 'Failed to load orders. Please try again.';
      let technicalDetails = '';

      if (err.response?.data?.detail) {
        const detail = err.response.data.detail;

        // Handle structured error response
        if (typeof detail === 'object') {
          userMessage = detail.message || userMessage;
          technicalDetails = JSON.stringify(detail, null, 2);

          // Special handling for specific error codes
          if (detail.error_code === 'VENDOR_PROFILE_NOT_FOUND') {
            userMessage = 'No vendor profile found. Please complete vendor registration.';
          } else if (detail.error_code === 'VENDOR_NOT_APPROVED') {
            userMessage = 'Your vendor account is pending approval. Please wait for admin approval.';
          } else if (detail.error_code === 'INVALID_ROLE') {
            userMessage = 'Access denied. Please log in with a vendor account.';
          }
        } else {
          // Handle string error response
          userMessage = detail;
          technicalDetails = detail;
        }
      } else if (err.response?.status === 401) {
        userMessage = 'Authentication expired. Please log in again.';
      } else if (err.response?.status === 403) {
        userMessage = 'Access denied. Please check your account status.';
      } else if (err.response?.status === 404) {
        userMessage = 'Vendor profile not found. Please complete registration.';
      }

      console.error('🔍 User message:', userMessage);
      console.error('🔍 Technical details:', technicalDetails);

      setError(userMessage);
      setOrders([]);
      setTotal(0);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value);
    setCurrentPage(1); // Reset to first page on search
  };

  const handleExportCSV = () => {
    exportOrdersToCSV(orders);
  };

  const getStatusBadge = (status: string) => {
    const statusConfig: Record<string, { label: string; className: string }> = {
      delivered: {
        label: 'Delivered',
        className: 'bg-[#E8F7EF] text-[#19984B]',
      },
      processing: {
        label: 'Processing',
        className: 'bg-[#FEF3E2] text-[#D97706]',
      },
      shipped: {
        label: 'Shipped',
        className: 'bg-blue-100 text-blue-700',
      },
      pending: {
        label: 'Pending',
        className: 'bg-amber-100 text-amber-700',
      },
      cancelled: {
        label: 'Cancelled',
        className: 'bg-red-100 text-red-700',
      },
    };

    const config = statusConfig[status.toLowerCase()] || statusConfig.pending;

    return (
      <span className={`px-3 py-1 rounded-full text-xs font-semibold ${config.className}`}>
        {config.label}
      </span>
    );
  };

  const goToFirstPage = () => setCurrentPage(1);
  const goToLastPage = () => setCurrentPage(totalPages);
  const goToPrevPage = () => setCurrentPage((prev) => Math.max(1, prev - 1));
  const goToNextPage = () => setCurrentPage((prev) => Math.min(totalPages, prev + 1));
  const handleRowClick = (order: VendorOrder) => {
    navigate(ROUTES.VENDOR_ORDER_DETAIL.replace(':id', order.id));
  };

  // Calculate vendor payout for an order
  const calculateVendorPayout = (order: VendorOrder) => {
    return order.items.reduce((sum, item) => sum + item.vendor_payout, 0);
  };

  // Get items summary for an order
  const getItemsSummary = (order: VendorOrder) => {
    const totalItems = order.items.reduce((sum, item) => sum + item.quantity, 0);
    const uniqueProducts = order.items.length;
    return `${totalItems} item${totalItems !== 1 ? 's' : ''} (${uniqueProducts} product${uniqueProducts !== 1 ? 's' : ''})`;
  };

  return (
    <div className="flex min-h-screen bg-gray-50">
      <VendorSidebar />

      <div className="flex-1">
        <div className="px-8 py-8">
          {/* Header Section */}
          <div className="flex items-center justify-between mb-8">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900">Order Management</h1>
              <div className="flex items-center gap-6 mt-2 text-sm">
                <span className="text-amber-600">
                  <span className="inline-block w-2 h-2 bg-amber-500 rounded-full mr-2"></span>
                  Pending Orders: {pendingCount}
                </span>
                <span className="text-[#19984B]">
                  <span className="inline-block w-2 h-2 bg-[#19984B] rounded-full mr-2"></span>
                  Completed Orders: {completedCount}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Search Bar */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search"
                  value={search}
                  onChange={handleSearchChange}
                  className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent w-64"
                />
              </div>

              {/* Filter Button */}
              <button
                type="button"
                className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                aria-label="Filter"
              >
                <Filter className="h-5 w-5 text-gray-600" />
              </button>

              {/* Sort Button */}
              <button
                type="button"
                className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                aria-label="Sort"
              >
                <ArrowUpDown className="h-5 w-5 text-gray-600" />
              </button>
            </div>
          </div>

          {/* Orders Table */}
          {loading ? (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="flex items-center justify-center py-20 text-gray-600 gap-3">
                <Loader2 className="h-6 w-6 animate-spin" />
                <span className="text-sm">Loading orders...</span>
              </div>
            </div>
          ) : error ? (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-20 text-center">
                <div className="mb-4">
                  <svg className="mx-auto h-12 w-12 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <p className="text-red-600 font-medium text-base mb-2">Unable to Load Orders</p>
                <p className="text-gray-600 text-sm mb-4">{error}</p>
                <button
                  onClick={() => fetchOrders()}
                  className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#105E53]"
                >
                  Try Again
                </button>
              </div>
            </div>
          ) : orders.length === 0 ? (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-6 py-20 text-center">
                <p className="text-gray-600 text-sm">No orders found.</p>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <table className="w-full table-fixed">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="w-[180px] px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Order Number
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Order Items
                    </th>
                    <th className="w-[140px] px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Your Payout
                    </th>
                    <th className="w-[160px] px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {orders.map((order) => (
                    <tr
                      key={order.id}
                      className="hover:bg-gray-50 transition cursor-pointer"
                      onClick={() => handleRowClick(order)}
                    >
                      <td className="w-[180px] px-6 py-4">
                        <div className="text-sm font-medium text-gray-900 whitespace-nowrap">Order {order.order_number}</div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-gray-600 line-clamp-2">{getItemsSummary(order)}</div>
                      </td>
                      <td className="w-[140px] px-6 py-4">
                        <div className="text-sm font-medium text-gray-900 whitespace-nowrap">₦{calculateVendorPayout(order).toFixed(2)}</div>
                      </td>
                      <td className="w-[160px] px-6 py-4">{getStatusBadge(order.fulfillment_status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination Footer */}
              <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-white">
                {/* Pagination Controls */}
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={goToFirstPage}
                    disabled={currentPage === 1}
                    className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="First page"
                  >
                    <ChevronsLeft className="h-4 w-4 text-gray-600" />
                  </button>
                  <button
                    type="button"
                    onClick={goToPrevPage}
                    disabled={currentPage === 1}
                    className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Previous page"
                  >
                    <ChevronLeft className="h-4 w-4 text-gray-600" />
                  </button>
                  <span className="px-4 py-2 text-sm font-medium text-gray-700">
                    {String(currentPage).padStart(2, '0')}
                  </span>
                  <button
                    type="button"
                    onClick={goToNextPage}
                    disabled={currentPage === totalPages}
                    className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Next page"
                  >
                    <ChevronRight className="h-4 w-4 text-gray-600" />
                  </button>
                  <button
                    type="button"
                    onClick={goToLastPage}
                    disabled={currentPage === totalPages}
                    className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Last page"
                  >
                    <ChevronsRight className="h-4 w-4 text-gray-600" />
                  </button>
                </div>

                {/* Download CSV Button */}
                <button
                  type="button"
                  onClick={handleExportCSV}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
                >
                  <Download className="h-4 w-4" />
                  Download CSV
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <ToastContainer toasts={toasts} onDismiss={hideToast} />
    </div>
  );
}
