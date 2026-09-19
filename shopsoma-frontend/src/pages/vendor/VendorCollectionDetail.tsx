import { Edit2, Filter, Search, Upload, X, Eye } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { collectionService } from '../../services/collectionService';
import { productService } from '../../services/productService';
import { useVendor } from '../../context/VendorContext';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion } from '../../utils/pricing';
import type { CollectionDetail, CollectionProductSummary, Product } from '../../types';

const fallbackImage = '/images/placeholder-product.svg';

const buildStatusBadge = (status: 'Live' | 'Archived') => {
  const className =
    status === 'Live'
      ? 'bg-emerald-50 text-emerald-700'
      : 'bg-gray-100 text-gray-500';
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-semibold ${className}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70"></span>
      {status}
    </span>
  );
};

const getFulfillmentStatus = (product: CollectionProductSummary) => {
  if (product.made_to_order) {
    return {
      label: 'Made to Order',
      detail: product.made_to_order_timeline
        ? `Made to Order • ${product.made_to_order_timeline}`
        : 'Made to Order',
      className: 'bg-sky-50 text-sky-700',
    };
  }

  if (product.total_stock <= 0) {
    return {
      label: 'Out of Stock',
      detail: 'Out of Stock',
      className: 'bg-gray-100 text-gray-600',
    };
  }

  if (product.total_stock <= 5) {
    return {
      label: 'Low Stock',
      detail: `Low Stock • ${product.total_stock} left`,
      className: 'bg-emerald-50 text-emerald-700',
    };
  }

  return {
    label: 'Ready to Ship',
    detail: `${product.total_stock} In Stock`,
    className: 'bg-gray-100 text-gray-600',
  };
};

export default function VendorCollectionDetail() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [collection, setCollection] = useState<CollectionDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [heroImage, setHeroImage] = useState(fallbackImage);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showBannerModal, setShowBannerModal] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [isUploadingBanner, setIsUploadingBanner] = useState(false);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [isSavingProducts, setIsSavingProducts] = useState(false);
  const bannerInputRef = useRef<HTMLInputElement>(null);
  const [products, setProducts] = useState<CollectionProductSummary[]>([]);
  const [productsMeta, setProductsMeta] = useState({ total: 0, page: 1, total_pages: 1 });
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 6;
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedProducts, setSelectedProducts] = useState<Set<string>>(new Set());
  const [modalSearch, setModalSearch] = useState('');
  const [modalPage, setModalPage] = useState(1);
  const [modalProducts, setModalProducts] = useState<CollectionProductSummary[]>([]);
  const [isModalLoading, setIsModalLoading] = useState(false);
  const { toasts, hideToast, success, error: showError } = useToast();
  const { vendorProfile } = useVendor();
  const { currentCurrency, setCurrency, exchangeRates, fetchExchangeRate } = useCurrencyStore();

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  const getProductRouteId = (product: CollectionProductSummary) =>
    product.id || (product as unknown as { product_id?: string }).product_id;

  const mapProductToSummary = (product: Product): CollectionProductSummary => {
    const primaryImage = product.images?.find((img) => img.is_primary) || product.images?.[0];
    return {
      id: product.id,
      title: product.title,
      status: product.status,
      base_price: product.base_price,
      total_stock: product.total_stock || 0,
      made_to_order: product.made_to_order,
      made_to_order_timeline: product.made_to_order_timeline,
      created_at: product.created_at,
      image_url: primaryImage?.thumbnail_url || primaryImage?.image_url || null,
      collection_name: product.collection_name || null,
    };
  };

  const formatDisplayPrice = (amount: number, currency?: Product['currency']) => {
    return formatPriceWithConversion(
      amount,
      currency || 'NGN',
      currentCurrency,
      exchangeRates
    );
  };

  useEffect(() => {
    const fetchCollection = async () => {
      if (!id) return;
      setIsLoading(true);
      try {
        const detail = await collectionService.getCollection(id);
        setCollection(detail);
        setHeroImage(detail.banner_image_url || detail.thumbnails?.[0] || fallbackImage);
        setEditName(detail.name);
        setEditDescription(detail.description || '');
      } catch (error) {
        setCollection(null);
        setHeroImage(fallbackImage);
      } finally {
        setIsLoading(false);
      }
    };
    fetchCollection();
  }, [id]);

  useEffect(() => {
    const fetchProducts = async () => {
      if (!id) return;
      try {
        const response = await collectionService.getCollectionProducts(id, {
          page: currentPage,
          page_size: pageSize,
        });
        setProducts(response.items);
        setProductsMeta({ total: response.total, page: response.page, total_pages: response.total_pages });
      } catch (error) {
        setProducts([]);
        setProductsMeta({ total: 0, page: 1, total_pages: 1 });
      }
    };
    fetchProducts();
  }, [id, currentPage]);

  useEffect(() => {
    const fetchAvailableProducts = async () => {
      if (!id || !showAddModal) return;
      setIsModalLoading(true);
      try {
        const response = await collectionService.getAvailableCollectionProducts(id, {
          page: modalPage,
          page_size: 10,
          search: modalSearch || undefined,
        });
        if (response.items.length > 0) {
          setModalProducts(response.items);
          return;
        }

        if (vendorProfile?.id) {
          const fallback = await productService.getVendorProducts(vendorProfile.id, {
            page: modalPage,
            page_size: 10,
            sort_by: 'created_at',
            sort_order: 'desc',
            search: modalSearch || undefined,
          });
          const unassigned = fallback.products.filter((product) => !product.collection_id);
          const mapped = unassigned.map(mapProductToSummary);
          setModalProducts(mapped);
        } else {
          setModalProducts([]);
        }
      } catch (error) {
        setModalProducts([]);
      } finally {
        setIsModalLoading(false);
      }
    };
    fetchAvailableProducts();
  }, [id, modalPage, modalSearch, showAddModal, vendorProfile?.id]);

  const totalPages = Math.max(1, productsMeta.total_pages);
  const pagedProducts = products;

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(1);
    }
  }, [currentPage, totalPages]);

  const handleBannerSelect = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!id) return;
    const file = event.target.files?.[0];
    if (!file) return;
    setIsUploadingBanner(true);
    try {
      const upload = await productService.uploadImage(file, 'collections', true);
      const updated = await collectionService.updateCollection(id, {
        banner_image_url: upload.original,
      });
      setCollection((prev) =>
        prev
          ? {
              ...prev,
              banner_image_url: updated.banner_image_url,
            }
          : prev
      );
      setHeroImage(upload.original);
      success('Banner image updated.');
      setShowBannerModal(false);
    } catch (error) {
      showError('Failed to update banner image.');
    } finally {
      setIsUploadingBanner(false);
      if (bannerInputRef.current) {
        bannerInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="flex min-h-screen bg-[var(--color-page-bg)]">
      <VendorSidebar activePrimary="collections" />
      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900">Collection Manager</h1>
              <p className="text-sm text-gray-500">Keep your collection details on point.</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search"
                  className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent w-64"
                />
              </div>
              <CurrencySwitcher value={currentCurrency} onChange={setCurrency} />
              <button
                type="button"
                className="h-10 w-10 rounded-lg border border-gray-200 flex items-center justify-center hover:bg-gray-50"
                aria-label="Filter collections"
              >
                <Filter className="h-4 w-4 text-gray-600" />
              </button>
              <button
                type="button"
                className="h-10 w-10 rounded-lg border border-gray-200 flex items-center justify-center hover:bg-gray-50"
                aria-label="Export"
              >
                <Upload className="h-4 w-4 text-gray-600" />
              </button>
            </div>
          </div>

          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
            {isLoading ? (
              <div className="animate-pulse">
                <div className="h-64 md:h-72 bg-gray-100" />
                <div className="p-6 space-y-4">
                  <div className="flex items-center justify-between flex-wrap gap-4">
                    <div className="space-y-2">
                      <div className="h-5 w-20 rounded-full bg-gray-100" />
                      <div className="h-6 w-64 rounded bg-gray-100" />
                    </div>
                    <div className="flex items-center gap-10">
                      <div className="space-y-2">
                        <div className="h-3 w-24 rounded bg-gray-100" />
                        <div className="h-4 w-20 rounded bg-gray-100" />
                      </div>
                      <div className="space-y-2">
                        <div className="h-3 w-28 rounded bg-gray-100" />
                        <div className="h-4 w-12 rounded bg-gray-100" />
                      </div>
                    </div>
                  </div>
                  <div>
                    <div className="h-4 w-40 rounded bg-gray-100" />
                    <div className="mt-2 h-20 rounded-lg bg-gray-100" />
                  </div>
                </div>
              </div>
            ) : (
              <>
                <div className="relative h-64 md:h-72">
                  <img
                    src={heroImage}
                    alt={collection?.name || 'Collection'}
                    className="h-full w-full object-cover"
                  />
                  <button
                    type="button"
                    className="absolute bottom-4 right-4 inline-flex items-center gap-2 rounded-full bg-white/90 px-4 py-2 text-sm font-semibold text-gray-700 shadow-sm hover:bg-white disabled:opacity-60"
                    onClick={() => setShowBannerModal(true)}
                    disabled={isUploadingBanner}
                  >
                    <Edit2 className="h-4 w-4" />
                    {isUploadingBanner ? 'Uploading...' : 'Edit Image'}
                  </button>
                </div>
                <div className="p-6 space-y-4">
                  <div className="flex items-center justify-between flex-wrap gap-4">
                    <div>
                      {buildStatusBadge(collection?.is_active ? 'Live' : 'Archived')}
                      <div className="mt-2 flex items-center gap-2">
                        <h2 className="text-xl font-semibold text-gray-900">{collection?.name || 'Collection'}</h2>
                        <button
                          type="button"
                          className="text-gray-400 hover:text-gray-600"
                          aria-label="Edit collection details"
                          onClick={() => setShowEditModal(true)}
                        >
                          <Edit2 className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center gap-10 text-sm text-gray-500">
                      <div>
                        <span className="block text-xs uppercase tracking-wide text-gray-400">Date Created</span>
                        <span className="font-semibold text-gray-700">
                          {collection?.created_at
                            ? new Date(collection.created_at).toLocaleDateString('en-GB')
                            : '—'}
                        </span>
                      </div>
                      <div>
                        <span className="block text-xs uppercase tracking-wide text-gray-400">Products Available</span>
                        <span className="font-semibold text-gray-700">{collection?.products_available || 0}</span>
                      </div>
                    </div>
                  </div>

                  <div>
                    <p className="text-sm text-gray-500">Collection Description</p>
                    <div className="mt-2 border border-gray-200 rounded-lg p-4 text-sm text-gray-600">
                      {collection?.description || '—'}
                    </div>
                  </div>
                </div>
              </>
            )}
          </section>

          <section className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">List of Products</h3>
                <p className="text-xs text-gray-500 mt-1">Archived products are hidden from this list.</p>
              </div>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                onClick={() => setShowAddModal(true)}
              >
                <Edit2 className="h-4 w-4" />
                Add Product
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500">
                    <th className="py-3 px-4 font-medium">Product Name</th>
                    <th className="py-3 px-4 font-medium">Status</th>
                    <th className="py-3 px-4 font-medium">Price</th>
                    <th className="py-3 px-4 font-medium">Fulfillment</th>
                    <th className="py-3 px-4 font-medium">Date Created</th>
                    <th className="py-3 px-4 font-medium text-right"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {pagedProducts.map((product) => {
                    const fulfillment = getFulfillmentStatus(product);
                    return (
                    <tr key={product.id} className="hover:bg-gray-50">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-3">
                          <img
                            src={product.image_url || fallbackImage}
                            alt={product.title}
                            className="h-10 w-10 rounded-lg border border-gray-200 object-cover"
                          />
                          <span className="text-gray-800">{product.title}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span
                          className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${fulfillment.className}`}
                        >
                          {fulfillment.label}
                        </span>
                      </td>
                      <td className="py-3 px-4 font-semibold text-gray-800">
                        {formatDisplayPrice(product.base_price)}
                      </td>
                      <td className={`py-3 px-4 font-semibold ${product.made_to_order ? 'text-sky-700' : 'text-emerald-700'}`}>{fulfillment.detail}</td>
                      <td className="py-3 px-4 text-gray-600">
                        {new Date(product.created_at).toLocaleDateString('en-GB')}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-3">
                          <button
                            type="button"
                            className="inline-flex items-center gap-2 text-sm font-semibold text-gray-600 hover:text-gray-900"
                            aria-label="View product"
                            onClick={() => {
                              const targetId = getProductRouteId(product);
                              if (!targetId) {
                                showError('Unable to open product details.');
                                return;
                              }
                              navigate(`/vendor/products/${String(targetId)}/view`);
                            }}
                          >
                            <Eye className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            className="inline-flex items-center gap-2 text-sm font-semibold text-gray-600 hover:text-gray-900"
                            aria-label="Edit product"
                            onClick={() => {
                              const targetId = getProductRouteId(product);
                              if (!targetId) {
                                showError('Unable to open product editor.');
                                return;
                              }
                              navigate(`/vendor/products/${String(targetId)}/edit`);
                            }}
                          >
                            <Edit2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )})}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between pt-4 text-sm text-gray-500">
              <span>
                Page {currentPage} of {totalPages}
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded-full border border-gray-200 px-3 py-1 text-sm font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                  onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                  disabled={currentPage === 1}
                >
                  Prev
                </button>
                <button
                  type="button"
                  className="rounded-full border border-gray-200 px-3 py-1 text-sm font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-50"
                  onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-4xl rounded-2xl bg-white shadow-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-50"
                  onClick={() => setShowAddModal(false)}
                  aria-label="Close modal"
                >
                  <X className="h-4 w-4 text-gray-600" />
                </button>
                <h4 className="text-lg font-semibold text-gray-900">Add Item to Collection</h4>
              </div>
              <div className="flex items-center gap-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    type="text"
                    placeholder="Search"
                    value={modalSearch}
                    onChange={(event) => setModalSearch(event.target.value)}
                    className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent w-64"
                  />
                </div>
                <button
                  type="button"
                  className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                >
                  <Filter className="h-4 w-4" />
                  Filter
                </button>
              </div>
            </div>

            <div className="max-h-[420px] overflow-y-auto px-6 py-4">
              <div className="space-y-2">
                {isModalLoading
                  ? Array.from({ length: 6 }).map((_, index) => (
                      <div
                        key={`modal-skeleton-${index}`}
                        className="flex items-center gap-4 rounded-xl border border-gray-100 px-4 py-3 animate-pulse"
                      >
                        <div className="h-4 w-4 rounded border border-gray-200 bg-gray-100" />
                        <div className="h-10 w-10 rounded-lg bg-gray-100" />
                        <div className="h-4 flex-1 rounded bg-gray-100" />
                        <div className="h-5 w-20 rounded-full bg-gray-100" />
                        <div className="h-4 w-12 rounded bg-gray-100" />
                        <div className="h-4 w-16 rounded bg-gray-100" />
                        <div className="h-4 w-16 rounded bg-gray-100" />
                      </div>
                    ))
                  : modalProducts.map((product) => {
                      const checked = selectedProducts.has(product.id);
                      const fulfillment = getFulfillmentStatus(product);
                      const collectionLabel = product.collection_name || 'Uncategorized';
                      const collectionClass = product.collection_name
                        ? 'bg-gray-100 text-gray-600'
                        : 'bg-amber-50 text-amber-700';
                      return (
                        <label
                          key={product.id}
                          className="flex items-center gap-4 rounded-xl border border-gray-100 px-4 py-3 hover:bg-gray-50 cursor-pointer"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(event) => {
                              const next = new Set(selectedProducts);
                              if (event.target.checked) {
                                next.add(product.id);
                              } else {
                                next.delete(product.id);
                              }
                              setSelectedProducts(next);
                            }}
                            className="h-4 w-4 rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                            style={{ accentColor: '#105E53' }}
                          />
                          <img
                            src={product.image_url || fallbackImage}
                            alt={product.title}
                            className="h-10 w-10 rounded-lg border border-gray-200 object-cover"
                          />
                          <div className="flex-1 text-sm text-gray-800">
                            <div className="font-medium text-gray-900">{product.title}</div>
                            <span className={`mt-1 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${collectionClass}`}>
                              {collectionLabel}
                            </span>
                          </div>
                          <span
                            className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${fulfillment.className}`}
                          >
                            {fulfillment.label}
                          </span>
                          <span className="text-sm font-semibold text-gray-800">
                            {formatDisplayPrice(product.base_price)}
                          </span>
                          <span className={`text-sm font-semibold ${product.made_to_order ? 'text-sky-700' : 'text-emerald-700'}`}>
                            {fulfillment.detail}
                          </span>
                          <span className="text-sm text-gray-500">
                            {new Date(product.created_at).toLocaleDateString('en-GB')}
                          </span>
                        </label>
                      );
                    })}
              </div>
            </div>

            <div className="px-6 py-4 border-t border-gray-100">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-500">
                  {selectedProducts.size} products selected
                </span>
                <button
                  type="button"
                  className="w-full max-w-md ml-auto inline-flex items-center justify-center gap-2 rounded-full bg-[#105E53] px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-[#0c4c45] disabled:opacity-70"
                  onClick={async () => {
                    if (!id || selectedProducts.size === 0) {
                      setShowAddModal(false);
                      return;
                    }
                    setIsSavingProducts(true);
                    await collectionService.addProductsToCollection(id, Array.from(selectedProducts));
                    setSelectedProducts(new Set());
                    setShowAddModal(false);
                    setModalPage(1);
                    const response = await collectionService.getCollectionProducts(id, {
                      page: currentPage,
                      page_size: pageSize,
                    });
                    setProducts(response.items);
                    setProductsMeta({ total: response.total, page: response.page, total_pages: response.total_pages });
                    success('Products added to collection.');
                    setIsSavingProducts(false);
                  }}
                  disabled={isSavingProducts}
                >
                  {isSavingProducts ? (
                    <>
                      <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                      Saving...
                    </>
                  ) : (
                    'Save Changes'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {showBannerModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md rounded-2xl bg-white shadow-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h4 className="text-lg font-semibold text-gray-900">Upload Banner Image</h4>
              <button
                type="button"
                className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-50"
                onClick={() => setShowBannerModal(false)}
                aria-label="Close modal"
              >
                <X className="h-4 w-4 text-gray-600" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4 text-sm text-gray-600">
              <p>
                For the best fit in the banner, use a wide image with a 3:1 ratio.
              </p>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 space-y-1">
                <p className="text-sm font-semibold text-gray-800">Recommended size</p>
                <p className="text-sm text-gray-600">1600 x 600 px (minimum 1200 x 450 px)</p>
                <p className="text-xs text-gray-500">JPG or PNG, up to 10MB.</p>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3">
              <button
                type="button"
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-50"
                onClick={() => setShowBannerModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-[#105E53] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0c4c45] inline-flex items-center gap-2 disabled:opacity-70"
                onClick={() => bannerInputRef.current?.click()}
                disabled={isUploadingBanner}
              >
                {isUploadingBanner ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Uploading...
                  </>
                ) : (
                  'Choose Image'
                )}
              </button>
              <input
                ref={bannerInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleBannerSelect}
              />
            </div>
          </div>
        </div>
      )}
      {showEditModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h4 className="text-lg font-semibold text-gray-900">Edit Collection</h4>
              <button
                type="button"
                className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-50"
                onClick={() => setShowEditModal(false)}
                aria-label="Close modal"
              >
                <X className="h-4 w-4 text-gray-600" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <label className="block text-sm text-gray-600">
                Collection Name
                <input
                  type="text"
                  value={editName}
                  onChange={(event) => setEditName(event.target.value)}
                  className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
                />
              </label>
              <label className="block text-sm text-gray-600">
                Description
                <textarea
                  value={editDescription}
                  onChange={(event) => setEditDescription(event.target.value)}
                  rows={4}
                  className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
                />
              </label>
            </div>
            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3">
              <button
                type="button"
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-50"
                onClick={() => setShowEditModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-[#105E53] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0c4c45] inline-flex items-center gap-2 disabled:opacity-70"
                onClick={async () => {
                  if (!id) return;
                  setIsSavingEdit(true);
                  const updated = await collectionService.updateCollection(id, {
                    name: editName.trim(),
                    description: editDescription.trim() || undefined,
                  });
                  setCollection((prev) =>
                    prev
                      ? { ...prev, name: updated.name, description: updated.description, banner_image_url: updated.banner_image_url }
                      : prev
                  );
                  if (updated.banner_image_url) {
                    setHeroImage(updated.banner_image_url);
                  }
                  success('Collection details updated.');
                  setShowEditModal(false);
                  setIsSavingEdit(false);
                }}
                disabled={isSavingEdit}
              >
                {isSavingEdit ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Saving...
                  </>
                ) : (
                  'Save Changes'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
      <ToastContainer toasts={toasts} onClose={hideToast} />
    </div>
  );
}
