import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { checkoutService, type Order } from '../../services/checkoutService';
import { useAuth } from '../../context/AuthContext';
import { usePreferenceStore } from '../../store/preferenceStore';
import { formatPriceWithCurrency } from '../../utils/pricing';
import CustomerShippingQuotes from '../../components/shipping/CustomerShippingQuotes';
import { normalizeProductImageUrl } from '../../utils/productImages';

export default function ProfileOrders() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [orders, setOrders] = useState<Order[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoadingOrderDetails, setIsLoadingOrderDetails] = useState(false);
  const pageSize = 10;
  const preferredCurrency = usePreferenceStore((state) => state.currency);

  useEffect(() => {
    loadOrders();
  }, [currentPage]);

  const loadOrders = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await checkoutService.getOrders(currentPage, pageSize);
      setOrders(data.orders || []);
      setTotalPages(Math.ceil((data.total || 0) / pageSize) || 1);
    } catch (err: any) {
      console.error('Error loading orders:', err);
      setError(err?.response?.data?.detail || 'Failed to load your orders. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleOrderClick = async (order: Order) => {
    setIsModalOpen(true);
    setIsLoadingOrderDetails(true);
    try {
      // Fetch full order details with items
      const fullOrder = await checkoutService.getOrder(order.id);
      setSelectedOrder(fullOrder);
    } catch (error) {
      console.error('Error loading order details:', error);
      setSelectedOrder(order); // Fallback to basic order data
    } finally {
      setIsLoadingOrderDetails(false);
    }
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedOrder(null);
  };

  const handleTrackOrder = () => {
    if (selectedOrder) {
      navigate(ROUTES.ORDER_TRACKING.replace(':orderId', selectedOrder.id));
    }
  };

  const handleSignOut = async () => {
    await logout();
    navigate(ROUTES.LOGIN, { replace: true });
  };

  const menuItems = [
    { label: 'Account Details', route: ROUTES.PROFILE },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Order History', route: ROUTES.PROFILE_ORDERS, active: true },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
    { label: 'Return', route: ROUTES.PROFILE_RETURNS },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
    { label: 'Sign Out', onClick: handleSignOut },
  ];

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    }).replace(/ /g, ' - ');
  };

  const handlePageChange = (page: number) => {
    if (page >= 1 && page <= totalPages) {
      setCurrentPage(page);
    }
  };

  return (
    <Layout>
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />

          <section className="flex-1">
            <header className="mb-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-gray-400">My Account</p>
                <h1 className="text-2xl font-serif text-dark mt-1">My Orders</h1>
              </div>
              <button
                type="button"
                onClick={() => navigate(ROUTES.HOME)}
                className="text-xs uppercase tracking-wider text-primary hover:underline font-medium self-start sm:self-auto"
              >
                Continue Shopping &rarr;
              </button>
            </header>

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 p-4 rounded-sm text-sm mb-6 flex items-center justify-between">
                <span>{error}</span>
                <button
                  type="button"
                  onClick={loadOrders}
                  className="text-xs font-semibold underline hover:no-underline"
                >
                  Try Again
                </button>
              </div>
            )}

            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="text-sm text-gray-500">Loading orders...</div>
              </div>
            ) : orders.length > 0 ? (
              <div className="space-y-6">
                <div className="overflow-x-auto">
                  <table className="min-w-full text-left text-sm">
                    <thead>
                      <tr className="uppercase text-xs tracking-[0.2em] text-gray-400">
                        <th className="py-3 px-4 font-semibold">S/N</th>
                        <th className="py-3 px-4 font-semibold">Order ID</th>
                        <th className="py-3 px-4 font-semibold">Date</th>
                        <th className="py-3 px-4 font-semibold">Amount</th>
                        <th className="py-3 px-4 font-semibold">Payment</th>
                        <th className="py-3 px-4 font-semibold">Fulfillment</th>
                        <th className="py-3 px-4 font-semibold text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map((order, index) => (
                        <tr
                          key={order.id}
                          className="border-t border-gray-100 text-gray-700 hover:bg-gray-50 cursor-pointer"
                          onClick={() => handleOrderClick(order)}
                        >
                          <td className="py-3 px-4">{(currentPage - 1) * pageSize + index + 1}.</td>
                          <td className="py-3 px-4 text-primary font-semibold hover:underline">{order.order_number}</td>
                          <td className="py-3 px-4">{formatDate(order.created_at)}</td>
                          <td className="py-3 px-4">{formatPriceWithCurrency(order.total_amount, preferredCurrency)}</td>
                          <td className="py-3 px-4">
                            <span className={`px-3 py-1 rounded-sm text-xs font-semibold ${getPaymentStatusStyles(order.payment_status)}`}>
                              {formatStatusLabel(order.payment_status)}
                            </span>
                          </td>
                          <td className="py-3 px-4">
                            <span className={`px-3 py-1 rounded-sm text-xs font-semibold ${getFulfillmentStatusStyles(order.fulfillment_status)}`}>
                              {formatStatusLabel(order.fulfillment_status)}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleOrderClick(order);
                              }}
                              className="text-xs font-semibold text-primary hover:underline"
                            >
                              View Details
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {totalPages > 1 && (
                  <div className="flex items-center justify-center gap-1 text-xs text-gray-600">
                    <button
                      onClick={() => handlePageChange(currentPage - 1)}
                      disabled={currentPage === 1}
                      className="w-8 h-8 border border-gray-200 rounded-sm disabled:opacity-50"
                    >
                      ←
                    </button>
                    {Array.from({ length: Math.min(3, totalPages) }, (_, i) => i + 1).map((page) => (
                      <button
                        key={page}
                        onClick={() => handlePageChange(page)}
                        className={`w-8 h-8 border border-gray-200 rounded-sm ${
                          page === currentPage ? 'bg-gray-100 text-dark' : ''
                        }`}
                      >
                        {page}
                      </button>
                    ))}
                    {totalPages > 3 && (
                      <>
                        <span className="px-2">...</span>
                        <button
                          onClick={() => handlePageChange(totalPages)}
                          className="w-8 h-8 border border-gray-200 rounded-sm"
                        >
                          {totalPages}
                        </button>
                      </>
                    )}
                    <button
                      onClick={() => handlePageChange(currentPage + 1)}
                      disabled={currentPage === totalPages}
                      className="w-8 h-8 border border-gray-200 rounded-sm disabled:opacity-50"
                    >
                      →
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="max-w-md mx-auto py-12 px-6 text-center space-y-4">
                <div className="mx-auto w-12 h-12 flex items-center justify-center rounded-full bg-primary/10 text-primary text-xl">
                  !
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-800">You currently have no order yet</p>
                  <p className="text-xs text-gray-500 mt-1">
                    No order yet, once you have completed the checkout process, you can view and track your order here.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => navigate(ROUTES.HOME)}
                  className="px-6 py-3 rounded-sm bg-primary text-white text-sm font-semibold hover:bg-primary-dark transition"
                >
                  Go to Shop
                </button>
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Order Details Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center p-4 z-50" onClick={handleCloseModal}>
          <div className="bg-white rounded-sm max-w-3xl w-full max-h-[90vh] overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
            {isLoadingOrderDetails ? (
              <div className="p-12 text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4" />
                <p className="text-sm text-gray-500">Loading order details...</p>
              </div>
            ) : selectedOrder ? (
              <>
                <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-dark">Order Details</h2>
                  <button onClick={handleCloseModal} className="text-gray-400 hover:text-gray-600 text-2xl" aria-label="Close">
                    ×
                  </button>
                </div>
                <div className="p-6 space-y-6">
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Order Number:</span>
                      <span className="font-semibold text-gray-900">{selectedOrder.order_number}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Order Date:</span>
                      <span className="font-semibold text-gray-900">
                        {new Date(selectedOrder.created_at).toLocaleDateString('en-US', {
                          year: 'numeric',
                          month: 'long',
                          day: 'numeric',
                        })}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Payment Status:</span>
                      <span className={`font-semibold ${
                        selectedOrder.payment_status === 'paid'
                          ? 'text-green-600'
                          : selectedOrder.payment_status === 'pending'
                            ? 'text-amber-600'
                            : 'text-red-600'
                      }`}>
                        {formatStatusLabel(selectedOrder.payment_status)}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Fulfillment Status:</span>
                      <span className="font-semibold text-gray-900">
                        {formatStatusLabel(selectedOrder.fulfillment_status)}
                      </span>
                    </div>
                  </div>

                  {selectedOrder.items && selectedOrder.items.length > 0 && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-[0.2em] mb-3">
                        Items ({selectedOrder.items.length})
                      </h3>
                      <div className="space-y-3">
                        {selectedOrder.items.map((item: any, index: number) => {
                          const productTitle = item.product_title || item.product_name || 'Product';
                          const variantDisplay = item.variant_name || item.variant_title || item.variant_details?.name || item.variant_details?.title;
                          const rawImageSrc = item.product_image_url || item.product_image || item.variant_details?.image_url;
                          const imageSrc = normalizeProductImageUrl(rawImageSrc) || '/images/placeholder-product.svg';

                          return (
                            <div key={index} className="flex gap-3 border-b border-gray-100 pb-3">
                              <div className="flex-shrink-0">
                                <img
                                  src={imageSrc}
                                  alt={productTitle}
                                  className="w-16 h-16 object-cover rounded-sm border border-gray-200"
                                  onError={(e) => {
                                    e.currentTarget.src = '/images/placeholder-product.svg';
                                  }}
                                />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="font-medium text-sm text-gray-900">{productTitle}</p>
                                {variantDisplay && <p className="text-xs text-gray-500 mt-1">{variantDisplay}</p>}
                                <p className="text-xs text-gray-500 mt-1">Qty: {item.quantity}</p>
                              </div>
                              <div className="text-right">
                                <p className="font-semibold text-sm text-gray-900">
                                  {formatPriceWithCurrency(item.subtotal || item.unit_price * item.quantity, preferredCurrency)}
                                </p>
                                <p className="text-xs text-gray-500">
                                  {formatPriceWithCurrency(item.unit_price, preferredCurrency)} each
                                </p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  <div className="border-t border-gray-200 pt-4 space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Subtotal:</span>
                      <span>{formatPriceWithCurrency(selectedOrder.subtotal, preferredCurrency)}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-gray-600">Shipping:</span>
                      <span>{formatPriceWithCurrency(selectedOrder.shipping_cost, preferredCurrency)}</span>
                    </div>
                    {selectedOrder.tax_amount > 0 && (
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-600">Tax:</span>
                        <span>{formatPriceWithCurrency(selectedOrder.tax_amount, preferredCurrency)}</span>
                      </div>
                    )}
                    {selectedOrder.discount_amount > 0 && (
                      <div className="flex justify-between text-sm text-green-600">
                        <span>Discount:</span>
                        <span>-{formatPriceWithCurrency(selectedOrder.discount_amount, preferredCurrency)}</span>
                      </div>
                    )}
                    <div className="flex justify-between text-base font-bold border-t border-gray-200 pt-2 mt-2">
                      <span>Total:</span>
                      <span>{formatPriceWithCurrency(selectedOrder.total_amount, preferredCurrency)}</span>
                    </div>
                  </div>

                  <CustomerShippingQuotes orderId={selectedOrder.id} />

                  <div className="flex flex-col sm:flex-row gap-3 pt-2">
                    <button
                      type="button"
                      onClick={handleTrackOrder}
                      className="flex-1 rounded-sm bg-primary text-white font-semibold py-3 text-sm hover:bg-primary-dark transition"
                    >
                      Track Order
                    </button>
                    <button
                      type="button"
                      onClick={handleCloseModal}
                      className="flex-1 rounded-sm bg-gray-100 text-gray-700 font-semibold py-3 text-sm hover:bg-gray-200 transition"
                    >
                      Close
                    </button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      )}
    </Layout>
  );
}

export function formatStatusLabel(status?: string): string {
  if (!status) return '';
  return status
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function getPaymentStatusStyles(status: string): string {
  switch (status.toLowerCase()) {
    case 'paid':
    case 'completed':
      return 'bg-emerald-50 text-emerald-700';
    case 'pending':
    case 'processing':
    case 'partially_paid':
      return 'bg-amber-50 text-amber-700';
    case 'failed':
    case 'cancelled':
    case 'refunded':
      return 'bg-red-50 text-red-700';
    default:
      return 'bg-gray-100 text-gray-600';
  }
}

function getFulfillmentStatusStyles(status: string): string {
  switch (status.toLowerCase()) {
    case 'fulfilled':
    case 'delivered':
      return 'bg-emerald-50 text-emerald-700';
    case 'pending':
    case 'processing':
    case 'order_received':
    case 'preparing_for_pickup':
    case 'pickup_scheduled':
      return 'bg-amber-50 text-amber-700';
    case 'shipped':
    case 'picked_up':
    case 'in_transit':
    case 'out_for_delivery':
      return 'bg-blue-50 text-blue-700';
    case 'cancelled':
    case 'returned':
    case 'delivery_failed':
      return 'bg-red-50 text-red-700';
    default:
      return 'bg-gray-100 text-gray-600';
  }
}
