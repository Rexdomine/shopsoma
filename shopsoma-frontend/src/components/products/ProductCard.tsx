import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Product } from '../../types';
import { Heart, ShoppingCart } from 'lucide-react';
import { IMAGE_CONFIG } from '../../config/constants';

interface ProductCardProps {
  product: Product;
  onAddToCart?: (productId: string) => void;
  onToggleFavorite?: (productId: string) => void;
  isFavorite?: boolean;
}

export default function ProductCard({
  product,
  onAddToCart,
  onToggleFavorite,
  isFavorite = false,
}: ProductCardProps) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;
  const primaryImage = product.images?.[0]?.image_url || placeholderImage;
  const secondaryImage = product.images?.[1]?.image_url || primaryImage;

  const handleImageError = (event: React.SyntheticEvent<HTMLImageElement>) => {
    event.currentTarget.src = placeholderImage;
    event.currentTarget.onerror = null;
  };

  const displayPrice = product.variants?.[0]?.price || product.base_price;
  const comparePrice = product.variants?.[0]?.compare_at_price;
  const hasDiscount = comparePrice && comparePrice > displayPrice;

  const handleAddToCart = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onAddToCart?.(product.id);
  };

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
      <div className="relative overflow-hidden bg-gray-100 rounded-lg aspect-[3/4] mb-3">
        {/* Product Images */}
        <img
          src={primaryImage}
          alt={product.title}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-500 ${
            isHovered && secondaryImage !== primaryImage ? 'opacity-0' : 'opacity-100'
          } ${imageLoaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setImageLoaded(true)}
          onError={handleImageError}
        />
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

        {/* Discount Badge */}
        {hasDiscount && (
          <div className="absolute top-3 left-3 bg-red-500 text-white px-2 py-1 text-xs font-semibold rounded">
            {Math.round(((comparePrice - displayPrice) / comparePrice) * 100)}% OFF
          </div>
        )}

        {/* Out of Stock Badge */}
        {product.inventory_quantity === 0 && (
          <div className="absolute top-3 left-3 bg-gray-800 text-white px-2 py-1 text-xs font-semibold rounded">
            OUT OF STOCK
          </div>
        )}

        {/* Favorite Button */}
        <button
          onClick={handleToggleFavorite}
          className="absolute top-3 right-3 w-9 h-9 bg-white rounded-full flex items-center justify-center shadow-md opacity-0 group-hover:opacity-100 transition-opacity duration-300 hover:scale-110 transform"
          aria-label="Add to favorites"
        >
          <Heart
            className={`w-5 h-5 ${
              isFavorite ? 'fill-red-500 text-red-500' : 'text-gray-700'
            }`}
          />
        </button>

        {/* Quick Add to Cart */}
        {product.inventory_quantity > 0 && (
          <button
            onClick={handleAddToCart}
            className="absolute bottom-0 left-0 right-0 bg-primary text-white py-3.5 font-body font-semibold opacity-0 group-hover:opacity-100 translate-y-full group-hover:translate-y-0 transition-all duration-300 flex items-center justify-center gap-2 hover:bg-primary-dark shadow-lg"
          >
            <ShoppingCart className="w-4 h-4" />
            Add to Cart
          </button>
        )}
      </div>

      {/* Product Info */}
      <div className="space-y-1">
        <h3 className="text-sm font-body font-medium text-dark line-clamp-2 group-hover:text-primary transition-colors">
          {product.title}
        </h3>

        {product.category && (
          <p className="text-xs font-body text-light uppercase tracking-wide">
            {product.category}
          </p>
        )}

        <div className="flex items-center gap-2 pt-1">
          <span className="text-base font-body font-semibold text-dark">
            ₦{displayPrice.toLocaleString()}
          </span>
          {hasDiscount && (
            <span className="text-sm font-body text-light line-through">
              ₦{comparePrice.toLocaleString()}
            </span>
          )}
        </div>

        {/* Rating */}
        {product.average_rating && product.average_rating > 0 && (
          <div className="flex items-center gap-1 text-xs text-gray-600">
            <span className="text-yellow-500">★</span>
            <span>{product.average_rating.toFixed(1)}</span>
            {product.review_count && product.review_count > 0 && (
              <span className="text-gray-400">({product.review_count})</span>
            )}
          </div>
        )}
      </div>
    </Link>
  );
}
