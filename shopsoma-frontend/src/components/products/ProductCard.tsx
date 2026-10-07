import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { Product, ProductVariant } from '../../types';
import { Bookmark } from 'lucide-react';
import { IMAGE_CONFIG } from '../../config/constants';
import { useCurrencyStore } from '../../store/currencyStore';
import { useCartStore } from '../../store/cartStore';
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
  const location = useLocation();
  const [isHovered, setIsHovered] = useState(false);
  const [imageLoaded, setImageLoaded] = useState(false);
  const [selectedSize, setSelectedSize] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string | null>(null);
  const [isAdded, setIsAdded] = useState(false);

  const { currentCurrency, exchangeRates } = useCurrencyStore();
  const addItem = useCartStore((state) => state.addItem);

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;
  const productImages = getProductImageSources(product, 'high');
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

  const isSingleProduct = !product.variations || product.variations.length === 0;
  const displayPrice = (isSingleProduct && product.base_price != null)
    ? product.base_price
    : (product.variants?.[0]?.price || product.base_price);
  const comparePrice = (isSingleProduct && product.compare_at_price != null)
    ? product.compare_at_price
    : product.variants?.[0]?.compare_at_price;
  const hasDiscount = Boolean(comparePrice && comparePrice > displayPrice);

  const resolveVariant = (): ProductVariant => {
    const variants = product.variants || [];
    if (variants.length === 0) {
      return {
        id: `default-${product.id}`,
        product_id: product.id,
        price: product.base_price,
        compare_at_price: product.compare_at_price,
        stock: product.total_stock,
        is_available: product.made_to_order ? true : (product.total_stock ?? 0) > 0,
      } as ProductVariant;
    }

    const currentSize = selectedSize || sizeOptions[0] || null;
    const currentColor = selectedColor || colorOptions[0]?.color || null;

    let matchedVariant: ProductVariant | undefined;

    if (currentSize && currentColor) {
      matchedVariant = variants.find(
        (v) =>
          v.size?.trim().toLowerCase() === currentSize.trim().toLowerCase() &&
          v.color?.trim().toLowerCase() === currentColor.trim().toLowerCase()
      );
    }

    if (!matchedVariant && currentSize) {
      matchedVariant = variants.find(
        (v) => v.size?.trim().toLowerCase() === currentSize.trim().toLowerCase()
      );
    }

    if (!matchedVariant && currentColor) {
      matchedVariant = variants.find(
        (v) => v.color?.trim().toLowerCase() === currentColor.trim().toLowerCase()
      );
    }

    const baseVariant = matchedVariant || variants[0];
    const resolvedPrice = (isSingleProduct && product.base_price != null)
      ? product.base_price
      : (baseVariant.price ?? product.base_price);
    const resolvedComparePrice = (isSingleProduct && product.compare_at_price != null)
      ? product.compare_at_price
      : (baseVariant.compare_at_price ?? product.compare_at_price);

    return {
      ...baseVariant,
      price: resolvedPrice,
      compare_at_price: resolvedComparePrice,
    };
  };

  const handleAddToBag = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    const variant = resolveVariant();
    addItem({
      product,
      variant,
      quantity: 1,
    });

    setIsAdded(true);
    setTimeout(() => setIsAdded(false), 1800);
  };

  const handleToggleFavorite = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggleFavorite?.(product.id);
  };

  return (
    <Link
      to={`/products/${product.id}`}
      state={{ from: `${location.pathname}${location.search}` }}
      className="group block w-full min-w-0"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Image Container */}
      <div className="relative overflow-hidden aspect-[3/4] mb-3 sm:mb-4 bg-gray-100">
        {/* Made to Order Badge - Top Left */}
        {product.made_to_order && (
          <div className="absolute top-2 sm:top-3 left-2 sm:left-3 z-20">
            <span className="px-1.5 sm:px-2 py-0.5 sm:py-1 bg-blue-600 text-white text-[9px] sm:text-[10px] font-serif uppercase tracking-[0.15em] rounded shadow-md">
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
          className="absolute top-2 sm:top-3 right-2 sm:right-3 w-8 sm:w-9 h-8 sm:h-9 flex items-center justify-center transition-opacity hover:opacity-80 z-20"
          aria-label="Add to favorites"
        >
          <Bookmark
            className={`w-4 sm:w-5 h-4 sm:h-5 ${
              isFavorite ? 'fill-primary stroke-primary' : 'stroke-white fill-none'
            }`}
            style={{ filter: 'drop-shadow(0 1px 2px rgba(0,0,0,0.2))' }}
          />
        </button>

        {/* Hover Overlay - Bottom Panel with Sizes/Colors */}
        <div
          className={`absolute bottom-0 left-0 right-0 bg-white transition-transform duration-300 z-10 ${
            isHovered ? 'translate-y-0' : 'translate-y-full'
          }`}
        >
          <div className="px-4 py-4 space-y-3">
            {/* Sizes */}
            {sizeOptions.length > 0 && (
              <div className="text-center">
                <p className="text-[10px] font-serif uppercase tracking-[0.15em] text-dark mb-2">
                  SIZES
                </p>
                <div className="flex flex-wrap gap-1.5 justify-center">
                  {sizeOptions.map((size) => {
                    const isSelected = (selectedSize ?? sizeOptions[0]) === size;
                    return (
                      <button
                        type="button"
                        key={size}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedSize(size);
                        }}
                        className={`text-xs font-serif px-2 py-0.5 rounded transition-colors ${
                          isSelected
                            ? 'bg-primary text-white font-medium shadow-sm'
                            : 'text-dark hover:bg-gray-100'
                        }`}
                      >
                        {size}
                      </button>
                    );
                  })}
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
                  {colorOptions.map((colorOption) => {
                    const isSelected =
                      (selectedColor ?? colorOptions[0]?.color) === colorOption.color;
                    return (
                      <button
                        type="button"
                        key={colorOption.color}
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedColor(colorOption.color);
                        }}
                        className={`flex flex-col items-center p-0.5 rounded transition ${
                          isSelected
                            ? 'ring-2 ring-primary ring-offset-1'
                            : 'opacity-85 hover:opacity-100'
                        }`}
                        title={colorOption.color}
                        aria-label={`Select color ${colorOption.color}`}
                      >
                        {hasSolidColorHex(colorOption.hex) ? (
                          <span
                            className="w-6 h-6 border border-gray-300 block"
                            style={{ backgroundColor: colorOption.hex! }}
                          />
                        ) : (
                          <span
                            className={`rounded-full border px-2 py-1 text-[10px] font-medium uppercase tracking-[0.08em] ${
                              isSelected
                                ? 'border-primary bg-primary text-white'
                                : 'border-gray-200 text-dark'
                            }`}
                          >
                            {colorOption.color}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Add to Bag Button */}
            <button
              type="button"
              onClick={handleAddToBag}
              className={`w-full py-2.5 text-[10px] font-serif uppercase tracking-[0.15em] transition-colors ${
                isAdded
                  ? 'bg-green-700 text-white font-semibold'
                  : 'bg-primary text-white hover:bg-primary-dark'
              }`}
            >
              {isAdded ? 'ADDED TO BAG ✓' : 'ADD TO BAG'}
            </button>
          </div>
        </div>
      </div>

      {/* Product Info */}
      <div className="space-y-1 sm:space-y-1.5 min-w-0">
        {/* Brand/Vendor */}
        <p className="text-[9px] sm:text-[10px] font-ui uppercase tracking-[0.2em] sm:tracking-[0.25em] text-primary truncate">
          {product.vendor_name || 'SHOPSOMA'}
        </p>

        {/* Title */}
        <h3 className="text-xs sm:text-sm font-serif text-dark leading-snug line-clamp-2 break-words">
          {product.title}
        </h3>

        {/* Price */}
        <div className="flex flex-wrap items-center gap-1 sm:gap-2">
          <span className="text-xs sm:text-sm font-ui text-dark font-medium whitespace-nowrap">
            {formatPriceWithConversion(displayPrice, product.currency, currentCurrency, exchangeRates)}
          </span>
          {hasDiscount && comparePrice && (
            <span className="text-[10px] sm:text-xs font-ui text-gray-400 line-through whitespace-nowrap">
              {formatPriceWithConversion(comparePrice, product.currency, currentCurrency, exchangeRates)}
            </span>
          )}
        </div>
      </div>
    </Link>
  );
}
