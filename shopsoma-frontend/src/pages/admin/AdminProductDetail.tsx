import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Edit2, Loader2, Package, Tag, Trash2, XCircle } from 'lucide-react';
import { ROUTES } from '../../config/constants';
import { apiErrorMessage } from '../../utils/apiErrorMessage';
import { adminService } from '../../services/adminService';
import type { Product } from '../../types';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion } from '../../utils/pricing';

function formatDate(dateStr: string) {
  const d = new Date(dateStr);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const yy = String(d.getFullYear());
  return `${mm}/${dd}/${yy}`;
}

const moderationAmbiguityKey = (productId: string) => `admin-moderation-outcome-unknown:${productId}`;

type ModerationCycleProduct = Pick<Product, 'id' | 'title' | 'description'>;

// The vendor update endpoint starts a new moderation cycle only when these
// content fields change. Keep the ambiguity lock tied to that same boundary;
// generic updated_at changes (price, stock, category, etc.) are not enough.
const moderationCycleSignature = (product: Pick<Product, 'title' | 'description'>) => JSON.stringify([
  product.title,
  product.description ?? '',
]);

const hasCurrentModerationAmbiguity = (product: ModerationCycleProduct) => {
  try {
    const marker = sessionStorage.getItem(moderationAmbiguityKey(product.id));
    if (!marker) return false;
    const parsed = JSON.parse(marker) as { cycleSignature?: string };
    if (parsed.cycleSignature === moderationCycleSignature(product)) return true;
  } catch {
    // Treat malformed session state as stale and clear it below.
  }
  sessionStorage.removeItem(moderationAmbiguityKey(product.id));
  return false;
};

const saveModerationAmbiguity = (product: ModerationCycleProduct) => {
  sessionStorage.setItem(moderationAmbiguityKey(product.id), JSON.stringify({
    cycleSignature: moderationCycleSignature(product),
  }));
};

export default function AdminProductDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toasts, hideToast, error, success } = useToast();
  const { currentCurrency, setCurrency, exchangeRates } = useCurrencyStore();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isModerating, setIsModerating] = useState(false);
  const moderationBusy = useRef(false);
  const moderationDialog = useRef<HTMLDivElement>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [moderationAction, setModerationAction] = useState<'approve' | 'deny' | null>(null);
  const [approvalNotes, setApprovalNotes] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');
  const [rejectionNotes, setRejectionNotes] = useState('');
  const [moderationError, setModerationError] = useState<string | null>(null);
  const [moderationOutcomeUnknown, setModerationOutcomeUnknown] = useState(false);
  const [refreshError, setRefreshError] = useState<string | null>(null);

  const reconcileModeration = async (
    productId: string,
    action: 'approve' | 'deny',
    originalCycle: ModerationCycleProduct,
  ): Promise<{ product: Product | null; cycleChanged: boolean }> => {
    const expectedStatus = action === 'approve' ? 'approved' : 'rejected';
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const data = await adminService.getProduct(productId);
      setProduct(data);
      if (data.moderation_status === expectedStatus || data.moderation_status !== 'pending') {
        sessionStorage.removeItem(moderationAmbiguityKey(productId));
        return { product: data, cycleChanged: false };
      }
      if (moderationCycleSignature(data) !== moderationCycleSignature(originalCycle)) {
        sessionStorage.removeItem(moderationAmbiguityKey(productId));
        return { product: data, cycleChanged: true };
      }
      if (attempt < 2) await new Promise(resolve => setTimeout(resolve, 250));
    }
    saveModerationAmbiguity({ id: productId, title: originalCycle.title, description: originalCycle.description });
    return { product: null, cycleChanged: false };
  };

  const refreshProduct = async () => {
    if (!id) return;
    setIsRefreshing(true);
    try {
      const data = await adminService.getProduct(id);
      setProduct(data);
      setRefreshError(null);
      if (data.moderation_status !== 'pending') sessionStorage.removeItem(moderationAmbiguityKey(data.id));
      const ambiguityIsCurrent = data.moderation_status === 'pending' && hasCurrentModerationAmbiguity(data);
      if (moderationOutcomeUnknown && moderationAction && ambiguityIsCurrent) {
        const expectedStatus = moderationAction === 'approve' ? 'approved' : 'rejected';
        if (data.moderation_status === expectedStatus) {
          success(moderationAction === 'approve' ? 'Product approval verified.' : 'Product denial verified.', 'Moderation complete');
          setModerationOutcomeUnknown(false);
          setModerationError(null);
          setModerationAction(null);
          setApprovalNotes(''); setRejectionReason(''); setRejectionNotes('');
        } else if (data.moderation_status !== 'pending') {
          setModerationOutcomeUnknown(false);
          setModerationError('The moderation request was not confirmed. Review the current status before retrying.');
        } else {
          setModerationOutcomeUnknown(true);
          setModerationError('The moderation request is still pending. Refresh again before retrying.');
        }
      } else if (moderationOutcomeUnknown && moderationAction && !ambiguityIsCurrent) {
        setModerationOutcomeUnknown(false);
        setModerationError(null);
        setModerationAction(null);
        setApprovalNotes(''); setRejectionReason(''); setRejectionNotes('');
      } else if (moderationOutcomeUnknown && data.moderation_status !== 'pending') {
        sessionStorage.removeItem(moderationAmbiguityKey(data.id));
        setModerationOutcomeUnknown(false);
        setModerationError(null);
      } else if (moderationOutcomeUnknown && data.moderation_status === 'pending' && ambiguityIsCurrent) {
        setModerationError('The moderation request is still pending. Refresh again before retrying.');
      } else {
        setModerationOutcomeUnknown(false);
      }
    } catch (err: any) {
      const message = apiErrorMessage(err, 'Failed to refresh product. Please try again.');
      if (moderationOutcomeUnknown && !moderationAction) {
        setRefreshError(null);
        setModerationError(message);
      } else {
        setRefreshError(message);
        error(message, 'Refresh Failed');
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    if (!moderationAction) return;
    const opener = document.activeElement as HTMLElement | null;
    const dialog = moderationDialog.current;
    dialog?.querySelector<HTMLTextAreaElement>('textarea')?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !moderationBusy.current) {
        setModerationAction(null);
        setModerationError(null);
      }
      if (event.key !== 'Tab') return;
      const controls = Array.from(dialog?.querySelectorAll<HTMLElement>('textarea:not(:disabled), button:not(:disabled)') || []);
      const first = controls[0], last = controls[controls.length - 1];
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    dialog?.addEventListener('keydown', onKeyDown);
    return () => { dialog?.removeEventListener('keydown', onKeyDown); opener?.focus(); };
  }, [moderationAction]);

  useEffect(() => {
    const fetchProduct = async () => {
      if (!id) {
        error('Product ID is required', 'Error');
        navigate(ROUTES.ADMIN_PRODUCTS);
        return;
      }

      try {
        setLoading(true);
        setLoadError(null);
        const data = await adminService.getProduct(id);
        setProduct(data);
        if (data.moderation_status === 'pending' && hasCurrentModerationAmbiguity(data)) {
          setModerationOutcomeUnknown(true);
          setModerationError('A previous moderation request could not be confirmed. Refresh the product before retrying.');
        } else if (data.moderation_status !== 'pending') {
          sessionStorage.removeItem(moderationAmbiguityKey(data.id));
        }
      } catch (err: any) {
        console.error('Failed to load product', err);
        setLoadError(apiErrorMessage(err, 'Failed to load product. Please try again.'));
      } finally {
        setLoading(false);
      }
    };

    fetchProduct();
  }, [id, navigate, error]);

  const handleModeration = async () => {
    if (!product || !moderationAction || product.moderation_status !== 'pending' || moderationBusy.current || isRefreshing || refreshError || moderationOutcomeUnknown) return;
    if (moderationAction === 'deny' && rejectionReason.trim().length < 10) {
      setModerationError('Rejection reason must be at least 10 characters');
      return;
    }
    moderationBusy.current = true;
    try {
      setIsModerating(true);
      setModerationError(null);
      setModerationOutcomeUnknown(false);
      saveModerationAmbiguity(product);
      if (moderationAction === 'approve') {
        await adminService.approveProduct(product.id, approvalNotes.trim() || undefined);
      } else {
        await adminService.rejectProduct(product.id, rejectionReason.trim(), rejectionNotes.trim() || undefined);
      }
      sessionStorage.removeItem(moderationAmbiguityKey(product.id));
      success(moderationAction === 'approve' ? 'Product approved successfully.' : 'Product denied successfully.', 'Moderation complete');
      setModerationAction(null);
      setApprovalNotes(''); setRejectionReason(''); setRejectionNotes('');
      await refreshProduct();
    } catch (err: any) {
      const status = err?.response?.status;
      const outcomeMayBeCommitted = !err?.response || (typeof status === 'number' && status >= 500);
      if (!outcomeMayBeCommitted || !product || !moderationAction) {
        if (product) sessionStorage.removeItem(moderationAmbiguityKey(product.id));
        setModerationError(apiErrorMessage(err, 'Moderation action failed'));
      } else {
        setModerationOutcomeUnknown(true);
        setIsRefreshing(true);
        try {
          const reconciled = await reconcileModeration(product.id, moderationAction, product);
          setRefreshError(null);
          if (reconciled.product?.moderation_status === (moderationAction === 'approve' ? 'approved' : 'rejected')) {
            success(moderationAction === 'approve' ? 'Product approval verified.' : 'Product denial verified.', 'Moderation complete');
            setModerationOutcomeUnknown(false);
            setModerationError(null);
            setModerationAction(null);
            setApprovalNotes(''); setRejectionReason(''); setRejectionNotes('');
          } else if (reconciled.cycleChanged) {
            setModerationOutcomeUnknown(false);
            setModerationError(null);
            setModerationAction(null);
            setApprovalNotes(''); setRejectionReason(''); setRejectionNotes('');
          } else if (reconciled.product) {
            setModerationOutcomeUnknown(false);
            setModerationError('The moderation request was not confirmed. Review the current status before retrying.');
          } else {
            setModerationError('The moderation request is still pending. Refresh again before retrying.');
          }
        } catch (reconciliationError: any) {
          saveModerationAmbiguity(product);
          setModerationOutcomeUnknown(true);
          setModerationError(`The moderation outcome could not be confirmed. Refresh the product before retrying. ${apiErrorMessage(reconciliationError, 'Refresh failed')}`);
        } finally {
          setIsRefreshing(false);
        }
      }
    } finally {
      moderationBusy.current = false;
      setIsModerating(false);
    }
  };

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
      await adminService.deleteProduct(product.id);

      success('Product deleted successfully', 'Deleted');
      setDeleteModalOpen(false);

      // Navigate back to products list
      setTimeout(() => {
        navigate(ROUTES.ADMIN_PRODUCTS);
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex items-center justify-center">
        <div className="flex items-center gap-3 text-gray-600">
          <Loader2 className="h-6 w-6 animate-spin" />
          <span>Loading product details...</span>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <main className="min-h-screen bg-[var(--color-page-bg)] p-8">
        <h1 className="text-2xl font-semibold">Unable to load product</h1>
        <p role="alert" className="mt-4 text-red-700">{loadError}</p>
        <button type="button" onClick={() => navigate(ROUTES.ADMIN_PRODUCTS)} className="mt-6 rounded border px-4 py-2">
          Back to Products
        </button>
      </main>
    );
  }

  if (!product) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex items-center justify-center">
        <div className="text-center">
          <Package className="h-16 w-16 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-600">Product not found</p>
        </div>
      </div>
    );
  }

  const formatDisplayPrice = (amount?: number | null) => {
    const safeAmount = amount ?? 0;
    return formatPriceWithConversion(
      safeAmount,
      product.currency || 'NGN',
      currentCurrency,
      exchangeRates
    );
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)]">
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

          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-3xl font-bold text-gray-900">{product.title}</h1>
              <p className="text-sm text-gray-500 mt-1">
                Product ID: {product.id}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <CurrencySwitcher value={currentCurrency} onChange={setCurrency} />
              {product.moderation_status === 'pending' && !refreshError && (
                <>
                  <button type="button" onClick={() => setModerationAction('approve')} disabled={isModerating || isRefreshing || moderationOutcomeUnknown} className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"><CheckCircle className="h-4 w-4" />Approve Product</button>
                  <button type="button" onClick={() => setModerationAction('deny')} disabled={isModerating || isRefreshing || moderationOutcomeUnknown} className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"><XCircle className="h-4 w-4" />Deny Product</button>
                </>
              )}
              <button
                onClick={() => navigate(ROUTES.ADMIN_PRODUCT_EDIT.replace(':id', product.id))}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                <Edit2 className="h-4 w-4" />
                Edit Product
              </button>
              <button
                onClick={() => setDeleteModalOpen(true)}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
              >
                <Trash2 className="h-4 w-4" />
                Delete
              </button>
            </div>
          </div>
        </div>

        {refreshError && (
          <div role="alert" className="mb-6 rounded-lg border border-yellow-300 bg-yellow-50 p-4 text-yellow-900">
            <p>The moderation action succeeded, but the displayed product could not be refreshed. {refreshError}</p>
            <button type="button" disabled={isRefreshing} onClick={refreshProduct} className="mt-2 font-medium underline disabled:opacity-50">
              {isRefreshing ? 'Refreshing…' : 'Refresh product'}
            </button>
          </div>
        )}

        {moderationOutcomeUnknown && !moderationAction && (
          <div role="alert" className="mb-6 rounded-lg border border-yellow-300 bg-yellow-50 p-4 text-yellow-900">
            <p>{moderationError || 'A previous moderation request could not be confirmed. Refresh the product before retrying.'}</p>
            <button type="button" disabled={isRefreshing} onClick={refreshProduct} className="mt-2 font-medium underline disabled:opacity-50">
              {isRefreshing ? 'Refreshing…' : 'Refresh product status'}
            </button>
          </div>
        )}

        {/* Product Info Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Details */}
          <div className="lg:col-span-2 space-y-6">
            {/* Product Image */}
            <div className="bg-white rounded-xl shadow-sm overflow-hidden">
              <img
                src={
                  product.images?.[0]
                    ? typeof product.images[0] === 'string'
                      ? product.images[0]
                      : product.images[0].image_url || product.images[0].thumbnail_url
                    : '/images/placeholder-product.svg'
                }
                alt={product.title}
                className="w-full h-96 object-cover"
                onError={(e) => {
                  const target = e.target as HTMLImageElement;
                  target.src = '/images/placeholder-product.svg';
                }}
              />
              {product.images && product.images.length > 1 && (
                <div className="p-4 grid grid-cols-4 gap-2">
                  {product.images.slice(1, 5).map((img, idx) => (
                    <img
                      key={idx}
                      src={
                        typeof img === 'string'
                          ? img
                          : img.image_url || img.thumbnail_url || '/images/placeholder-product.svg'
                      }
                      alt={`${product.title} ${idx + 2}`}
                      className="w-full h-24 object-cover rounded-lg"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.src = '/images/placeholder-product.svg';
                      }}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Description */}
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-3">Description</h2>
              <p className="text-gray-600 whitespace-pre-wrap">{product.description}</p>
            </div>

            {/* Additional Details */}
            {product.fabric_composition && (
              <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-3">Fabric & Materials</h2>
                <p className="text-gray-600 whitespace-pre-wrap">{product.fabric_composition}</p>
              </div>
            )}

            {product.care_instructions && (
              <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-3">Care Instructions</h2>
                <p className="text-gray-600 whitespace-pre-wrap">{product.care_instructions}</p>
              </div>
            )}

            {product.made_to_order && (
              <div className="bg-white rounded-xl shadow-sm p-6 mb-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-3">Production</h2>
                <div className="flex items-center gap-2">
                  <span className="px-3 py-1 bg-blue-100 text-blue-800 text-xs font-semibold rounded-full">
                    MADE TO ORDER
                  </span>
                  {product.made_to_order_timeline && (
                    <span className="text-sm text-gray-600">{product.made_to_order_timeline}</span>
                  )}
                </div>
              </div>
            )}

            {/* Variations - Colors & Sizes */}
            {product.variations && product.variations.length > 0 && (
              <div className="bg-white rounded-xl shadow-sm p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Variations</h2>
                <div className="space-y-4">
                  {product.variations.map((variation: any, index: number) => (
                    <div key={variation.id || index} className="border border-gray-200 rounded-lg p-4">
                      {/* Variation Title */}
                      <div className="flex items-center justify-between mb-3">
                        <h3 className="font-medium text-gray-900">{variation.title}</h3>
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          variation.is_active
                            ? 'bg-green-100 text-green-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {variation.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </div>

                      {/* Color Swatch */}
                      {variation.color_hex && (
                        <div className="flex items-center gap-2 mb-3">
                          <span className="text-sm text-gray-500">Color:</span>
                          <div className="flex items-center gap-2">
                            <div
                              className="w-6 h-6 rounded border border-gray-300"
                              style={{ backgroundColor: variation.color_hex }}
                              title={variation.color_hex}
                            />
                            <span className="text-sm font-medium text-gray-700">{variation.color_hex}</span>
                          </div>
                        </div>
                      )}

                      {/* Size Stocks Table */}
                      {variation.size_stocks && variation.size_stocks.length > 0 && (
                        <div>
                          <p className="text-sm text-gray-500 mb-2">Available Sizes:</p>
                          <div className="overflow-x-auto">
                            <table className="min-w-full divide-y divide-gray-200">
                              <thead className="bg-gray-50">
                                <tr>
                                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Size</th>
                                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Stock</th>
                                  <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                                </tr>
                              </thead>
                              <tbody className="bg-white divide-y divide-gray-200">
                                {variation.size_stocks.map((sizeStock: any) => (
                                  <tr key={sizeStock.id}>
                                    <td className="px-3 py-2 whitespace-nowrap text-sm font-medium text-gray-900">
                                      {sizeStock.size}
                                    </td>
                                    <td className="px-3 py-2 whitespace-nowrap text-sm text-gray-700">
                                      {sizeStock.stock} units
                                    </td>
                                    <td className="px-3 py-2 whitespace-nowrap">
                                      {product.made_to_order ? (
                                        <span className="px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                          Made to Order
                                        </span>
                                      ) : (
                                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                                          sizeStock.stock > 0
                                            ? 'bg-green-100 text-green-800'
                                            : 'bg-red-100 text-red-800'
                                        }`}>
                                          {sizeStock.stock > 0 ? 'In Stock' : 'Out of Stock'}
                                        </span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </div>
                      )}

                      {/* Pricing Override (if set) */}
                      {(variation.price || variation.sale_price) && (
                        <div className="mt-3 pt-3 border-t border-gray-200">
                          <p className="text-sm text-gray-500 mb-1">Variation Pricing:</p>
                          <div className="flex items-center gap-3">
                            {variation.price && (
                              <span className="text-sm font-medium text-gray-900">
                                Price: {formatDisplayPrice(variation.price)}
                              </span>
                            )}
                            {variation.sale_price && (
                              <span className="text-sm font-medium text-green-600">
                                Sale: {formatDisplayPrice(variation.sale_price)}
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            {/* Status Card */}
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Status</h2>
              <div className="space-y-3">
                <div>
                  <span className="text-sm text-gray-500">Moderation Status</span>
                  <div className="mt-1">
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getStatusColor(product.moderation_status)}`}>
                      {product.moderation_status?.toUpperCase()}
                    </span>
                  </div>
                </div>
                <div>
                  <span className="text-sm text-gray-500">Product Status</span>
                  <div className="mt-1">
                    <span className={`px-3 py-1 rounded-full text-xs font-semibold ${getStatusColor(product.status)}`}>
                      {product.status?.toUpperCase()}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Pricing Card */}
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Pricing</h2>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Base Price</span>
                  <span className="text-lg font-bold text-gray-900">{formatDisplayPrice(product.base_price)}</span>
                </div>
                {product.compare_at_price && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm text-gray-500">Compare At</span>
                    <span className="text-sm text-gray-500 line-through">{formatDisplayPrice(product.compare_at_price)}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Inventory Card */}
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Inventory</h2>
              <div className="space-y-3">
                {product.made_to_order ? (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-500">Fulfillment</span>
                      <span className="text-sm font-medium text-blue-700">Made to Order</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-500">Production Timeline</span>
                      <span className="text-sm font-medium text-gray-900">{product.made_to_order_timeline || 'Not set'}</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-500">Total Stock</span>
                      <span className="text-sm font-medium text-gray-900">{product.total_stock || 0}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-gray-500">Inventory Quantity</span>
                      <span className="text-sm font-medium text-gray-900">{product.inventory_quantity || 0}</span>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Category Card */}
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Category & Organization</h2>
              <div className="space-y-3">
                <div>
                  <span className="text-xs text-gray-500 uppercase tracking-wide">Category</span>
                  <div className="flex items-center gap-2 mt-1">
                    <Tag className="h-4 w-4 text-gray-400" />
                    <span className="text-sm font-medium text-gray-900">
                      {product.category_name || 'Uncategorized'}
                    </span>
                  </div>
                </div>

                {product.collection_name && (
                  <div>
                    <span className="text-xs text-gray-500 uppercase tracking-wide">Collection</span>
                    <div className="flex items-center gap-2 mt-1">
                      <Package className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-900">{product.collection_name}</span>
                    </div>
                  </div>
                )}

                {product.size_guide?.gender && (
                  <div>
                    <span className="text-xs text-gray-500 uppercase tracking-wide">Gender</span>
                    <div className="flex items-center gap-2 mt-1">
                      <Package className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-900 capitalize">{product.size_guide.gender}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Dates Card */}
            <div className="bg-white rounded-xl shadow-sm p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Dates</h2>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Created</span>
                  <span className="text-sm text-gray-900">{formatDate(product.created_at)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-500">Updated</span>
                  <span className="text-sm text-gray-900">{formatDate(product.updated_at)}</span>
                </div>
              </div>
            </div>

            {/* Vendor Info */}
            {product.vendor_id && (
              <div className="bg-white rounded-xl shadow-sm p-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-4">Vendor</h2>
                <div className="space-y-2">
                  <div className="text-sm text-gray-500">Vendor ID</div>
                  <div className="text-sm font-medium text-gray-900">{product.vendor_id}</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {moderationAction && (
        <div className="fixed inset-0 z-50 overflow-y-auto bg-black/50 p-4" ref={moderationDialog} role="dialog" aria-modal="true" aria-labelledby="moderation-title">
          <div className="mx-auto mt-16 w-full max-w-lg rounded-lg bg-white p-6 space-y-4">
            <h3 id="moderation-title" className="text-lg font-semibold">{moderationAction === 'approve' ? 'Approve Product' : 'Deny Product'}</h3>
            {moderationAction === 'approve' ? <>
              <p>Approve “{product.title}”? The vendor will be notified.</p>
              <label className="block text-sm font-medium">Approval Notes (Optional)<textarea disabled={isModerating || isRefreshing} aria-label="Approval Notes (Optional)" value={approvalNotes} onChange={e => setApprovalNotes(e.target.value)} maxLength={500} rows={3} className="mt-1 w-full rounded border p-2" /></label>
            </> : <>
              <p>Deny “{product.title}”? The vendor will be notified.</p>
              <label className="block text-sm font-medium">Rejection Reason *<textarea disabled={isModerating || isRefreshing} aria-label="Rejection Reason *" value={rejectionReason} onChange={e => setRejectionReason(e.target.value)} maxLength={1000} rows={3} className="mt-1 w-full rounded border p-2" /></label>
              <label className="block text-sm font-medium">Rejection Notes (Optional)<textarea disabled={isModerating || isRefreshing} aria-label="Rejection Notes (Optional)" value={rejectionNotes} onChange={e => setRejectionNotes(e.target.value)} maxLength={500} rows={3} className="mt-1 w-full rounded border p-2" /></label>
            </>}
            {moderationError && <p role="alert" className="text-sm text-red-700">{moderationError}</p>}
            {moderationOutcomeUnknown && <button type="button" onClick={refreshProduct} disabled={isRefreshing} className="text-sm font-medium underline disabled:opacity-50">{isRefreshing ? 'Refreshing…' : 'Refresh product status'}</button>}
            <div className="flex justify-end gap-3"><button type="button" onClick={() => { setModerationAction(null); setModerationError(null); }} disabled={isModerating || isRefreshing} className="rounded border px-4 py-2">Cancel</button><button type="button" onClick={handleModeration} disabled={isModerating || isRefreshing || moderationOutcomeUnknown} className="rounded bg-blue-600 px-4 py-2 text-white disabled:opacity-50">{isModerating ? 'Processing…' : moderationOutcomeUnknown ? 'Refresh required' : moderationAction === 'approve' ? 'Approve Product' : 'Deny Product'}</button></div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteModalOpen && (
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
                  Are you sure you want to delete <strong>"{product.title}"</strong>? This action will permanently remove the product from the marketplace.
                </p>
              </div>
            </div>

            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
              <p className="text-sm text-red-800">
                <strong>Warning:</strong> This action cannot be undone.
              </p>
            </div>

            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDeleteModalOpen(false)}
                disabled={isDeleting}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeleteConfirm}
                disabled={isDeleting}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-50"
              >
                {isDeleting ? 'Deleting...' : 'Delete Product'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ToastContainer toasts={toasts} onClose={hideToast} />
    </div>
  );
}
