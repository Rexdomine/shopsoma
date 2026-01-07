import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ChevronDown, Search, X } from 'lucide-react';
import Layout from '../../components/layout/Layout';
import Loading from '../../components/common/Loading';
import type { Product } from '../../types';
import { productService, type ProductListParams } from '../../services/productService';
import { MEN_HERO_IMAGE_URL, WOMEN_HERO_IMAGE_URL } from '../../config/constants';
import ProductCard from '../../components/products/ProductCard';
import VendorShowcaseCard from '../../components/products/VendorShowcaseCard';
import { useWishlistActions } from '../../hooks/useWishlistActions';
import { usePreferenceStore } from '../../store/preferenceStore';

const PAGE_SIZE = 12;

// Spotlight vendor configuration
const SPOTLIGHT_VENDOR = {
  id: '1', // Replace with actual vendor ID
  name: 'Shopsoma Fashion Store',
  imageUrl: '/images/hero/demo-image-2.png', // Replace with actual vendor image
  productCount: 24, // This can be dynamic if needed
};

type FilterState = {
  category: string;
  color: string;
  price: string;
};

type PriceRangeOption = {
  label: string;
  value: string;
  min?: number;
  max?: number;
};

const priceRanges: PriceRangeOption[] = [
  { label: 'All', value: 'all' },
  { label: '₦0 - ₦50,000', value: '0-50000', min: 0, max: 50000 },
  { label: '₦50,000 - ₦100,000', value: '50000-100000', min: 50000, max: 100000 },
  { label: '₦100,000 - ₦200,000', value: '100000-200000', min: 100000, max: 200000 },
  { label: '₦200,000+', value: '200000+', min: 200000 },
];

const sortOptions = [
  { label: 'Suggested', value: 'suggested' },
  { label: 'Newest', value: 'newest' },
  { label: 'Price: Low to High', value: 'price-asc' },
  { label: 'Price: High to Low', value: 'price-desc' },
];


// Predefined colors for visual swatches
const COLOR_PRESETS: Record<string, string> = {
  black: '#1f2933',
  blue: '#1d4ed8',
  brown: '#8b5d33',
  gold: '#c59d5f',
  gray: '#6b7280',
  green: '#0f766e',
  neutral: '#cfcfcf',
  orange: '#f97316',
  purple: '#a855f7',
  red: '#ef4444',
  white: '#ffffff',
  yellow: '#facc15',
  beige: '#f5f5dc',
  pink: '#f472b6',
};

type ColorMeta = {
  label: string;
  hex?: string;
  count: number;
};

type HeroContent = {
  title: string;
  body: string;
  imageUrl: string;
  ctaLabel?: string;
};

type ProductListProps = {
  presetCategory?: string;
  initialParams?: ProductListParams;
  heroOverride?: HeroContent;
};

const DEFAULT_HERO: HeroContent = {
  title: 'Lisa Folawiyo',
  body: 'Kooky Recipes Bad Raw Viral. Mukbang Pitchfork Party Church-key Viral Bicycle Rights Photo Chicharrones Cray. Heirloom Cray Blue Bottle Shaman Health Art Party Tumeric Salvia',
  imageUrl: '/images/hero/demo-image-2.png',
  ctaLabel: 'Learn More',
};

const MEN_HERO: HeroContent = {
  title: 'Menswear: Elevated Everyday Style',
  body: 'Discover tailored pieces, bold silhouettes and everyday staples, curated for the modern man.',
  imageUrl: MEN_HERO_IMAGE_URL,
  ctaLabel: 'Shop all menswear',
};

const WOMEN_HERO: HeroContent = {
  title: 'Womenswear: Effortless Elegance',
  body: 'Explore statement pieces, refined tailoring and everyday essentials crafted for modern women.',
  imageUrl: WOMEN_HERO_IMAGE_URL,
  ctaLabel: 'Shop all womenswear',
};

const MEN_CATEGORY_KEYS = ['men', 'mens', 'menswear', "men's fashion", 'mens fashion', "men's wear", 'mens wear'];
const WOMEN_CATEGORY_KEYS = ['women', 'womens', 'womenswear', "women's fashion", 'womens fashion', "women's wear", 'womens wear'];

export default function ProductList({
  presetCategory,
  initialParams,
  heroOverride,
}: ProductListProps = {}) {
  const [searchParams] = useSearchParams();
  const searchQuery = searchParams.get('q') || '';
  const categoryParam = searchParams.get('category') || '';

  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [filters, setFilters] = useState<FilterState>({
    category: presetCategory || categoryParam || 'All',
    color: 'All',
    price: 'all',
  });
  const preferredInterest = usePreferenceStore((state) => state.interest);
  const [curatedFilterApplied, setCuratedFilterApplied] = useState(false);
  const [showInterestBanner, setShowInterestBanner] = useState<boolean>(() => {
    if (typeof window === 'undefined') return true;
    const stored = window.localStorage.getItem('shopsoma_pref_interest_banner');
    return stored !== 'hidden';
  });
  const [sortOption, setSortOption] = useState('suggested');
  const [customPriceInputs, setCustomPriceInputs] = useState({ min: '', max: '' });
  const [customPriceRange, setCustomPriceRange] = useState<{ min?: number; max?: number } | null>(null);
  const { favorites, toggleFavorite } = useWishlistActions();
  const activeCategory = presetCategory || filters.category;
  const initialParamsKey = useMemo(() => JSON.stringify(initialParams ?? {}), [initialParams]);
  const stableInitialParams = useMemo(() => {
    if (!initialParams) return undefined;
    return { ...initialParams };
  }, [initialParamsKey, initialParams]);

  const normalize = (value: string) =>
    value.toLowerCase().replace(//g, "'").trim();

  const categoryMatchesPreset = (categoryValue: string, preset: string) => {
    const normalized = normalize(categoryValue);
    if (preset === 'Men') return MEN_CATEGORY_KEYS.some((key) => normalized === key);
    if (preset === 'Women') return WOMEN_CATEGORY_KEYS.some((key) => normalized === key);
    return normalized === normalize(preset);
  };

  const matchesCategory = (product: Product, category: string) => {
    if (!category || category === 'All') return true;
    const productCategory = normalize(product.category_name || '');
    const parentCategory = normalize(product.category_parent_name || '');
    if (productCategory && categoryMatchesPreset(productCategory, category)) {
      return true;
    }
    if (parentCategory && categoryMatchesPreset(parentCategory, category)) {
      return true;
    }
    const collectionCategory = normalize(product.collection_name || '');
    if (collectionCategory && categoryMatchesPreset(collectionCategory, category)) {
      return true;
    }
    const description = normalize(product.description || '');
    return description.startsWith(`${normalize(category)} -`);
  };

  useEffect(() => {
    const loadProducts = async () => {
      try {
        setLoading(true);
        setPage(1);
        const response = await productService.getProducts({
          page: 1,
          page_size: 60,
          sort_by: 'created_at',
          sort_order: 'desc',
          ...stableInitialParams,
        });
        setAllProducts(response.products || []);
        setError(null);
      } catch (err) {
        console.error('Failed to load products', err);
        setError('We could not load the current collection. Please refresh.');
      } finally {
        setLoading(false);
      }
    };

    loadProducts();
  }, [initialParamsKey, stableInitialParams]);

  // Derive interest category from preference
  const interestCategory = preferredInterest === 'menswear' ? 'Men' : preferredInterest === 'womenswear' ? 'Women' : null;

  // Update filters when URL params change
  useEffect(() => {
    if (presetCategory) {
      setFilters((prev) => ({ ...prev, category: presetCategory }));
    } else {
      setFilters(prev => ({
        ...prev,
        category: categoryParam || 'All'
      }));
      if (!categoryParam || categoryParam === 'All') {
        setCuratedFilterApplied(false);
      }
    }
  }, [categoryParam, presetCategory]);

  // Determine if there are products in current filters
  const filteredProducts = useMemo(() => {
    return allProducts.filter((product) => {
      const matchesSearch =
        !searchQuery ||
        product.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        product.description?.toLowerCase().includes(searchQuery.toLowerCase());

      const matchesCategoryFilter = matchesCategory(product, activeCategory);

      const matchesColor =
        filters.color === 'All' ||
        product.variants?.some(
          variant =>
            variant.color?.toLowerCase() === filters.color.toLowerCase()
        );

      let matchesPrice = true;
      if (filters.price !== 'all') {
        const range = priceRanges.find(r => r.value === filters.price);
        if (range) {
          if (range.min !== undefined && product.base_price < range.min) matchesPrice = false;
          if (range.max !== undefined && product.base_price > range.max) matchesPrice = false;
        }
      }

      if (customPriceRange) {
        if (customPriceRange.min !== undefined && product.base_price < customPriceRange.min) matchesPrice = false;
        if (customPriceRange.max !== undefined && product.base_price > customPriceRange.max) matchesPrice = false;
      }

      return matchesSearch && matchesCategoryFilter && matchesColor && matchesPrice;
    });
  }, [allProducts, searchQuery, activeCategory, filters, customPriceRange]);

  const sortedProducts = useMemo(() => {
    const products = [...filteredProducts];
    switch (sortOption) {
      case 'newest':
        products.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        break;
      case 'price-asc':
        products.sort((a, b) => a.base_price - b.base_price);
        break;
      case 'price-desc':
        products.sort((a, b) => b.base_price - a.base_price);
        break;
      default:
        break;
    }
    return products;
  }, [filteredProducts, sortOption]);

  const paginatedProducts = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return sortedProducts.slice(start, start + PAGE_SIZE);
  }, [sortedProducts, page]);

  const totalPages = Math.max(1, Math.ceil(sortedProducts.length / PAGE_SIZE));

  const paginationItems = useMemo(() => {
    if (totalPages <= 5) return Array.from({ length: totalPages }, (_, i) => i + 1);
    const items: (number | string)[] = [1];
    if (page > 3) items.push('...');
    const start = Math.max(2, page - 1);
    const end = Math.min(totalPages - 1, page + 1);
    for (let i = start; i <= end; i++) items.push(i);
    if (page < totalPages - 2) items.push('...');
    items.push(totalPages);
    return items;
  }, [page, totalPages]);

  useEffect(() => {
    if (page > totalPages) setPage(1);
  }, [totalPages, page]);

  const allCategories = useMemo(() => {
    const categories = new Set<string>();
    allProducts.forEach(product => {
      if (product.category_name) categories.add(product.category_name);
      if (product.category_parent_name) categories.add(product.category_parent_name);
    });
    return ['All', ...Array.from(categories)];
  }, [allProducts]);

  const allColors = useMemo(() => {
    const colors = new Set<string>();
    allProducts.forEach(product => {
      product.variants?.forEach(variant => {
        if (variant.color) colors.add(variant.color);
      });
    });
    return ['All', ...Array.from(colors)];
  }, [allProducts]);

  const colorMeta = useMemo(() => {
    const meta: Record<string, ColorMeta> = {};
    allProducts.forEach((product) => {
      product.variants?.forEach((variant) => {
        if (!variant.color) return;
        if (!meta[variant.color]) {
          meta[variant.color] = { label: variant.color, hex: variant.color_hex, count: 0 };
        }
        meta[variant.color].count += 1;
        if (!meta[variant.color].hex && variant.color_hex) {
          meta[variant.color].hex = variant.color_hex;
        }
      });
    });
    return meta;
  }, [allProducts]);

  const priceCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    priceRanges.forEach(range => {
      if (range.value === 'all') {
        counts[range.value] = filteredProducts.length;
        return;
      }
      counts[range.value] = filteredProducts.filter(product => {
        const price = product.base_price;
        if (range.min !== undefined && price < range.min) return false;
        if (range.max !== undefined && price > range.max) return false;
        return true;
      }).length;
    });
    return counts;
  }, [filteredProducts]);

  const formatCount = (count: number) => (count < 10 ? `0${count}` : `${count}`);

  const emptyStateMessage = useMemo(() => {
    if (presetCategory === 'Men') return 'No menswear products available yet. Please check back soon.';
    if (presetCategory === 'Women') return 'No womenswear products available yet. Please check back soon.';
    if (presetCategory === 'Perfumes') return 'No perfumes available yet. Please check back soon.';
    if (presetCategory === 'Bags and Wallets') return 'No bags or wallets available yet. Please check back soon.';
    if (searchQuery) return `No results found for "${searchQuery}".`;
    return 'No products match the current filters.';
  }, [presetCategory, searchQuery]);

  const heroContent = useMemo(() => {
    if (heroOverride) return heroOverride;
    if (presetCategory === 'Men') return MEN_HERO;
    if (presetCategory === 'Women') return WOMEN_HERO;
    return DEFAULT_HERO;
  }, [heroOverride, presetCategory]);

  const heroCtaLinks = useMemo(() => {
    if (presetCategory) {
      return [{ label: heroContent.ctaLabel ?? 'Shop all', to: '/products' }];
    }
    return [
      { label: 'Shop Men', to: '/products/men' },
      { label: 'Shop Women', to: '/products/women' },
    ];
  }, [heroContent.ctaLabel, presetCategory]);

  const handleFilterChange = (type: keyof FilterState, value: string) => {
    setFilters(prev => ({ ...prev, [type]: value }));
    setPage(1);
    if (type === 'category' && value === 'All') {
      setCuratedFilterApplied(false);
    }
  };

  const handleSortChange = (value: string) => {
    setSortOption(value);
    setPage(1);
  };

  const handleCustomPriceChange = (field: 'min' | 'max', value: string) => {
    setCustomPriceInputs(prev => ({ ...prev, [field]: value }));
  };

  const applyCustomPrice = () => {
    const min = customPriceInputs.min ? Number(customPriceInputs.min.replace(/[^0-9.]/g, '')) : undefined;
    const max = customPriceInputs.max ? Number(customPriceInputs.max.replace(/[^0-9.]/g, '')) : undefined;

    setCustomPriceRange({
      min: min !== undefined && !Number.isNaN(min) ? min : undefined,
      max: max !== undefined && !Number.isNaN(max) ? max : undefined,
    });
    setFilters(prev => ({ ...prev, price: 'custom' }));
    setPage(1);
  };

  const resetFilters = () => {
    setFilters({ category: presetCategory || categoryParam || 'All', color: 'All', price: 'all' });
    setCustomPriceRange(null);
    setCustomPriceInputs({ min: '', max: '' });
    setSortOption('suggested');
    setPage(1);
  };

  return (
    <Layout>
      <section className="relative">
        <div className="relative h-[440px] md:h-[480px] lg:h-[520px] overflow-hidden">
          <div
            className="absolute inset-0"
            style={{
              backgroundImage: `url(${heroContent.imageUrl})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
            }}
          />
          <div className="absolute inset-0 bg-black/10" />
          <div className="relative z-10 h-full flex flex-col justify-center text-center text-white px-6">
            <div className="max-w-2xl mx-auto space-y-6">
              <h1 className="text-2xl sm:text-3xl md:text-4xl font-serif tracking-[0.08em]">
                {heroContent.title}
              </h1>
              <p className="text-sm md:text-base font-serif text-white/90">
                {heroContent.body}
              </p>
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-center gap-4">
                {heroCtaLinks.map((cta) => (
                  <Link
                    key={cta.label}
                    to={cta.to}
                    className="inline-flex justify-center border border-white/70 px-4 py-2 text-xs uppercase tracking-[0.4em] hover:bg-white hover:text-primary transition"
                  >
                    {cta.label}
                  </Link>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-4 md:px-6">
            <div className="flex flex-wrap items-center justify-between gap-3 py-4">
              <div className="flex items-center gap-4 text-sm">
                <button
                  type="button"
                  className={`text-sm uppercase tracking-[0.2em] ${filters.category === 'All' ? 'text-primary font-semibold' : 'text-gray-500'}`}
                  onClick={() => handleFilterChange('category', 'All')}
                >
                  All Items ({formatCount(filteredProducts.length)})
                </button>
                <button
                  type="button"
                  className="text-sm uppercase tracking-[0.2em] text-gray-500"
                >
                  Collections
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <Search className="w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    placeholder="Search"
                    className="text-sm border-b border-gray-200 focus:outline-none focus:border-primary"
                    onChange={() => {
                      // Search is currently handled via URL param
                    }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setFilterMenuOpen(true)}
                  className="text-xs uppercase tracking-[0.3em] border border-gray-200 px-4 py-2"
                >
                  Refine
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Product grid */}
      <section className="max-w-7xl mx-auto px-4 md:px-6 py-10">
        <div className="flex gap-8">
          {/* Filters Sidebar */}
          <aside className="hidden lg:block w-64 shrink-0">
            <div className="sticky top-24">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xs font-semibold uppercase tracking-[0.4em] text-gray-400">Filters</h3>
                <button
                  type="button"
                  onClick={resetFilters}
                  className="text-xs font-semibold uppercase tracking-[0.4em] text-primary"
                >
                  Reset
                </button>
              </div>
              <FilterGroup
                title="Category"
                options={allCategories}
                selected={filters.category}
                onChange={(value) => handleFilterChange('category', value)}
              />
              <FilterGroup
                title="Color"
                options={allColors}
                selected={filters.color}
                onChange={(value) => handleFilterChange('color', value)}
                type="color"
                colorMeta={colorMeta}
              />
              <PriceFilter
                selected={filters.price}
                ranges={priceRanges}
                counts={priceCounts}
                inputs={customPriceInputs}
                onInputChange={handleCustomPriceChange}
                onApplyCustom={applyCustomPrice}
                onSelectRange={(value) => {
                  handleFilterChange('price', value);
                  setCustomPriceRange(null);
                }}
              />
            </div>
          </aside>

          {/* Product grid content */}
          <div className="flex-1">
              {/* Preference Based Filter Banner */}
              {interestCategory && showInterestBanner && (
                <div className="mb-8 rounded-none border border-gray-200 bg-gray-50 px-6 py-5">
                  <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
                    <div>
                      <p className="text-xs uppercase tracking-[0.4em] text-gray-400">Suggested for you</p>
                      <h2 className="text-lg font-serif text-gray-900">
                        {interestCategory === 'Men' ? 'Menswear picks tailored for you' : 'Womenswear picks tailored for you'}
                      </h2>
                      <p className="text-sm text-gray-500">
                        Based on your account preference, we pulled the best {interestCategory.toLowerCase()} drops.
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        className="text-xs uppercase tracking-[0.4em] text-gray-500 hover:text-primary"
                        onClick={() => {
                          setShowInterestBanner(false);
                          if (typeof window !== 'undefined') {
                            window.localStorage.setItem('shopsoma_pref_interest_banner', 'hidden');
                          }
                        }}
                      >
                        Hide this reminder
                      </button>
                    <button
                      type="button"
                      className={`px-4 py-2 text-xs font-semibold uppercase tracking-[0.3em] rounded-sm transition border ${
                        curatedFilterApplied
                          ? 'border-gray-300 text-gray-600 hover:bg-gray-100'
                          : 'border-primary text-primary hover:bg-primary hover:text-white'
                      }`}
                      onClick={() => {
                        if (curatedFilterApplied) {
                          handleFilterChange('category', 'All');
                          setCuratedFilterApplied(false);
                        } else {
                          setFilters((prev) => ({
                            ...prev,
                            category: interestCategory ?? 'All',
                          }));
                          setCuratedFilterApplied(true);
                        }
                      }}
                    >
                      {curatedFilterApplied ? 'View all products' : 'View curated picks'}
                    </button>
                  </div>
                </div>
              )}

              {loading ? (
                <div className="py-20">
                  <Loading fullScreen={false} message="Preparing the catalog..." />
                </div>
              ) : error ? (
                <div className="py-16 text-center">
                  <p className="text-sm text-red-500">{error}</p>
                </div>
              ) : paginatedProducts.length === 0 ? (
              <div className="py-16 text-center">
                  <p className="text-sm text-gray-500">{emptyStateMessage}</p>
                </div>
              ) : (
                <>
                  {/* Page 1: 4 rows with vendor showcases */}
                  {page === 1 ? (
                    <>
                      {/* Mobile layout: 2-column grid with full-width featured vendors */}
                      <div className="lg:hidden space-y-10">
                        <VendorShowcaseCard
                          vendorId={SPOTLIGHT_VENDOR.id}
                          vendorName={SPOTLIGHT_VENDOR.name}
                          imageUrl={SPOTLIGHT_VENDOR.imageUrl}
                          productCount={SPOTLIGHT_VENDOR.productCount}
                        />
                        <div className="grid grid-cols-2 gap-x-4 gap-y-8">
                          {(() => {
                            const mobileItems = paginatedProducts.slice(0, 12).reduce<
                              Array<
                                | { type: 'product'; product: Product }
                                | { type: 'vendor'; key: string }
                              >
                            >((acc, product, index) => {
                              acc.push({ type: 'product', product });
                              if (index === 5) {
                                acc.push({ type: 'vendor', key: 'featured-vendor' });
                              }
                              return acc;
                            }, []);

                            return mobileItems.map((item) => {
                              if (item.type === 'vendor') {
                                return (
                                  <div key={item.key} className="col-span-2">
                                    <VendorShowcaseCard
                                      vendorId={SPOTLIGHT_VENDOR.id}
                                      vendorName="Featured Designer"
                                      imageUrl={SPOTLIGHT_VENDOR.imageUrl}
                                      productCount={SPOTLIGHT_VENDOR.productCount}
                                    />
                                  </div>
                                );
                              }
                              const isFavorite = favorites.has(item.product.id);
                              return (
                                <div key={item.product.id} className="col-span-1">
                                  <ProductCard
                                    product={item.product}
                                    onToggleFavorite={toggleFavorite}
                                    isFavorite={isFavorite}
                                  />
                                </div>
                              );
                            });
                          })()}
                        </div>
                      </div>

                      {/* Desktop layout: curated vendor + product grid */}
                      <div className="hidden lg:block">
                        {/* Row 1: Vendor Showcase (2 cols) + 1 Product - 3 column grid */}
                        {paginatedProducts.length >= 1 && (
                          <div className="grid grid-cols-3 gap-x-6 gap-y-10 mb-10">
                            <div className="col-span-2">
                              <VendorShowcaseCard
                                vendorId={SPOTLIGHT_VENDOR.id}
                                vendorName={SPOTLIGHT_VENDOR.name}
                                imageUrl={SPOTLIGHT_VENDOR.imageUrl}
                                productCount={SPOTLIGHT_VENDOR.productCount}
                              />
                            </div>
                            {paginatedProducts.slice(0, 1).map((product) => {
                              const isFavorite = favorites.has(product.id);
                              return (
                                <ProductCard
                                  key={product.id}
                                  product={product}
                                  onToggleFavorite={toggleFavorite}
                                  isFavorite={isFavorite}
                                />
                              );
                            })}
                          </div>
                        )}

                        {/* Row 2: 4 Products - 4 column grid */}
                        {paginatedProducts.length >= 2 && (
                          <div className="grid grid-cols-4 gap-x-6 gap-y-10 mb-10">
                            {paginatedProducts.slice(1, 5).map((product) => {
                              const isFavorite = favorites.has(product.id);
                              return (
                                <ProductCard
                                  key={product.id}
                                  product={product}
                                  onToggleFavorite={toggleFavorite}
                                  isFavorite={isFavorite}
                                />
                              );
                            })}
                          </div>
                        )}

                        {/* Row 3: 4 Products - 4 column grid */}
                        {paginatedProducts.length >= 6 && (
                          <div className="grid grid-cols-4 gap-x-6 gap-y-10 mb-10">
                            {paginatedProducts.slice(5, 9).map((product) => {
                              const isFavorite = favorites.has(product.id);
                              return (
                                <ProductCard
                                  key={product.id}
                                  product={product}
                                  onToggleFavorite={toggleFavorite}
                                  isFavorite={isFavorite}
                                />
                              );
                            })}
                          </div>
                        )}

                        {/* Row 4: 1 Product + Vendor Showcase (2 cols) + 1 Product - 4 column grid */}
                        {paginatedProducts.length >= 10 && (
                          <div className="grid grid-cols-4 gap-x-6 gap-y-10">
                            {paginatedProducts.slice(9, 10).map((product) => {
                              const isFavorite = favorites.has(product.id);
                              return (
                                <ProductCard
                                  key={product.id}
                                  product={product}
                                  onToggleFavorite={toggleFavorite}
                                  isFavorite={isFavorite}
                                />
                              );
                            })}
                            <div className="col-span-2">
                              <VendorShowcaseCard
                                vendorId={SPOTLIGHT_VENDOR.id}
                                vendorName="Featured Designer"
                                imageUrl={SPOTLIGHT_VENDOR.imageUrl}
                                productCount={SPOTLIGHT_VENDOR.productCount}
                              />
                            </div>
                            {paginatedProducts.slice(10, 11).map((product) => {
                              const isFavorite = favorites.has(product.id);
                              return (
                                <ProductCard
                                  key={product.id}
                                  product={product}
                                  onToggleFavorite={toggleFavorite}
                                  isFavorite={isFavorite}
                                />
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </>
                  ) : (
                    /* Other pages: Regular 4-column grid, 4 rows = 12 products */
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10">
                      {paginatedProducts.map((product) => {
                        const isFavorite = favorites.has(product.id);
                        return (
                          <ProductCard
                            key={product.id}
                            product={product}
                            onToggleFavorite={toggleFavorite}
                            isFavorite={isFavorite}
                          />
                        );
                      })}
                    </div>
                  )}

                  <div className="flex items-center justify-center gap-3 pt-10">
                    <button
                      type="button"
                      onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                      className="w-10 h-10 border border-gray-200 flex items-center justify-center text-gray-500 hover:border-primary hover:text-primary transition"
                      disabled={page === 1}
                    >
                      <ArrowLeft className="w-4 h-4" />
                    </button>
                    {paginationItems.map((item, index) =>
                      typeof item === 'number' ? (
                        <button
                          key={item}
                          type="button"
                          onClick={() => setPage(item)}
                          className={`w-10 h-10 border text-sm font-semibold transition ${
                            page === item
                              ? 'border-primary bg-primary text-white'
                              : 'border-gray-200 text-gray-600 hover:border-primary hover:text-primary'
                          }`}
                        >
                          {item}
                        </button>
                      ) : (
                        <span key={`${item}-${index}`} className="px-2 text-gray-400">
                          {item}
                        </span>
                      )
                    )}
                    <button
                      type="button"
                      onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
                      className="w-10 h-10 border border-gray-200 flex items-center justify-center text-gray-500 hover:border-primary hover:text-primary transition"
                      disabled={page === totalPages}
                    >
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                </>
              )}

          </div>
        </div>
      </section>
    </Layout>
  );
}

interface FilterGroupProps {
  title: string;
  options: string[];
  selected: string;
  onChange: (value: string) => void;
  type?: 'default' | 'color';
  colorMeta?: Record<string, ColorMeta>;
}

function FilterGroup({
  title,
  options,
  selected,
  onChange,
  type = 'default',
  colorMeta,
}: FilterGroupProps) {
  const [open, setOpen] = useState(false);

  const getColorValue = (option: string): string => {
    if (option === 'All') return '#ffffff';
    const meta = colorMeta?.[option];
    if (meta?.hex) return meta.hex;
    return COLOR_PRESETS[option.toLowerCase()] ?? option.toLowerCase();
  };

  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center justify-between py-4 text-xs font-semibold uppercase tracking-[0.4em] text-gray-500 hover:text-primary transition"
      >
        <span>{title}</span>
        <span className="flex items-center gap-2 text-[11px] tracking-[0.2em]">
          <span className="text-gray-400">{selected}</span>
          <ChevronDown
            className={`w-4 h-4 transition-transform ${open ? 'rotate-180 text-primary' : ''}`}
          />
        </span>
      </button>
      <div
        className={`overflow-hidden transition-[max-height] duration-300 ${
          open ? 'max-h-72' : 'max-h-0'
        }`}
      >
        <div
          className={`pb-4 space-y-1.5 ${type === 'color' ? 'overflow-y-auto pr-1' : ''}`}
          style={type === 'color' && open ? { maxHeight: '18rem' } : undefined}
        >
          {options.length === 0 && (
            <p className="text-xs text-gray-400 px-2">No options yet</p>
          )}
          {options.map((option) => {
            const selectedColor = selected === option;
            const showColorSwatch = type === 'color' && option !== 'All';
            const swatchColor = showColorSwatch ? getColorValue(option) : undefined;
            const count =
              showColorSwatch && option !== 'All' ? colorMeta?.[option]?.count ?? 0 : 0;

            return (
              <button
                key={option}
                type="button"
                onClick={() => onChange(option)}
                className={`flex items-center w-full text-left text-sm font-semibold py-1.5 px-2 transition ${
                  selectedColor ? 'text-primary' : 'text-gray-600 hover:text-primary'
                }`}
              >
                <span
                  className={`w-3.5 h-3.5 mr-3 border-2 transition ${
                    selectedColor ? 'border-primary bg-primary' : 'border-gray-300 bg-white'
                  }`}
                />
                <div className="flex items-center gap-3 flex-1">
                  {showColorSwatch && (
                    <span
                      className="w-5 h-5 border border-gray-200"
                      style={{ backgroundColor: swatchColor }}
                    />
                  )}
                  <span>{option}</span>
                </div>
                {showColorSwatch && count > 0 && (
                  <span className="text-xs text-gray-400">({count})</span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

interface PriceFilterProps {
  selected: string;
  ranges: PriceRangeOption[];
  counts: Record<string, number>;
  inputs: { min: string; max: string };
  onInputChange: (field: 'min' | 'max', value: string) => void;
  onApplyCustom: () => void;
  onSelectRange: (value: string) => void;
}

function PriceFilter({
  selected,
  ranges,
  counts,
  inputs,
  onInputChange,
  onApplyCustom,
  onSelectRange,
}: PriceFilterProps) {
  const [open, setOpen] = useState(false);

  const selectedLabel =
    selected === 'custom'
      ? 'Custom'
      : ranges.find((range) => range.value === selected)?.label || 'All';

  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center justify-between py-4 text-xs font-semibold uppercase tracking-[0.4em] text-gray-500 hover:text-primary transition"
      >
        <span>Price</span>
        <span className="flex items-center gap-2 text-[11px] tracking-[0.2em]">
          <span className="text-gray-400">{selectedLabel}</span>
          <ChevronDown
            className={`w-4 h-4 transition-transform ${open ? 'rotate-180 text-primary' : ''}`}
          />
        </span>
      </button>
      <div
        className={`overflow-hidden transition-[max-height] duration-300 ${
          open ? 'max-h-[420px]' : 'max-h-0'
        }`}
      >
        <div className="pb-5 space-y-4">
          <div className="grid grid-cols-2 gap-3 px-2">
            {(['min', 'max'] as const).map((field) => (
              <div key={field}>
                <label className="block text-[10px] uppercase tracking-[0.35em] text-gray-400 mb-1">
                  {field === 'min' ? 'Min' : 'Max'}
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">
                    
6
                  </span>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={inputs[field]}
                    placeholder={field === 'min' ? '0' : '150,000'}
                    onChange={(event) => onInputChange(field, event.target.value)}
                    onBlur={onApplyCustom}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        onApplyCustom();
                      }
                    }}
                    className="w-full border border-gray-200 py-2 pl-7 pr-3 text-sm font-semibold text-gray-700 focus:border-primary focus:ring-2 focus:ring-primary/10 transition"
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-1.5">
            {ranges.map((range) => {
              const isSelected = selected === range.value && selected !== 'custom';
              const count = counts[range.value] ?? 0;
              return (
                <button
                  key={range.value}
                  type="button"
                  onClick={() => onSelectRange(range.value)}
                  className={`flex items-center w-full text-left text-sm font-semibold py-1.5 px-2 transition ${
                    isSelected ? 'text-primary' : 'text-gray-600 hover:text-primary'
                  }`}
                >
                  <span
                    className={`w-3.5 h-3.5 mr-3 border-2 transition ${
                      isSelected ? 'border-primary bg-primary' : 'border-gray-300 bg-white'
                    }`}
                  />
                  <div className="flex items-center justify-between flex-1 text-sm">
                    <span>
                      {range.value === 'all' ? 'All Price Points' : range.label}
                    </span>
                    <span className="text-xs text-gray-400">({count})</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
