import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';

const heroImages = [
  {
    webp: '/images/hero/portrait-lesbian-couple-posing-together.webp',
    jpg: '/images/hero/portrait-lesbian-couple-posing-together.jpg',
    alt: 'Fashion collection showcase'
  },
  {
    webp: '/images/hero/medium-shot-woman-posing.webp',
    jpg: '/images/hero/medium-shot-woman-posing.jpg',
    alt: 'Elegant style inspiration'
  },
  {
    webp: '/images/hero/happy-man-party-wearing-sunglasses.webp',
    jpg: '/images/hero/happy-man-party-wearing-sunglasses.jpg',
    alt: 'Modern fashion trends'
  },
  {
    webp: '/images/hero/portrait-cool-man-with-sunglasses-dancing.webp',
    jpg: '/images/hero/portrait-cool-man-with-sunglasses-dancing.jpg',
    alt: 'Contemporary streetwear'
  },
];

function OptimizedImage({
  webp,
  jpg,
  alt,
  index,
  onLoaded,
}: {
  webp: string;
  jpg: string;
  alt: string;
  index: number;
  onLoaded: () => void;
}) {
  const [isLoaded, setIsLoaded] = useState(false);

  const handleLoad = () => {
    if (!isLoaded) {
      setIsLoaded(true);
      onLoaded();
    }
  };

  return (
    <div className="aspect-square overflow-hidden bg-gray-100 shadow-lg relative border border-gray-200">
      {!isLoaded && (
        <div className="absolute inset-0 bg-gradient-to-br from-gray-200 to-gray-100 animate-pulse" />
      )}
      <picture>
        <source srcSet={webp} type="image/webp" />
        <img
          src={jpg}
          alt={alt}
          className={`w-full h-full object-cover transition-all duration-700 ease-out hover:scale-105 ${
            isLoaded ? 'opacity-100' : 'opacity-0'
          }`}
          loading={index === 0 ? 'eager' : 'lazy'}
          onLoad={handleLoad}
          decoding="async"
        />
      </picture>
    </div>
  );
}

export default function HeroSection() {
  const totalImages = heroImages.length;
  const [loadedCount, setLoadedCount] = useState(0);

  const handleImageLoaded = useCallback(() => {
    setLoadedCount((prev) => Math.min(prev + 1, totalImages));
  }, [totalImages]);

  const showHeroGrid = loadedCount >= totalImages;
  const skeletonTiles = useMemo(() => Array.from({ length: totalImages }), [totalImages]);

  return (
    <section className="bg-[var(--color-page-bg)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 lg:py-24">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Left Content */}
          <div className="space-y-6">
            <div className="space-y-4">
              <h1 className="text-4xl lg:text-5xl font-display font-bold text-dark leading-tight">
                New Household
                <br />
                Collection
              </h1>
              <p className="text-base font-body text-gray-700">
                Enhance the appearance of your space.
              </p>
            </div>

            <Link
              to="/products"
              className="inline-flex items-center justify-center gap-2 px-8 py-3.5 font-ui font-semibold transition-all duration-200 text-base bg-cta text-[var(--color-cta-text)] hover:bg-cta-dark border border-cta"
            >
              Shop Now
              <ArrowRight className="w-5 h-5" />
            </Link>

            {/* Stats */}
            <div className="flex gap-8 pt-6">
              <div>
                <div className="text-2xl font-display font-bold text-dark">200+</div>
                <div className="text-sm font-body text-gray-500">Products</div>
              </div>
              <div>
                <div className="text-2xl font-display font-bold text-dark">50+</div>
                <div className="text-sm font-body text-gray-500">Vendors</div>
              </div>
              <div>
                <div className="text-2xl font-display font-bold text-dark">1000+</div>
                <div className="text-sm font-body text-gray-500">Customers</div>
              </div>
            </div>
          </div>

          {/* Right Content - Product Showcase */}
          <div className="relative hidden lg:block">
            {!showHeroGrid && (
              <div className="grid grid-cols-2 gap-4">
                {skeletonTiles.map((_, index) => (
                  <div
                    key={`hero-skeleton-${index}`}
                    className="aspect-square rounded-md bg-gradient-to-br from-gray-200 to-gray-100 animate-pulse"
                  />
                ))}
              </div>
            )}
            <div className={`grid grid-cols-2 gap-4 ${showHeroGrid ? 'opacity-100' : 'opacity-0'}`}>
              {heroImages.map((image, index) => (
                <OptimizedImage
                  key={image.jpg}
                  {...image}
                  index={index}
                  onLoaded={handleImageLoaded}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
