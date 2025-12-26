import { Filter, Search, Upload, MoreHorizontal, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { productService } from '../../services/productService';
import { useVendor } from '../../context/VendorContext';
import { collectionService } from '../../services/collectionService';
import CurrencySwitcher from '../../components/common/CurrencySwitcher';
import { useCurrencyStore } from '../../store/currencyStore';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';
import type { CollectionSummary } from '../../types';

type CollectionCard = {
  id: string;
  name: string;
  status: 'Live' | 'Archived';
  is_active?: boolean;
  dateCreated: string;
  productsAvailable: number;
  imageUrl: string;
  thumbnails: string[];
};

const fallbackImage = '/images/placeholder-product.svg';

const fallbackCollections: CollectionCard[] = [
  {
    id: 'latest-collection',
    name: "S/S 2025: A Summer Forgotten at Dawn",
    status: 'Live',
    dateCreated: '24/06/2024',
    productsAvailable: 18,
    imageUrl: fallbackImage,
    thumbnails: [fallbackImage, fallbackImage, fallbackImage],
  },
];

const buildStatusBadge = (status: CollectionCard['status']) => {
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

export default function VendorCollections() {
  const { vendorProfile } = useVendor();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [imagePool, setImagePool] = useState<string[]>([]);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [collections, setCollections] = useState<CollectionCard[]>(fallbackCollections);
  const [loadingCollections, setLoadingCollections] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState('');
  const [newCollectionDescription, setNewCollectionDescription] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const { toasts, hideToast, success, error } = useToast();
  const { currentCurrency, setCurrency, fetchExchangeRate } = useCurrencyStore();

  useEffect(() => {
    fetchExchangeRate();
  }, [fetchExchangeRate]);

  useEffect(() => {
    const fetchImages = async () => {
      if (!vendorProfile?.id) return;
      try {
        const response = await productService.getVendorProducts(vendorProfile.id, {
          page_size: 8,
          sort_by: 'created_at',
          sort_order: 'desc',
        });
        const images = response.products
          .map((product) => product.images?.find((img) => img.is_primary)?.image_url || product.images?.[0]?.image_url)
          .filter((value): value is string => Boolean(value));
        setImagePool(images.length ? images : [fallbackImage]);
      } catch (error) {
        setImagePool([fallbackImage]);
      }
    };
    fetchImages();
  }, [vendorProfile?.id]);

  const mappedCollections = useMemo(() => {
    const pool = imagePool.length ? imagePool : [fallbackImage];
    return collections.map((collection, index) => ({
      ...collection,
      imageUrl: collection.imageUrl || pool[index % pool.length],
      thumbnails: collection.thumbnails?.length ? collection.thumbnails : pool.slice(0, 3),
    }));
  }, [collections, imagePool]);

  const filteredCollections = useMemo(() => {
    if (!search.trim()) return mappedCollections;
    const query = search.toLowerCase();
    return mappedCollections.filter((collection) => collection.name.toLowerCase().includes(query));
  }, [mappedCollections, search]);

  const latestCollection = filteredCollections[0];
  const otherCollections = filteredCollections.slice(1);
  const latestThumbnails = latestCollection?.thumbnails?.length
    ? latestCollection.thumbnails
    : filteredCollections.slice(0, 3).map((item) => item.imageUrl);

  useEffect(() => {
    const fetchCollections = async () => {
      try {
        setLoadingCollections(true);
      const response = await collectionService.getCollections(true);
      if (response.length) {
        const mapped = response.map((collection: CollectionSummary) => {
          const status: CollectionCard['status'] = collection.is_active ? 'Live' : 'Archived';
          return {
            id: collection.id,
            name: collection.name,
            status,
          is_active: collection.is_active,
          dateCreated: new Date(collection.created_at).toLocaleDateString('en-GB'),
          productsAvailable: collection.products_available || 0,
          imageUrl: collection.banner_image_url || collection.thumbnails?.[0] || '',
          thumbnails: collection.thumbnails || [],
          };
        });
        setCollections(mapped);
        }
      } catch (error) {
        setCollections(fallbackCollections);
      } finally {
        setLoadingCollections(false);
      }
    };
    fetchCollections();
  }, []);

  return (
    <div className="flex min-h-screen bg-[var(--color-page-bg)]">
      <ToastContainer toasts={toasts} onClose={hideToast} />
      <VendorSidebar activePrimary="collections" />
      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-semibold text-gray-900">Collection Manager</h1>
              <p className="text-sm text-gray-500">Curate and organize your seasonal drops</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
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

          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Latest Collection</h2>
            </div>
            {loadingCollections && (
              <div className="rounded-2xl border border-gray-200 bg-white p-6 text-sm text-gray-500">
                Loading collections...
              </div>
            )}
            {!loadingCollections && latestCollection && (
              <div
                className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden cursor-pointer hover:-translate-y-0.5 hover:shadow-md transition"
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/vendor/collections/${latestCollection.id}`)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    navigate(`/vendor/collections/${latestCollection.id}`);
                  }
                }}
              >
                <div className="relative h-64 md:h-72">
                  <img
                    src={latestCollection.imageUrl}
                    alt={latestCollection.name}
                    className="h-full w-full object-cover"
                  />
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setOpenMenuId((prev) => (prev === latestCollection.id ? null : latestCollection.id));
                    }}
                    className="absolute top-3 right-3 h-9 w-9 rounded-full bg-white/90 border border-gray-200 flex items-center justify-center text-gray-600 hover:text-gray-900"
                    aria-label="Collection options"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                  {openMenuId === latestCollection.id && (
                    <div
                      className="absolute top-14 right-3 w-44 rounded-xl border border-gray-200 bg-white shadow-lg overflow-hidden text-sm text-gray-700"
                      onClick={(event) => event.stopPropagation()}
                    >
                      {latestCollection.is_active ? (
                        <button
                          type="button"
                          className="w-full px-4 py-2 text-left hover:bg-gray-50"
                          onClick={async () => {
                            try {
                              await collectionService.updateCollection(latestCollection.id, { is_active: false });
                              setCollections((prev) =>
                                prev.map((item) =>
                                  item.id === latestCollection.id
                                    ? { ...item, status: 'Archived', is_active: false }
                                    : item
                                )
                              );
                              success('Collection archived.');
                            } catch (archiveError: any) {
                              error(archiveError?.response?.data?.detail || 'Failed to archive collection.');
                            } finally {
                              setOpenMenuId(null);
                            }
                          }}
                        >
                          Archive Collection
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="w-full px-4 py-2 text-left hover:bg-gray-50"
                          onClick={async () => {
                            try {
                              await collectionService.updateCollection(latestCollection.id, { is_active: true });
                              setCollections((prev) =>
                                prev.map((item) =>
                                  item.id === latestCollection.id
                                    ? { ...item, status: 'Live', is_active: true }
                                    : item
                                )
                              );
                              success('Collection restored.');
                            } catch (restoreError: any) {
                              error(restoreError?.response?.data?.detail || 'Failed to restore collection.');
                            } finally {
                              setOpenMenuId(null);
                            }
                          }}
                        >
                          Restore Collection
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <div className="p-6 flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    {buildStatusBadge(latestCollection.status)}
                    <span className="text-left text-lg font-semibold text-gray-900">
                      {latestCollection.name}
                    </span>
                  </div>
                  <div className="ml-auto flex items-center gap-8 text-sm text-gray-500">
                    <div className="flex items-center -space-x-2">
                      {latestThumbnails?.map((thumbnail, index) => (
                        <img
                          key={`${latestCollection.id}-thumb-${index}`}
                          src={thumbnail}
                          alt={`${latestCollection.name} preview ${index + 1}`}
                          className="h-10 w-10 rounded-full border-2 border-white object-cover shadow-sm"
                        />
                      ))}
                    </div>
                    <div>
                      <span className="block text-xs uppercase tracking-wide text-gray-400">Date Created</span>
                      <span className="font-semibold text-gray-700">{latestCollection.dateCreated}</span>
                    </div>
                    <div>
                      <span className="block text-xs uppercase tracking-wide text-gray-400">Products Available</span>
                      <span className="font-semibold text-gray-700">{latestCollection.productsAvailable}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </section>

          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Other Collections</h2>
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                onClick={() => setShowCreateModal(true)}
              >
                + Create New Collection
              </button>
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              {otherCollections.map((collection) => (
                <button
                  key={collection.id}
                  type="button"
                  onClick={() => navigate(`/vendor/collections/${collection.id}`)}
                  className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden text-left hover:-translate-y-0.5 hover:shadow-md transition"
                >
                  <div className="relative h-48">
                    <img
                      src={collection.imageUrl}
                      alt={collection.name}
                      className="h-full w-full object-cover"
                    />
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpenMenuId((prev) => (prev === collection.id ? null : collection.id));
                      }}
                      className="absolute top-3 right-3 h-9 w-9 rounded-full bg-white/90 border border-gray-200 flex items-center justify-center text-gray-600 hover:text-gray-900"
                      aria-label="Collection options"
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </button>
                    {openMenuId === collection.id && (
                      <div
                        className="absolute top-14 right-3 w-44 rounded-xl border border-gray-200 bg-white shadow-lg overflow-hidden text-sm text-gray-700"
                        onClick={(event) => event.stopPropagation()}
                      >
                        {collection.is_active ? (
                          <button
                            type="button"
                            className="w-full px-4 py-2 text-left hover:bg-gray-50"
                            onClick={async () => {
                              try {
                                await collectionService.updateCollection(collection.id, { is_active: false });
                                setCollections((prev) =>
                                  prev.map((item) =>
                                    item.id === collection.id
                                      ? { ...item, status: 'Archived', is_active: false }
                                      : item
                                  )
                                );
                                success('Collection archived.');
                              } catch (archiveError: any) {
                                error(archiveError?.response?.data?.detail || 'Failed to archive collection.');
                              } finally {
                                setOpenMenuId(null);
                              }
                            }}
                          >
                            Archive Collection
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="w-full px-4 py-2 text-left hover:bg-gray-50"
                            onClick={async () => {
                              try {
                                await collectionService.updateCollection(collection.id, { is_active: true });
                                setCollections((prev) =>
                                  prev.map((item) =>
                                    item.id === collection.id
                                      ? { ...item, status: 'Live', is_active: true }
                                      : item
                                  )
                                );
                                success('Collection restored.');
                              } catch (restoreError: any) {
                                error(restoreError?.response?.data?.detail || 'Failed to restore collection.');
                              } finally {
                                setOpenMenuId(null);
                              }
                            }}
                          >
                            Restore Collection
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="p-5 space-y-2">
                    {buildStatusBadge(collection.status)}
                    <h3 className="text-lg font-semibold text-gray-900">{collection.name}</h3>
                    <div className="flex items-center justify-between text-xs text-gray-500">
                      <span>Date Created: {collection.dateCreated}</span>
                      <span>Products Available: {collection.productsAvailable}</span>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h4 className="text-lg font-semibold text-gray-900">Create Collection</h4>
              <button
                type="button"
                className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-50"
                onClick={() => setShowCreateModal(false)}
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
                  value={newCollectionName}
                  onChange={(event) => setNewCollectionName(event.target.value)}
                  className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
                />
              </label>
              <label className="block text-sm text-gray-600">
                Description
                <textarea
                  value={newCollectionDescription}
                  onChange={(event) => setNewCollectionDescription(event.target.value)}
                  rows={4}
                  className="mt-2 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
                />
              </label>
            </div>
            <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-end gap-3">
              <button
                type="button"
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-50"
                onClick={() => setShowCreateModal(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-[#105E53] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0c4c45] inline-flex items-center gap-2 disabled:opacity-70"
                disabled={isCreating || !newCollectionName.trim()}
                onClick={async () => {
                  if (!newCollectionName.trim()) return;
                  setIsCreating(true);
                  try {
                    const created = await collectionService.createCollection({
                      name: newCollectionName.trim(),
                      description: newCollectionDescription.trim() || undefined,
                    });
                    success('Collection created. Add a banner image and products next.');
                    setShowCreateModal(false);
                    setNewCollectionName('');
                    setNewCollectionDescription('');
                    navigate(`/vendor/collections/${created.id}`);
                  } catch (createError: any) {
                    error(createError?.response?.data?.detail || 'Failed to create collection.');
                  } finally {
                    setIsCreating(false);
                  }
                }}
              >
                {isCreating ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Creating...
                  </>
                ) : (
                  'Create Collection'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
