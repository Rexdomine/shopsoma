import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Heart, ArrowLeft, ArrowRight, ChevronDown } from 'lucide-react';
import Layout from '../../components/layout/Layout';
import Loading from '../../components/common/Loading';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import { IMAGE_CONFIG, ROUTES } from '../../config/constants';

const PAGE_SIZE = 12;

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

const getProductPrice = (product: Product) =>
  Number(product.variants?.[0]?.price ?? product.base_price ?? 0);

const getProductComparePrice = (product: Product) =>
  Number(product.variants?.[0]?.compare_at_price ?? product.compare_at_price ?? 0);

const articles = [
  {
    id: 1,
    category: 'Culture | Sep 12, 2022',
    title: 'Why African Fashion is Necessary',
    description:
      'Discover timeless silhouettes and the artisans elevating pan-African style through thoughtful craftsmanship.',
  },
  {
    id: 2,
    category: 'Culture | Sep 12, 2022',
    title: 'The New Luxury Playbook',
    description:
      'From bold Ankara prints to tailored classics — explore the seasonal direction curated by our editors.',
  },
  {
    id: 3,
    category: 'Culture | Sep 12, 2022',
    title: 'Designers to Know Right Now',
    description:
      'Meet the ateliers reshaping modern African fashion with premium textiles and architectural lines.',
  },
];

export default function ProductList() {
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [filterMenuOpen, setFilterMenuOpen] = useState(false);
  const [filters, setFilters] = useState<FilterState>({
    category: 'All',
    color: 'All',
    price: 'all',
  });
  const [sortOption, setSortOption] = useState('suggested');
  const [customPriceInputs, setCustomPriceInputs] = useState({ min: '', max: '' });
  const [customPriceRange, setCustomPriceRange] = useState<{ min?: number; max?: number } | null>(null);

  useEffect(() => {
    const loadProducts = async () => {
      try {
        setLoading(true);
        const response = await productService.getProducts({
          page: 1,
          page_size: 60,
          sort_by: 'created_at',
          sort_order: 'desc',
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
  }, []);

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;
  const filterMenuRef = useRef<HTMLDivElement>(null);

  const categories = useMemo(() => {
    const unique = new Set<string>();
    allProducts.forEach((product) => {
      if (product.category) unique.add(product.category);
    });
    return ['All', ...Array.from(unique)];
  }, [allProducts]);

  const { colorOptions, colorMeta } = useMemo(() => {
    const metaMap = new Map<
      string,
      { label: string; hex?: string; productIds: Set<string> }
    >();
    allProducts.forEach((product) => {
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
  }, [allProducts]);

  const priceRangeCounts = useMemo(() => {
    const counts: Record<string, number> = {
      all: allProducts.length,
    };
    priceRanges.forEach((range) => {
      if (range.value !== 'all') {
        counts[range.value] = 0;
      }
    });

    allProducts.forEach((product) => {
      const price = getProductPrice(product);
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
  }, [allProducts]);

  const filteredProducts = useMemo(() => {
    let list = [...allProducts];

    if (filters.category !== 'All') {
      list = list.filter((product) => product.category === filters.category);
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
        const price = getProductPrice(product);
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
        const price = getProductPrice(product);
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
        sorted.sort((a, b) => getProductPrice(a) - getProductPrice(b));
        break;
      case 'price-desc':
        sorted.sort((a, b) => getProductPrice(b) - getProductPrice(a));
        break;
      default:
        break;
    }

    return sorted;
  }, [allProducts, filters, sortOption, customPriceRange]);

  const totalPages = Math.max(1, Math.ceil(filteredProducts.length / PAGE_SIZE));

  useEffect(() => {
    setPage((prev) => Math.min(prev, totalPages));
  }, [totalPages]);

  const paginatedProducts = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredProducts.slice(start, start + PAGE_SIZE);
  }, [filteredProducts, page]);

  const toggleFavorite = (productId: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  const handleFilterChange = (key: keyof FilterState, value: string) => {
    if (key === 'price' && value !== 'custom') {
      setCustomPriceInputs({ min: '', max: '' });
      setCustomPriceRange(null);
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

  const currentSortLabel =
    sortOptions.find((option) => option.value === sortOption)?.label || 'Suggested';

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

  return (
    <Layout>
      <section className="bg-white py-12 lg:py-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-xs uppercase tracking-[0.3em] text-gray-400 mb-8">
            Home / Collections / <span className="text-gray-700">All</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-[260px_auto] gap-12">
            <aside className="space-y-8">
              <Link
                to={ROUTES.HOME}
                className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.3em] text-gray-500 hover:text-primary transition"
              >
                <ArrowLeft className="w-4 h-4" />
                Home / All
              </Link>

              <div className="space-y-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between border-b border-gray-100 pb-3">
                    <span className="text-[11px] uppercase tracking-[0.4em] text-gray-400">
                      Filter by
                    </span>
                    <div className="relative" ref={filterMenuRef}>
                      <button
                        type="button"
                        onClick={() => setFilterMenuOpen((prev) => !prev)}
                        className={`inline-flex items-center gap-3 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.3em] transition ${
                          filterMenuOpen
                            ? 'border-primary text-primary'
                            : 'border-gray-200 text-gray-600 hover:border-primary hover:text-primary'
                        }`}
                      >
                        {currentSortLabel}
                        <ChevronDown
                          className={`w-3.5 h-3.5 transition-transform ${
                            filterMenuOpen ? 'rotate-180' : ''
                          }`}
                        />
                      </button>
                      {filterMenuOpen && (
                        <div className="absolute right-0 mt-2 w-56 rounded-2xl border border-gray-100 bg-white shadow-xl z-10 overflow-hidden">
                          {sortOptions.map((option) => (
                            <button
                              key={option.value}
                              type="button"
                              onClick={() => {
                                setSortOption(option.value);
                                setFilterMenuOpen(false);
                              }}
                              className={`w-full text-left px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] transition ${
                                sortOption === option.value
                                  ? 'text-primary bg-primary/5'
                                  : 'text-gray-600 hover:text-primary hover:bg-gray-50'
                              }`}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      )}
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

            <div className="space-y-8">

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
                  <p className="text-sm text-gray-500">
                    No products found for the selected filters.
                  </p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-8">
                    {paginatedProducts.map((product) => {
                      const isFavorite = favorites.has(product.id);
                      const price = getProductPrice(product);
                      const comparePrice = getProductComparePrice(product);
                      const hasDiscount =
                        comparePrice > 0 && comparePrice > price;
                      const image = product.images?.[0]?.image_url ?? placeholderImage;

                      return (
                        <article
                          key={product.id}
                          className="group rounded-[32px] bg-white shadow-sm transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_18px_40px_rgba(16,94,83,0.08)]"
                        >
                          <div className="relative aspect-[3/4] overflow-hidden rounded-[28px] bg-[#f5f7f8] m-3 mb-0">
                            <Link to={`${ROUTES.PRODUCTS}/${product.id}`}>
                              <img
                                src={image}
                                alt={product.title}
                                className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                                onError={(event) => {
                                  event.currentTarget.src = placeholderImage;
                                  event.currentTarget.onerror = null;
                                }}
                              />
                            </Link>
                            <button
                              type="button"
                              onClick={() => toggleFavorite(product.id)}
                              className={`absolute top-4 right-4 w-9 h-9 rounded-full flex items-center justify-center shadow-lg transition-colors ${
                                isFavorite ? 'bg-primary text-white' : 'bg-white text-gray-500'
                              }`}
                              aria-label="Add to wishlist"
                            >
                              <Heart className={`w-4 h-4 ${isFavorite ? 'fill-current' : ''}`} />
                            </button>
                          </div>
                          <div className="px-6 py-5 space-y-3">
                            <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-gray-400">
                              {product.category ?? 'Collection'}
                            </p>
                            <Link
                              to={`${ROUTES.PRODUCTS}/${product.id}`}
                              className="block text-sm font-display font-semibold text-dark leading-snug hover:text-primary transition-colors"
                            >
                              {product.title}
                            </Link>
                            <div className="flex items-end gap-2">
                              <span className="text-base font-semibold text-dark">
                                ₦{price.toLocaleString()}
                              </span>
                              {hasDiscount && (
                                <span className="text-xs text-gray-400 line-through">
                                  ₦{comparePrice.toLocaleString()}
                                </span>
                              )}
                            </div>
                          </div>
                        </article>
                      );
                    })}
                  </div>

                  <div className="flex items-center justify-center gap-3 pt-10">
                    <button
                      type="button"
                      onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                      className="w-10 h-10 rounded-full border border-gray-200 flex items-center justify-center text-gray-500 hover:border-primary hover:text-primary transition"
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
                          className={`w-10 h-10 rounded-full border text-sm font-semibold transition ${
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
                      className="w-10 h-10 rounded-full border border-gray-200 flex items-center justify-center text-gray-500 hover:border-primary hover:text-primary transition"
                      disabled={page === totalPages}
                    >
                      <ArrowRight className="w-4 h-4" />
                    </button>
                  </div>
                </>
              )}

            </div>
          </div>
        </div>
      </section>
      <section className="w-full py-16 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-12">
            <p className="text-xs uppercase tracking-[0.3em] text-gray-400">
              Showcased Articles
            </p>
            <h2 className="text-2xl font-display font-semibold text-dark">
              Stories behind the silhouettes
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {articles.map((article) => (
              <article
                key={article.id}
                className="rounded-[32px] bg-white shadow-sm hover:-translate-y-1 hover:shadow-xl transition-all duration-300 w-full"
              >
                <div className="h-48 bg-[#f5f7f8] rounded-t-[32px]" />
                <div className="p-6 space-y-3">
                  <p className="text-[11px] uppercase tracking-[0.3em] text-gray-400">
                    {article.category}
                  </p>
                  <h3 className="text-lg font-display font-semibold text-dark leading-snug">
                    {article.title}
                  </h3>
                  <p className="text-sm text-gray-500">
                    {article.description}
                  </p>
                  <button
                    type="button"
                    className="text-sm font-semibold text-primary hover:underline"
                  >
                    Read More
                  </button>
                </div>
              </article>
            ))}
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
                  className={`w-3.5 h-3.5 rounded-full mr-3 border-2 transition ${
                    selectedColor ? 'border-primary bg-primary' : 'border-gray-300 bg-white'
                  }`}
                />
                <div className="flex items-center gap-3 flex-1">
                  {showColorSwatch && (
                    <span
                      className="w-5 h-5 rounded-md border border-gray-200"
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
                    className="w-full rounded-xl border border-gray-200 py-2 pl-7 pr-3 text-sm font-semibold text-gray-700 focus:border-primary focus:ring-2 focus:ring-primary/10 transition"
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
                    className={`w-3.5 h-3.5 rounded-full mr-3 border-2 transition ${
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
