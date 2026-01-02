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
    value.toLowerCase().replace(/’/g, "'").trim();

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

  // Sync filters.category when preference changes while curated filter is active
  useEffect(() => {
    if (presetCategory) return;
    if (curatedFilterApplied) {
      if (interestCategory) {
        // Update to the new preference category
        setFilters(prev => ({
          ...prev,
          category: interestCategory,
        }));
      } else {
        // If preference is set to "neither", turn off curated filter
        setFilters(prev => ({
          ...prev,
          category: 'All',
        }));
        setCuratedFilterApplied(false);
      }
    }
  }, [preferredInterest, interestCategory, curatedFilterApplied, presetCategory]);

  const filterMenuRef = useRef<HTMLDivElement>(null);

  const categories = useMemo(() => {
    const unique = new Set<string>();
    allProducts.forEach((product) => {
      if (product.category_name) unique.add(product.category_name);
    });
    return ['All', ...Array.from(unique)];
  }, [allProducts]);

  // Get products filtered by search and category (but not color/price) for building filter options
  const searchAndCategoryFilteredProducts = useMemo(() => {
    let list = [...allProducts];

    // Apply search query filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      list = list.filter((product) => {
        const titleMatch = product.title?.toLowerCase().includes(query);
        const descriptionMatch = product.description?.toLowerCase().includes(query);
        const categoryMatch = product.category_name?.toLowerCase().includes(query);
        return titleMatch || descriptionMatch || categoryMatch;
      });
    }

    // Apply category filter
    if (activeCategory !== 'All') {
      list = list.filter((product) => matchesCategory(product, activeCategory));
    }

    return list;
  }, [allProducts, searchQuery, activeCategory]);

  const { colorOptions, colorMeta } = useMemo(() => {
    const metaMap = new Map<
      string,
      { label: string; hex?: string; productIds: Set<string> }
    >();
    // Use search-filtered products instead of all products
    searchAndCategoryFilteredProducts.forEach((product) => {
      product.variants?.forEach((variant) => {
        if (!variant.color) return;
        const normalizedKey = variant.color.toLowerCase();
        const existing =
          metaMap.get(normalizedKey) ?? {
            label: variant.color,
            hex: variant.color_hex ?? undefined,
            productIds: new Set<string>(),
          };
        if (!existing.hex && variant.color_hex) {
          existing.hex = variant.color_hex;
        }
        existing.label = variant.color;
        existing.productIds.add(product.id);
        metaMap.set(normalizedKey, existing);
      });
    });

    const sortedEntries = Array.from(metaMap.entries()).sort((a, b) =>
      a[1].label.localeCompare(b[1].label, undefined, { sensitivity: 'base' })
    );

    const colorMeta: Record<string, ColorMeta> = {};
    sortedEntries.forEach(([key, meta]) => {
      const finalMeta: ColorMeta = {
        label: meta.label,
        hex: meta.hex,
        count: meta.productIds.size,
      };
      colorMeta[meta.label] = finalMeta;
      colorMeta[key] = finalMeta;
    });

    return {
      colorOptions: ['All', ...sortedEntries.map(([, meta]) => meta.label)],
      colorMeta,
    };
  }, [searchAndCategoryFilteredProducts]);

  const priceRangeCounts = useMemo(() => {
    const counts: Record<string, number> = {
      all: searchAndCategoryFilteredProducts.length,
    };
    priceRanges.forEach((range) => {
      if (range.value !== 'all') {
        counts[range.value] = 0;
      }
    });

    searchAndCategoryFilteredProducts.forEach((product) => {
      const price = Number(product.variants?.[0]?.price ?? product.base_price ?? 0);
      priceRanges.forEach((range) => {
        if (range.value === 'all') return;
        const minMatch = range.min !== undefined ? price >= range.min : true;
        const maxMatch = range.max !== undefined ? price <= range.max : true;
        if (minMatch && maxMatch) {
          counts[range.value] += 1;
        }
      });
    });

    return counts;
  }, [searchAndCategoryFilteredProducts]);

  const filteredProducts = useMemo(() => {
    let list = [...allProducts];

    // Apply search query filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase().trim();
      list = list.filter((product) => {
        const titleMatch = product.title?.toLowerCase().includes(query);
        const descriptionMatch = product.description?.toLowerCase().includes(query);
        const categoryMatch = product.category_name?.toLowerCase().includes(query);
        return titleMatch || descriptionMatch || categoryMatch;
      });
    }

    if (activeCategory !== 'All') {
      list = list.filter((product) => matchesCategory(product, activeCategory));
    }

    if (filters.color !== 'All') {
      list = list.filter((product) =>
        product.variants?.some(
          (variant) =>
            variant.color &&
            variant.color.toLowerCase() === filters.color.toLowerCase()
        )
      );
    }

    if (filters.price === 'custom' && customPriceRange) {
      list = list.filter((product) => {
        const price = Number(product.variants?.[0]?.price ?? product.base_price ?? 0);
        if (customPriceRange.min !== undefined && price < customPriceRange.min) {
          return false;
        }
        if (customPriceRange.max !== undefined && price > customPriceRange.max) {
          return false;
        }
        return true;
      });
    } else if (filters.price !== 'all') {
      list = list.filter((product) => {
        const price = Number(product.variants?.[0]?.price ?? product.base_price ?? 0);
        switch (filters.price) {
          case '0-50000':
            return price < 50000;
          case '50000-100000':
            return price >= 50000 && price <= 100000;
          case '100000-200000':
            return price >= 100000 && price <= 200000;
          case '200000+':
            return price >= 200000;
          default:
            return true;
        }
      });
    }

    const sorted = [...list];
    switch (sortOption) {
      case 'newest':
        sorted.sort(
          (a, b) =>
            new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        );
        break;
      case 'price-asc':
        sorted.sort((a, b) => {
          const priceA = Number(a.variants?.[0]?.price ?? a.base_price ?? 0);
          const priceB = Number(b.variants?.[0]?.price ?? b.base_price ?? 0);
          return priceA - priceB;
        });
        break;
      case 'price-desc':
        sorted.sort((a, b) => {
          const priceA = Number(a.variants?.[0]?.price ?? a.base_price ?? 0);
          const priceB = Number(b.variants?.[0]?.price ?? b.base_price ?? 0);
          return priceB - priceA;
        });
        break;
      default:
        break;
    }

    return sorted;
  }, [allProducts, filters, sortOption, customPriceRange, searchQuery, activeCategory]);

  const totalPages = Math.max(1, Math.ceil(filteredProducts.length / PAGE_SIZE));

  useEffect(() => {
    setPage((prev) => Math.min(prev, totalPages));
  }, [totalPages]);

  const paginatedProducts = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredProducts.slice(start, start + PAGE_SIZE);
  }, [filteredProducts, page]);

  const emptyStateMessage =
    presetCategory === 'Men'
      ? 'No menswear products available yet. Please check back soon.'
      : presetCategory === 'Women'
        ? 'No womenswear products available yet. Please check back soon.'
        : 'No products found for the selected filters.';

const handleFilterChange = (key: keyof FilterState, value: string) => {
  if (key === 'price' && value !== 'custom') {
    setCustomPriceInputs({ min: '', max: '' });
    setCustomPriceRange(null);
  }
  if (key === 'category' && value !== interestCategory) {
    setCuratedFilterApplied(false);
  }
  setFilters((prev) => ({ ...prev, [key]: value }));
  setPage(1);
};

  const parsePriceInput = (value: string): number | undefined => {
    if (!value) return undefined;
    const cleaned = value.replace(/[^\d.]/g, '');
    if (!cleaned) return undefined;
    const parsed = Number(cleaned);
    return Number.isNaN(parsed) ? undefined : parsed;
  };

  const handleCustomPriceApply = () => {
    const minValue = parsePriceInput(customPriceInputs.min);
    const maxValue = parsePriceInput(customPriceInputs.max);

    if (minValue === undefined && maxValue === undefined) {
      setCustomPriceRange(null);
      setFilters((prev) => ({ ...prev, price: 'all' }));
      setPage(1);
      return;
    }

    const rangeMin =
      minValue !== undefined && maxValue !== undefined
        ? Math.min(minValue, maxValue)
        : minValue;
    const rangeMax =
      minValue !== undefined && maxValue !== undefined
        ? Math.max(minValue, maxValue)
        : maxValue;

    setCustomPriceRange({
      min: rangeMin,
      max: rangeMax,
    });
    setFilters((prev) => ({ ...prev, price: 'custom' }));
    setPage(1);
  };

  const paginationItems = useMemo(() => {
    if (totalPages <= 5) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }

    if (page <= 3) {
      return [1, 2, 3, '...', totalPages];
    }

    if (page >= totalPages - 2) {
      return [1, '...', totalPages - 2, totalPages - 1, totalPages];
    }

    return [1, '...', page, '...', totalPages];
  }, [page, totalPages]);

  useEffect(() => {
    if (!filterMenuOpen) return undefined;

    const handleClickOutside = (event: MouseEvent) => {
      if (
        filterMenuRef.current &&
        !filterMenuRef.current.contains(event.target as Node)
      ) {
        setFilterMenuOpen(false);
      }
    };

    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setFilterMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEsc);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [filterMenuOpen]);

  const heroContent =
    heroOverride ||
    (presetCategory === 'Men'
      ? MEN_HERO
      : presetCategory === 'Women'
        ? WOMEN_HERO
        : DEFAULT_HERO);

  return (
    <Layout>
      {/* Store Hero Section */}
      <section
        className="relative w-full min-h-[50vh] bg-cover bg-center flex items-end"
        style={{
          backgroundImage: `url('${heroContent.imageUrl}')`,
        }}
      >
        {/* Dark overlay for text legibility */}
        <div className="absolute inset-0 bg-black/20" />

        {/* Overlay content - Left positioned */}
        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 w-full pb-12 lg:pb-16">
          <div className="max-w-md">
            <h1
              className="text-3xl lg:text-4xl font-display text-white mb-4"
              style={{ textShadow: '0 2px 8px rgba(0,0,0,0.4)' }}
            >
              {heroContent.title}
            </h1>
            <p
              className="text-sm font-serif text-white/95 leading-relaxed mb-6"
              style={{ textShadow: '0 1px 4px rgba(0,0,0,0.3)' }}
            >
              {heroContent.body}
            </p>
            <button
              className="inline-block px-6 py-2.5 bg-white/10 backdrop-blur-sm border border-white text-white text-xs font-ui uppercase tracking-[0.2em] hover:bg-white hover:text-dark transition-all"
            >
              {heroContent.ctaLabel || 'Learn More'}
            </button>
          </div>
        </div>
      </section>

      {/* Filter Bar + Search Row */}
      <section className="bg-[var(--color-page-bg)] border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
            {/* Left side: Tabs */}
            <div className="flex items-center gap-6">
              <button
                type="button"
                className="text-sm font-ui tracking-wide text-dark border-b-2 border-primary pb-1"
              >
                All Items ({filteredProducts.length})
              </button>
              <button
                type="button"
                className="text-sm font-ui tracking-wide text-gray-500 hover:text-dark pb-1"
              >
                Collections
              </button>
            </div>

            {/* Right side: Search + Refine */}
            <div className="flex items-center gap-4 w-full lg:w-auto">
              <div className="relative flex-1 lg:flex-initial lg:w-64">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search"
                  className="w-full pl-10 pr-4 py-2 border border-gray-300 text-sm font-ui focus:outline-none focus:border-primary transition"
                  defaultValue={searchQuery}
                />
              </div>
              <button
                type="button"
                onClick={() => setFilterMenuOpen(true)}
                className="px-6 py-2 border border-gray-300 text-xs font-ui uppercase tracking-[0.2em] text-dark hover:border-primary hover:text-primary transition whitespace-nowrap"
              >
                REFINE
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Filter Modal */}
      {filterMenuOpen && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div
            ref={filterMenuRef}
            className="bg-white w-full max-w-2xl max-h-[80vh] overflow-y-auto shadow-2xl"
          >
            {/* Modal Header */}
            <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
              <h2 className="text-lg font-ui uppercase tracking-[0.2em] text-dark">Filter Products</h2>
              <button
                type="button"
                onClick={() => setFilterMenuOpen(false)}
                className="p-2 hover:bg-gray-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6">
              <aside className="space-y-8">

              {searchQuery && (
                <div className="bg-primary/5 border border-primary/20 px-6 py-4">
                  <p className="text-sm text-gray-700">
                    Search results for: <span className="font-semibold text-primary">"{searchQuery}"</span>
                    {filters.category !== 'All' && (
                      <span className="ml-2">
                        in <span className="font-semibold text-primary">{filters.category}</span>
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Found {filteredProducts.length} {filteredProducts.length === 1 ? 'product' : 'products'}
                  </p>
                </div>
              )}

              <div className="space-y-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                    <span className="text-[11px] uppercase tracking-[0.4em] text-gray-400">
                      Sort by
                    </span>
                    <div className="relative">
                      <select
                        value={sortOption}
                        onChange={(e) => setSortOption(e.target.value)}
                        className="border border-gray-200 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.3em] text-gray-600 hover:border-primary focus:border-primary focus:outline-none transition"
                      >
                        {sortOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <FilterGroup
                    title="Category"
                    options={categories}
                    selected={filters.category}
                    onChange={(value) => handleFilterChange('category', value)}
                  />
                  <FilterGroup
                    title="Color"
                    options={colorOptions}
                    selected={filters.color}
                    onChange={(value) => handleFilterChange('color', value)}
                    type="color"
                    colorMeta={colorMeta}
                  />
                  <PriceFilter
                    selected={filters.price}
                    ranges={priceRanges}
                    counts={priceRangeCounts}
                    inputs={customPriceInputs}
                    onInputChange={(field, value) =>
                      setCustomPriceInputs((prev) => ({ ...prev, [field]: value }))
                    }
                    onApplyCustom={handleCustomPriceApply}
                    onSelectRange={(value) => handleFilterChange('price', value)}
                  />
                </div>
              </div>
              </aside>
            </div>

            {/* Modal Footer */}
            <div className="sticky bottom-0 bg-white border-t border-gray-200 px-6 py-4 flex items-center justify-between">
              <button
                type="button"
                onClick={() => {
                  setFilters({ category: 'All', color: 'All', price: 'all' });
                  setCustomPriceInputs({ min: '', max: '' });
                  setCustomPriceRange(null);
                }}
                className="text-sm font-ui text-gray-600 hover:text-primary underline"
              >
                Clear All
              </button>
              <button
                type="button"
                onClick={() => setFilterMenuOpen(false)}
                className="px-8 py-2.5 bg-primary text-white text-xs font-ui uppercase tracking-[0.2em] hover:bg-primary-dark transition"
              >
                Apply Filters
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Product Grid Section */}
      <section className="bg-[var(--color-page-bg)] py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="space-y-8">
              {preferredInterest && !showInterestBanner && (
                <div className="text-right">
                  <button
                    type="button"
                    className="text-xs text-gray-500 hover:text-primary underline"
                    onClick={() => {
                      setShowInterestBanner(true);
                      if (typeof window !== 'undefined') {
                        window.localStorage.removeItem('shopsoma_pref_interest_banner');
                      }
                    }}
                  >
                    Show curated picks reminder
                  </button>
                </div>
              )}

              {preferredInterest && showInterestBanner && (
                <div className="border border-gray-200 rounded-sm p-4 text-sm text-gray-700 bg-gray-50">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <p>
                        You're interested in{' '}
                        <span className="font-semibold">
                          {preferredInterest === 'menswear' ? 'Menswear' : 'Womenswear'}
                        </span>{' '}
                        looks.
                      </p>
                      <button
                        type="button"
                        className="mt-2 text-xs text-gray-500 hover:text-primary underline"
                        onClick={() => {
                          setShowInterestBanner(false);
                          if (typeof window !== 'undefined') {
                            window.localStorage.setItem('shopsoma_pref_interest_banner', 'hidden');
                          }
                        }}
                      >
                        Hide this reminder
                      </button>
                    </div>
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
                      {/* Row 1: Vendor Showcase (2 cols) + 1 Product - 3 column grid */}
                      {paginatedProducts.length >= 1 && (
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-x-6 gap-y-10 mb-10">
                          <div className="lg:col-span-2">
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
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10 mb-10">
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
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10 mb-10">
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
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10">
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
                          <div className="lg:col-span-2">
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
                    </>
                  ) : (
                    /* Other pages: Regular 4-column grid, 4 rows = 12 products */
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-10">
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
                    ₦
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
