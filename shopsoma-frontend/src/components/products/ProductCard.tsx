import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { Product } from '../../types';
import { Bookmark } from 'lucide-react';
import { IMAGE_CONFIG } from '../../config/constants';
import { useCurrencyStore } from '../../store/currencyStore';
import { formatPriceWithConversion } from '../../utils/pricing';
import { hasSolidColorHex } from '../../utils/colorDisplay';
import { getProductImageSources } from '../../utils/productImages';

interface ProductCardProps {
  product: Product;
  onToggleFavorite?: (productId: string) => void;
  isFavorite?: boolean;
}

export default function ProductCard({
  product,
  onToggleFavorite,
  isFavorite = false,
}: ProductCardProps) {
  const navigate = useNavigate();
  const [isHovered, setIsHovered] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const { currentCurrency, exchangeRates } = useCurrencyStore();

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;
  const productImages = getProductImageSources(product);
  const primaryImage = productImages[0] ?? { src: placeholderImage };
  const secondaryImage = productImages[1] ?? primaryImage;

  const sizeOptions = Array.from(
    new Set(
      (product.variants || [])
        .map((v) => v.size)
        .filter((v): v is string => Boolean(v))
    )
  );

  // Get unique colors with hex values
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
    image.src = placeholderImage;
    image.onerror = null;
  };

  const displayPrice = product.variants?.[0]?.price || product.base_price;
  const comparePrice = product.variants?.[0]?.compare_at_price;
  const hasDiscount = comparePrice && comparePrice > displayPrice;

  const handleToggleFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(product.id);
  };

  return (
    <Link
      to={`/products/${product.id}`}
      className="group block"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Image Container */}
      <div className="relative overflow-hidden aspect-[3/4] mb-4 bg-gray-100">
        {/* Made to Order Badge - Top Left */}
        {product.made_to_order && (
          <div className="absolute top-3 left-3 z-20">
            <span className="px-2 py-1 bg-blue-600 text-white text-[10px] font-serif uppercase tracking-[0.15em] rounded shadow-md">
              MADE TO ORDER
            </span>
          </div>
        )}

        {/* Loading Skeleton */}
        {!imageLoaded && (
          <div className="absolute inset-0 bg-gradient-to-br from-gray-100 via-gray-50 to-gray-100 animate-pulse" />
        )}

        {/* Primary Image */}
        <img
          src={primaryImage.src}
          alt={product.title}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 z-0 ${
            isHovered && secondaryImage.src !== primaryImage.src ? 'opacity-0' : 'opacity-100'
          }`}
          onError={(event) => handleImageError(event, primaryImage.fallbackSrc)}
          onLoad={() => setImageLoaded(true)}
          style={{ display: imageLoaded ? 'block' : 'block' }}
        />

        {/* Secondary Image (shown on hover) */}
        {secondaryImage.src !== primaryImage.src && imageLoaded && (
          <img
            src={secondaryImage.src}
            alt={product.title}
            className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 z-0 ${
              isHovered ? 'opacity-100' : 'opacity-0'
            }`}
            onError={(event) => handleImageError(event, secondaryImage.fallbackSrc)}
          />
        )}

        {/* Favorite Button - Top Right */}
        <button
          onClick={handleToggleFavorite}
          className="absolute top-3 right-3 w-9 h-9 flex items-center justify-center transition-opacity hover:opacity-80 z-20"
          aria-label="Add to favorites"
        >
          <Bookmark
            className={`w-5 h-5 ${
              isFavorite ? 'fill-primary stroke-primary' : 'stroke-white fill-none'
            }`}
            style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.2))' }}
          />
        </button>

        {/* Hover Overlay - Bottom Panel with Sizes/Colors (only show if product has variants) */}
        {(sizeOptions.length > 0 || colorOptions.length > 0) && (
          <div
            className={`absolute bottom-0 left-0 right-0 bg-white transition-transform duration-300 z-10 ${
              isHovered ? 'translate-y-0' : 'translate-y-full'
            }`}
          >
            <div className="px-4 py-4 space-y-4">
              {/* Sizes */}
              {sizeOptions.length > 0 && (
                <div className="text-center">
                  <p className="text-[10px] font-serif uppercase tracking-[0.15em] text-dark mb-2">
                    SIZES
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {sizeOptions.map((size) => (
                      <span
                        key={size}
                        className="text-xs font-serif text-dark"
                      >
                        {size}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Colors */}
              {colorOptions.length > 0 && (
                <div className="text-center">
                  <p className="text-[10px] font-serif uppercase tracking-[0.15em] text-dark mb-2">
                    COLORS
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {colorOptions.map((colorOption) => (
                      <div
                        key={colorOption.color}
                        className="flex flex-col items-center"
                      >
                        {hasSolidColorHex(colorOption.hex) ? (
                          <span
                            className="w-6 h-6 border border-gray-300"
                            style={{ backgroundColor: colorOption.hex! }}
                            title={colorOption.color}
                          />
                        ) : (
                          <span className="rounded-full border border-gray-200 px-2 py-1 text-[10px] font-medium uppercase tracking-[0.08em] text-dark">
                            {colorOption.color}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Add to Bag Button */}
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  navigate(`/products/${product.id}`);
                }}
                className="w-full py-2.5 bg-primary text-white text-[10px] font-serif uppercase tracking-[0.15em] hover:bg-primary-dark transition-colors"
              >
                ADD TO BAG
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Product Info */}
      <div className="space-y-1.5">
        {/* Brand/Vendor */}
        <p className="text-[10px] font-ui uppercase tracking-[0.25em] text-primary">
          {product.vendor_name || 'SHOPSOMA'}
        </p>

        {/* Title */}
        <h3 className="text-sm font-serif text-dark leading-snug line-clamp-2">
          {product.title}
        </h3>

        {/* Price */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-ui text-dark">
            {formatPriceWithConversion(displayPrice, product.currency, currentCurrency, exchangeRates)}
          </span>
          {hasDiscount && comparePrice && (
            <span className="text-xs font-ui text-gray-400 line-through">
              {formatPriceWithConversion(comparePrice, product.currency, currentCurrency, exchangeRates)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
