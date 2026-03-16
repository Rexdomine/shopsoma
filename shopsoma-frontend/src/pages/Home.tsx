import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/layout/Layout';
import type { Product } from '../types';
import { productService } from '../services/productService';
import { getFeaturedRotationSettings } from '../services/settingsService';
import { IMAGE_CONFIG } from '../config/constants';
import { useWishlistActions } from '../hooks/useWishlistActions';
import { useCurrency } from '../hooks/useCurrency';
import { formatPriceWithConversion } from '../utils/pricing';

const HERO_IMAGE = '/images/hero/demo-image-2.png';

type HomeProductCardProps = {
  product: Product;
  isFavorite: boolean;
  onToggleFavorite: (id: string) => void;
};

function HomeProductCard({
  product,
  isFavorite,
  onToggleFavorite,
}: HomeProductCardProps) {
  const [isHovered, setIsHovered] = useState(false);
  const { currentCurrency, exchangeRates } = useCurrency();
  const primaryImage = product.images?.[0]?.image_url || IMAGE_CONFIG.PLACEHOLDER;
  const secondaryImage = product.images?.[1]?.image_url || primaryImage;
  const vendor = product.vendor_name || 'Shopsoma';
  const price = product.variants?.[0]?.price ?? product.base_price ?? 0;

  const sizeOptions = Array.from(
    new Set(
      (product.variants || [])
        .map((v) => v.size)
        .filter((v): v is string => Boolean(v))
    )
  );

  const colorOptions = (() => {
    const colorMap = new Map<string, { color: string; hex: string | null }>();
    (product.variants || []).forEach((v) => {
      if (v.color) {
        const key = v.color.toLowerCase();
        if (!colorMap.has(key)) {
          colorMap.set(key, { color: v.color, hex: v.color_hex ?? null });
        }
      }
    });
    return Array.from(colorMap.values());
  })();

  return (
    <div
      className="group relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="relative">
        <Link to={`/products/${product.id}`} className="relative aspect-[3/4] overflow-hidden bg-white block">
          <img
            src={isHovered ? secondaryImage : primaryImage}
            alt={product.title}
            className="w-full h-full object-cover transition-all duration-500"
          />
          <button
            type="button"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onToggleFavorite(product.id);
            }}
            className="absolute top-3 right-3 p-1.5 hover:opacity-80 transition-opacity z-10"
            aria-label="Toggle favorite"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill={isFavorite ? '#ffffff' : 'none'}
              stroke="#ffffff"
              strokeWidth="1.5"
              className="transition-all"
            >
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
            </svg>
          </button>
        </Link>

        {/* Hover Modal */}
        {isHovered && (
          <div className="absolute bottom-0 left-0 right-0 bg-white/95 backdrop-blur-sm p-4 transition-all duration-300">
            <div className="space-y-3 text-center">
              {sizeOptions.length > 0 && (
                <div>
                  <p className="text-[10px] font-ui uppercase tracking-[0.25em] text-gray-500 mb-2">Sizes</p>
                  <div className="flex flex-wrap items-center justify-center gap-2">
                    {sizeOptions.map((size) => (
                      <span
                        key={size}
                        className="text-xs font-ui"
                        style={{ color: '#1E5053' }}
                      >
                        {size}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {colorOptions.length > 0 && (
                <div>
                  <p className="text-[10px] font-ui uppercase tracking-[0.25em] text-gray-500 mb-2">Colors</p>
                  <div className="flex flex-wrap items-center justify-center gap-1.5">
                    {colorOptions.slice(0, 6).map((color) => (
                      <span
                        key={color.color}
                        className="w-5 h-5 border border-gray-300"
                        style={{ backgroundColor: color.hex ?? '#e5e5e5' }}
                        title={color.color}
                      />
                    ))}
                    {colorOptions.length > 6 && (
                      <span className="text-xs font-ui text-gray-500 ml-1">+{colorOptions.length - 6}</span>
                    )}
                  </div>
                </div>
              )}

              <Link
                to={`/products/${product.id}`}
                className="inline-block w-full bg-primary text-white text-xs font-ui tracking-[0.2em] py-2.5 uppercase hover:bg-primary-dark transition-colors"
              >
                Add to Bag
              </Link>
            </div>
          </div>
        )}
      </div>

      <Link to={`/products/${product.id}`} className="block pt-3 space-y-1">
        <p className="text-[10px] font-ui uppercase tracking-[0.25em]" style={{ color: '#1E5053' }}>
          {vendor}
        </p>
        <h3 className="text-sm font-serif leading-snug" style={{ color: '#1E5053' }}>
          {product.title}
        </h3>
        <p className="text-sm font-ui" style={{ color: '#1E5053' }}>
          {formatPriceWithConversion(price, product.currency, currentCurrency, exchangeRates)}
        </p>
      </Link>
    </div>
  );
}

function Hero() {
  return (
    <section
      className="hero relative w-full min-h-[45vh] sm:min-h-[60vh] lg:min-h-[70vh] bg-cover bg-center flex items-end justify-center"
      style={{ backgroundImage: `url(${HERO_IMAGE})` }}
    >
      <div className="text-center pb-10 sm:pb-14 lg:pb-16 px-4">
        <h1
          className="text-xl sm:text-2xl lg:text-4xl font-serif font-normal text-white mb-4 sm:mb-6"
          style={{
            fontFamily: 'var(--font-serif)',
            fontWeight: 400,
            textShadow: '0 2px 8px rgba(0,0,0,0.3)'
          }}
        >
          Orange Culture: A night Beyond
        </h1>
        <div className="flex items-center justify-center gap-10">
          <Link
            to="/men"
            className="text-white font-ui uppercase tracking-[0.2em] text-sm border-b border-white pb-1 hover:opacity-80 transition-opacity"
          >
            Shop Men
          </Link>
          <Link
            to="/women"
            className="text-white font-ui uppercase tracking-[0.2em] text-sm border-b border-white pb-1 hover:opacity-80 transition-opacity"
          >
            Shop Women
          </Link>
        </div>
      </div>
    </section>
  );
}

type FeaturedCollabProps = {
  product: Product;
};

function FeaturedCollab({ product }: FeaturedCollabProps) {
  const imageUrl = product.images?.[0]?.image_url || '';
  const title = product.title;
  const description = product.description || '';
  const productLink = `/products/${product.id}`;

  return (
    <section className="w-full bg-[var(--color-page-bg)]">
      <div className="w-full">
        <div className="grid grid-cols-1 lg:grid-cols-2 items-stretch">
          {/* Left Side - Text Content with Theme Background */}
          <div className="order-2 lg:order-1 bg-[var(--color-page-bg)] flex flex-col justify-center items-center text-center px-6 sm:px-10 lg:px-24 py-12 sm:py-16 lg:py-28">
            <div className="max-w-md space-y-6">
              <p className="text-[10px] font-ui uppercase tracking-[0.3em]" style={{ color: '#1E5053' }}>
                FEATURED
              </p>
              <h2
                className="text-2xl sm:text-3xl lg:text-4xl font-serif leading-tight"
                style={{
                  fontFamily: 'var(--font-serif)',
                  color: '#1E5053'
                }}
              >
                {title}
              </h2>
              <p
                className="text-sm sm:text-base font-serif leading-relaxed"
                style={{ color: '#1E5053' }}
              >
                {description}
              </p>
              <Link
                to={productLink}
                className="bg-[#1E5053] text-white text-xs font-ui uppercase tracking-[0.2em] px-8 py-3 hover:opacity-90 transition-opacity inline-flex items-center justify-center"
              >
                SHOP NOW
              </Link>
            </div>
          </div>

          {/* Right Side - Image */}
          <div className="order-1 lg:order-2 relative h-[280px] sm:h-[360px] lg:h-auto">
            <img
              src={imageUrl}
              alt={title}
              className="w-full h-full object-cover"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function HomeProductCardSkeleton() {
  return (
    <div className="bg-white border border-[#E7E3DA] rounded-lg overflow-hidden animate-pulse">
      <div className="h-64 bg-gray-200" />
      <div className="p-4 space-y-3">
        <div className="h-3 w-24 bg-gray-200 rounded" />
        <div className="h-4 w-3/4 bg-gray-200 rounded" />
        <div className="h-3 w-32 bg-gray-200 rounded" />
      </div>
    </div>
  );
}

function FeaturedCollabSkeleton() {
  return (
    <section className="w-full bg-[var(--color-page-bg)]">
      <div className="grid grid-cols-1 lg:grid-cols-2 items-stretch">
        <div className="order-2 lg:order-1 bg-[var(--color-page-bg)] flex flex-col justify-center items-center text-center px-6 sm:px-10 lg:px-24 py-12 sm:py-16 lg:py-28">
          <div className="max-w-md space-y-6 w-full animate-pulse">
            <div className="h-3 w-20 bg-gray-200 rounded mx-auto" />
            <div className="h-8 w-3/4 bg-gray-200 rounded mx-auto" />
            <div className="h-4 w-full bg-gray-200 rounded mx-auto" />
            <div className="h-4 w-5/6 bg-gray-200 rounded mx-auto" />
            <div className="h-10 w-40 bg-gray-200 rounded mx-auto" />
          </div>
        </div>
        <div className="order-1 lg:order-2 relative h-[280px] sm:h-[360px] lg:h-auto bg-gray-200 animate-pulse" />
      </div>
    </section>
  );
}

function CategoryStrip() {
  const categories = useMemo(
    () => [
      { name: 'Gowns', image: '/images/gown-category-image.svg' },
      { name: 'Hand stitched', image: '/images/demo-image-3.svg' },
      { name: 'Strong Construction', image: '/images/strong-construction-category-image.svg' },
      { name: 'Cotton', image: '/images/cotton-category-image.svg' },
    ],
    []
  );

  return (
    <section className="py-16 bg-[var(--color-page-bg)]">
      <div className="w-full px-4 sm:px-6 space-y-6 sm:space-y-8">
        <h3 className="text-left text-xs sm:text-sm font-ui tracking-normal" style={{ color: '#1E5053' }}>
          Shop by Category
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {categories.map((cat) => (
            <div key={cat.name} className="relative group cursor-pointer">
              <div className="aspect-[3/4] overflow-hidden bg-gray-100">
                <img
                  src={cat.image}
                  alt={cat.name}
                  className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                />
              </div>
              <div className="absolute bottom-4 left-4">
                <p
                  className="text-sm font-ui bg-white/90 px-3 py-1.5"
                  style={{ color: '#1E5053' }}
                >
                  {cat.name}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function EditorialSection() {
  return (
    <section className="py-16 bg-[var(--color-page-bg)]">
      <div className="max-w-4xl mx-auto px-4 sm:px-8 lg:px-12 text-center space-y-10 sm:space-y-12">
        <p
          className="text-sm sm:text-base font-serif leading-relaxed"
          style={{
            fontFamily: 'var(--font-serif)',
            color: '#1E5053',
            lineHeight: '1.8'
          }}
        >
          Shopsoma Is A Fund Fashion Bird Meh Dollar. +1 +1 Semiotics Direct Lyft Hexagon Beer Pug Locavore. Squid It Of Crucifix Cardigan Bushwick Organic You Cleanse. Bushwick Shabby Tumblr Ennui Big Photo Humblebrag Hoodie. Neutra Heirloom Thundercats Booth Irony Hoodie.
        </p>

        {/* Editorial Image Section */}
        <div className="space-y-6">
          <div className="space-y-2">
            <h4
              className="text-xl sm:text-2xl font-serif"
              style={{
                fontFamily: 'var(--font-serif)',
                color: '#1E5053'
              }}
            >
              Kilentar: Avant Premier
            </h4>
            <p
              className="text-sm sm:text-base font-serif"
              style={{
                fontFamily: 'var(--font-serif)',
                color: '#1E5053'
              }}
            >
              Autumn/Winter 2026
            </p>
          </div>

          <div className="w-full overflow-hidden">
            <img
              src="/images/demo-image-7.svg"
              alt="Kilentar: Avant Premier"
              className="w-full h-auto object-cover"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

export default function Home() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [featuredProducts, setFeaturedProducts] = useState<Product[]>([]);
  const [featuredIndex, setFeaturedIndex] = useState(0);
  const [featuredLoading, setFeaturedLoading] = useState(true);
  const [featuredReady, setFeaturedReady] = useState(false);
  const [rotationMinutes, setRotationMinutes] = useState(10);
  const { favorites, toggleFavorite } = useWishlistActions();

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setLoading(true);
        const data = await productService.getProducts({
          page_size: 8,
          sort_by: 'created_at',
          sort_order: 'desc',
        });
        if (mounted) {
          setProducts(data.products);
        }
      } catch (error) {
        console.error('Failed to load products for homepage', error);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        setFeaturedLoading(true);
        const rotation = await getFeaturedRotationSettings();
        if (mounted && rotation?.rotation_minutes) {
          setRotationMinutes(rotation.rotation_minutes);
        }
        const data = await productService.getFeaturedProducts(12);
        if (mounted) {
          setFeaturedProducts(data || []);
        }
      } catch (error) {
        console.error('Failed to load featured products', error);
      } finally {
        if (mounted) setFeaturedLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!featuredProducts.length) return undefined;
    const rotationMs = Math.max(rotationMinutes, 1) * 60 * 1000;
    const computeIndex = () =>
      Math.floor(Date.now() / rotationMs) % featuredProducts.length;

    setFeaturedIndex(computeIndex());
    const timer = window.setInterval(() => {
      setFeaturedIndex(computeIndex());
    }, 60 * 1000);

    return () => window.clearInterval(timer);
  }, [featuredProducts, rotationMinutes]);

  const featuredProduct = featuredProducts[featuredIndex];
  const featuredImageUrl = featuredProduct?.images?.[0]?.image_url || '';
  const showFeaturedSkeleton =
    featuredLoading ||
    !featuredProduct ||
    !featuredProduct.images?.length ||
    !featuredProduct.images?.[0]?.image_url ||
    !featuredReady;

  useEffect(() => {
    if (!featuredImageUrl) {
      setFeaturedReady(false);
      return;
    }

    let isMounted = true;
    setFeaturedReady(false);

    const img = new Image();
    img.onload = () => {
      if (isMounted) setFeaturedReady(true);
    };
    img.onerror = () => {
      if (isMounted) setFeaturedReady(true);
    };
    img.src = featuredImageUrl;

    return () => {
      isMounted = false;
    };
  }, [featuredImageUrl]);

  return (
    <Layout>
      <div className="bg-[var(--color-page-bg)] text-[var(--color-text-main)]">
        <Hero />

        <section className="py-12 bg-[var(--color-page-bg)] border-b border-[#1E5053]">
          <div className="w-full px-4 sm:px-8 lg:px-20 space-y-6">
            {loading ? (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
                {Array.from({ length: 4 }).map((_, index) => (
                  <HomeProductCardSkeleton key={`home-skeleton-${index}`} />
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
                {products.slice(0, 4).map((product) => (
                  <HomeProductCard
                    key={product.id}
                    product={product}
                    isFavorite={favorites.has(product.id)}
                    onToggleFavorite={toggleFavorite}
                  />
                ))}
              </div>
            )}
          </div>
        </section>

        {showFeaturedSkeleton ? (
          <FeaturedCollabSkeleton />
        ) : (
          <FeaturedCollab product={featuredProduct} />
        )}
        <CategoryStrip />
        <EditorialSection />
      </div>
    </Layout>
  );
}
