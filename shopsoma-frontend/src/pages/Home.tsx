import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/layout/Layout';
import type { Product } from '../types';
import { productService } from '../services/productService';
import { getFeaturedRotationSettings } from '../services/settingsService';
import { IMAGE_CONFIG } from '../config/constants';
import { useWishlistActions } from '../hooks/useWishlistActions';
import { useCurrency } from '../hooks/useCurrency';
import { formatPriceWithConversion } from '../utils/pricing';
import { getProductImageSource, getProductImageSources } from '../utils/productImages';

const HERO_SLIDES = [
  {
    desktop: '/images/hero/campaign/campaign-exterior-desktop.webp',
    mobile: '/images/hero/campaign/campaign-exterior-mobile.webp',
    alt: 'Orange Culture campaign look 1: three models outside a terracotta building',
  },
  {
    desktop: '/images/hero/campaign/campaign-interior-desktop.webp',
    mobile: '/images/hero/campaign/campaign-interior-mobile.webp',
    alt: 'Orange Culture campaign look 2: models gathered in an editorial interior',
  },
  {
    desktop: '/images/hero/campaign/campaign-lounge-desktop.webp',
    mobile: '/images/hero/campaign/campaign-lounge-mobile.webp',
    alt: 'Orange Culture campaign look 3: a model relaxing in an editorial lounge',
  },
] as const;

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
  const productImages = getProductImageSources(product);
  const primaryImage = productImages[0] ?? { src: IMAGE_CONFIG.PLACEHOLDER };
  const secondaryImage = productImages[1] ?? primaryImage;
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

  const handleImageError = (
    event: React.SyntheticEvent<HTMLImageElement>,
    fallbackSrc?: string
  ) => {
    const image = event.currentTarget;
    if (fallbackSrc && image.dataset.fallbackApplied !== 'true') {
      image.dataset.fallbackApplied = 'true';
      image.src = fallbackSrc;
      return;
    }
    image.src = IMAGE_CONFIG.PLACEHOLDER;
    image.onerror = null;
  };

  return (
    <div
      className="group relative"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div className="relative">
        <Link to={`/products/${product.id}`} className="relative aspect-[3/4] overflow-hidden bg-white block">
          <img
            src={isHovered ? secondaryImage.src : primaryImage.src}
            alt={product.title}
            className="w-full h-full object-cover transition-all duration-500"
            onError={(event) => handleImageError(
              event,
              isHovered ? secondaryImage.fallbackSrc : primaryImage.fallbackSrc
            )}
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
  const [activeSlide, setActiveSlide] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [mountedSlides, setMountedSlides] = useState<Set<number>>(() => new Set([0]));
  const [readySlides, setReadySlides] = useState<Set<number>>(() => new Set([0]));
  const [pendingSlide, setPendingSlide] = useState<number | null>(null);
  const [failedSlides, setFailedSlides] = useState<Set<number>>(() => new Set());
  const [retryingSlides, setRetryingSlides] = useState<Set<number>>(() => new Set());
  const retryTimers = useRef<Map<number, number>>(new Map());
  const [isInteracting, setIsInteracting] = useState(false);
  const [isPaused, setIsPaused] = useState(false);

  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    return () => {
      retryTimers.current.forEach((timer) => window.clearTimeout(timer));
      retryTimers.current.clear();
    };
  }, []);

  const requestSlide = (target: number) => {
    let next: number | null = null;
    for (let offset = 0; offset < HERO_SLIDES.length; offset += 1) {
      const candidate = (target + offset + HERO_SLIDES.length) % HERO_SLIDES.length;
      if (!failedSlides.has(candidate)) {
        next = candidate;
        break;
      }
    }
    if (next === null) return;
    if (
      (next === activeSlide && mountedSlides.has(next) && readySlides.has(next) && !failedSlides.has(next))
      || (pendingSlide === next && mountedSlides.has(next) && !failedSlides.has(next))
    ) return;
    if (readySlides.has(next)) {
      setPendingSlide(null);
      setActiveSlide(next);
      return;
    }
    setMountedSlides((mounted) => new Set(mounted).add(next));
    setPendingSlide(next);
  };

  const handleSlideReady = (index: number) => {
    setFailedSlides((failed) => {
      const next = new Set(failed);
      next.delete(index);
      return next;
    });
    setReadySlides((ready) => new Set(ready).add(index));
    setRetryingSlides((retrying) => {
      const next = new Set(retrying);
      next.delete(index);
      return next;
    });
    const isFailureFallback = failedSlides.has(activeSlide);
    if (pendingSlide === index && (isFailureFallback || (!isPaused && !isInteracting && !reducedMotion))) {
      setActiveSlide(index);
      setPendingSlide(null);
    }
  };

  const scheduleRetry = (index: number) => {
    if (retryTimers.current.has(index)) return;
    const timer = window.setTimeout(() => {
      retryTimers.current.delete(index);
      setMountedSlides((mounted) => new Set(mounted).add(index));
      setRetryingSlides((retrying) => new Set(retrying).add(index));
      setPendingSlide((pending) => pending ?? index);
    }, 15000);
    retryTimers.current.set(index, timer);
  };

  const handleSlideError = (index: number) => {
    scheduleRetry(index);
    const failed = new Set(failedSlides).add(index);
    const findFallback = () => {
      for (let offset = 1; offset < HERO_SLIDES.length; offset += 1) {
        const candidate = (index + offset) % HERO_SLIDES.length;
        if (!failed.has(candidate)) return candidate;
      }
      return null;
    };

    setFailedSlides(failed);
    setReadySlides((ready) => {
      const next = new Set(ready);
      next.delete(index);
      return next;
    });
    setMountedSlides((mounted) => {
      const next = new Set(mounted);
      next.delete(index);
      return next;
    });

    if (index === activeSlide || (pendingSlide === index && failed.has(activeSlide))) {
      const fallback = findFallback();
      if (fallback === null) {
        setPendingSlide(null);
        return;
      }
      setMountedSlides((mounted) => new Set(mounted).add(fallback));
      if (readySlides.has(fallback)) {
        setActiveSlide(fallback);
        setPendingSlide(null);
      } else {
        setPendingSlide(fallback);
      }
      return;
    }

    if (pendingSlide === index) setPendingSlide(null);
  };

  useEffect(() => {
    if (reducedMotion || isInteracting || isPaused || pendingSlide !== null) return;
    const timer = window.setTimeout(() => requestSlide(activeSlide + 1), 6500);
    return () => window.clearTimeout(timer);
  }, [activeSlide, failedSlides, isInteracting, isPaused, pendingSlide, reducedMotion]);

  useEffect(() => {
    if (pendingSlide === null || failedSlides.has(pendingSlide)) return;
    const isFailureFallback = failedSlides.has(activeSlide);
    if (!isFailureFallback && (isPaused || isInteracting || reducedMotion)) return;
    if (readySlides.has(pendingSlide)) {
      setActiveSlide(pendingSlide);
      setPendingSlide(null);
      return;
    }
    requestSlide(pendingSlide);
  }, [activeSlide, failedSlides, isInteracting, isPaused, pendingSlide, readySlides, reducedMotion]);

  return (
    <section
      aria-label="Orange Culture campaign"
      aria-roledescription="carousel"
      className="hero relative isolate flex min-h-[520px] w-full items-end overflow-hidden bg-[#1b1715] sm:min-h-[600px] lg:min-h-[700px]"
      onMouseEnter={() => setIsInteracting(true)}
      onMouseLeave={() => setIsInteracting(false)}
      onFocusCapture={() => setIsInteracting(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setIsInteracting(false);
      }}
    >
      {HERO_SLIDES.map((slide, index) => mountedSlides.has(index) && (
        <picture
          key={slide.desktop}
          aria-hidden={index !== activeSlide || failedSlides.has(index)}
          className={`absolute inset-0 transition-opacity duration-[1400ms] ease-out ${index === activeSlide && !failedSlides.has(index) ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
        >
          <source media="(max-width: 767px)" srcSet={slide.mobile} />
          <img
            src={slide.desktop}
            alt={slide.alt}
            className="h-full w-full object-cover"
            loading={index === 0 || pendingSlide === index || retryingSlides.has(index) ? 'eager' : 'lazy'}
            fetchPriority={index === 0 ? 'high' : pendingSlide === index || retryingSlides.has(index) ? 'auto' : 'low'}
            decoding="async"
            onLoad={() => handleSlideReady(index)}
            onError={() => handleSlideError(index)}
          />
        </picture>
      ))}
      {failedSlides.size === HERO_SLIDES.length && (
        <div className="absolute inset-0 grid place-items-center px-6 text-center text-sm text-white/80" role="status">
          Campaign imagery is temporarily unavailable.
        </div>
      )}

      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#105E53]/[0.82] via-[#105E53]/[0.30] to-transparent" />
      <button
        type="button"
        aria-label={isPaused ? 'Resume automatic campaign slideshow' : 'Pause automatic campaign slideshow'}
        aria-pressed={isPaused}
        onClick={() => setIsPaused((paused) => !paused)}
        className="pointer-events-auto absolute right-5 top-5 z-20 rounded-full border border-white/60 bg-black/20 px-3 py-2 text-[10px] font-ui uppercase tracking-[0.16em] text-white backdrop-blur-sm transition-colors hover:bg-black/35 focus:outline-none focus:ring-2 focus:ring-white focus:ring-offset-2 focus:ring-offset-transparent"
      >
        {isPaused ? 'Resume' : 'Pause'}
      </button>
      <div className="relative z-10 flex w-full flex-col items-start px-5 pb-7 sm:px-10 sm:pb-10 lg:px-16 lg:pb-14">
        <div className="max-w-xl text-white">
          <p className="mb-3 text-[10px] font-ui font-semibold uppercase tracking-[0.32em] text-white/75">ShopSoma presents</p>
          <h1 className="font-serif text-3xl font-normal leading-tight sm:text-4xl lg:text-5xl" style={{ fontFamily: 'var(--font-serif)', textShadow: '0 2px 12px rgba(0,0,0,0.35)' }}>
            Orange Culture: A night Beyond
          </h1>
          <div className="mt-5 flex flex-wrap items-center gap-x-7 gap-y-3">
            <Link to="/men" className="pointer-events-auto border-b border-white pb-1 text-xs font-ui uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-75">Shop Men</Link>
            <Link to="/women" className="pointer-events-auto border-b border-white pb-1 text-xs font-ui uppercase tracking-[0.2em] text-white transition-opacity hover:opacity-75">Shop Women</Link>
          </div>
        </div>
      </div>
    </section>
  );
}

type FeaturedCollabProps = {
  product: Product;
};

function FeaturedCollab({ product }: FeaturedCollabProps) {
  const image = getProductImageSource(product);
  const imageUrl = image?.src || IMAGE_CONFIG.PLACEHOLDER;
  const title = product.title;
  const description = product.description || '';
  const productLink = `/products/${product.id}`;

  const handleImageError = (event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    if (image?.fallbackSrc && img.dataset.fallbackApplied !== 'true') {
      img.dataset.fallbackApplied = 'true';
      img.src = image.fallbackSrc;
      return;
    }
    img.src = IMAGE_CONFIG.PLACEHOLDER;
    img.onerror = null;
  };

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
              onError={handleImageError}
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
      { name: 'Dresses', image: '/images/gown-category-image.svg' },
      { name: 'Occasion wear', image: '/images/demo-image-3.svg' },
      { name: 'Workwear', image: '/images/strong-construction-category-image.svg' },
      { name: 'Casual', image: '/images/cotton-category-image.svg' },
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
  const featuredImage = featuredProduct ? getProductImageSource(featuredProduct) : null;
  const featuredImageUrl = featuredImage?.src || '';
  const showFeaturedSkeleton =
    featuredLoading ||
    !featuredProduct ||
    !featuredImageUrl ||
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
