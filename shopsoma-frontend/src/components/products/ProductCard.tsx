import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Product } from '../../types';
import { Heart } from 'lucide-react';
import { IMAGE_CONFIG } from '../../config/constants';
import { usePreferenceStore } from '../../store/preferenceStore';
import { formatPriceWithCurrency } from '../../utils/pricing';

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
  const [imageLoaded, setImageLoaded] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;
  const primaryImage = product.images?.[0]?.image_url || placeholderImage;
  const secondaryImage = product.images?.[1]?.image_url || primaryImage;

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

  const handleImageError = (event: React.SyntheticEvent<HTMLImageElement>) => {
    event.currentTarget.src = placeholderImage;
    event.currentTarget.onerror = null;
  };

  const displayPrice = product.variants?.[0]?.price || product.base_price;
  const comparePrice = product.variants?.[0]?.compare_at_price;
  const preferredCurrency = usePreferenceStore((state) => state.currency);
  const hasDiscount = comparePrice && comparePrice > displayPrice;

  const handleToggleFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(product.id);
  };

  // Determine availability tag based on stock and product metadata
  const getAvailabilityTag = () => {
    if (product.inventory_quantity === 0) return 'Pre-order';
    if (product.is_featured) return 'New Season';
    // You can add more logic here based on product metadata
    return 'Exclusive';
  };

  const availabilityTag = getAvailabilityTag();

  return (
    <Link
      to={`/products/${product.id}`}
      className="group block"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Image Container - No rounded edges, border only */}
      <div className="relative overflow-hidden aspect-[3/4] mb-3 border border-gray-200">
        {/* Primary Image */}
        <img
          src={primaryImage}
          alt={product.title}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-500 ${
            isHovered && secondaryImage !== primaryImage ? 'opacity-0' : 'opacity-100'
          } ${imageLoaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setImageLoaded(true)}
          onError={handleImageError}
        />

        {/* Secondary Image (shown on hover) */}
        {secondaryImage !== primaryImage && (
          <img
            src={secondaryImage}
            alt={product.title}
            className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-500 ${
              isHovered ? 'opacity-100' : 'opacity-0'
            }`}
            onError={handleImageError}
          />
        )}

        {/* Hover Overlay with Variants */}
        {isHovered && (sizeOptions.length > 0 || colorOptions.length > 0) && (
          <div className="absolute bottom-0 left-0 right-0 bg-white/95 backdrop-blur-sm p-4 transition-all duration-300">
            <div className="flex items-start justify-between">
              {/* Color Swatches - Left */}
              {colorOptions.length > 0 && (
                <div className="flex-shrink-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-2">
                    Colors
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {colorOptions.map((colorOption) => (
                      <div
                        key={colorOption.color}
                        className="w-6 h-6 rounded-full border-2 border-gray-300"
                        style={{ backgroundColor: colorOption.hex ?? '#f5f5f5' }}
                        title={colorOption.color}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Size Options - Right */}
              {sizeOptions.length > 0 && (
                <div className="flex-shrink-0 text-right">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-2">
                    All Sizes
                  </p>
                  <div className="flex flex-wrap gap-2 justify-end">
                    {sizeOptions.map((size) => (
                      <span
                        key={size}
                        className="text-xs font-medium text-dark"
                      >
                        {size}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Favorite Button - Top Right */}
        <button
          onClick={handleToggleFavorite}
          className="absolute top-3 right-3 w-10 h-10 flex items-center justify-center transition-opacity"
          aria-label="Add to favorites"
        >
          <Heart
            className={`w-6 h-6 ${
              isFavorite ? 'fill-primary stroke-primary' : 'stroke-dark fill-none'
            }`}
          />
        </button>
      </div>

      {/* Product Info - Clean, no background */}
      <div className="space-y-1">
        {/* Brand/Vendor */}
        <p className="text-xs uppercase tracking-wider text-gray-500">
          {product.vendor_name || 'THE CORE'}
        </p>

        {/* Title */}
        <h3 className="text-sm font-medium text-dark leading-tight">
          {product.title}
        </h3>

        {/* Price */}
        <div className="flex items-center gap-2 pt-1">
          <span className="text-base font-semibold text-dark">
            {formatPriceWithCurrency(displayPrice, preferredCurrency)}
          </span>
          {hasDiscount && comparePrice && (
            <span className="text-sm text-gray-400 line-through">
              {formatPriceWithCurrency(comparePrice, preferredCurrency)}
            </span>
          )}
        </div>

        {/* Availability Tags */}
        <div className="flex flex-wrap gap-2 pt-2">
          <span className="px-3 py-1 border border-gray-300 text-xs font-medium text-dark">
            {availabilityTag}
          </span>
          {hasDiscount && (
            <span className="px-3 py-1 border border-gray-300 text-xs font-medium text-dark">
              On Sale
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
