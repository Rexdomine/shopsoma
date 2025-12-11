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

  // Calculate order stats
  const pendingCount = orders.filter((o) => o.status === 'pending' || o.status === 'processing').length;
  const completedCount = orders.filter((o) => o.status === 'delivered').length;

  useEffect(() => {
    fetchOrders();
  }, [currentPage, search]);

  const fetchOrders = async () => {
    try {
      setLoading(true);
      const response = await getVendorOrders({
        page: currentPage,
        page_size: 20,
        search,
      });
      setOrders(response.orders);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      console.error('Error fetching orders:', err);
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
