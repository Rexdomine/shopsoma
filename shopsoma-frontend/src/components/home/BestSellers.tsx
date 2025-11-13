import { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Heart } from 'lucide-react';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import Loading from '../common/Loading';
import { IMAGE_CONFIG } from '../../config/constants';

export default function BestSellers() {
  const [products, setProducts] = useState<Product[]>([]);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;

  useEffect(() => {
    loadHotItems();
  }, []);

  const loadHotItems = async () => {
    try {
      setLoading(true);
      const response = await productService.getProducts({
        page_size: 12,
        sort_by: 'orders_count',
        sort_order: 'desc',
      });
      setProducts(response.products);
    } catch (err) {
      console.error('Failed to load hot items:', err);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  };

  const scroll = (direction: 'left' | 'right') => {
    if (scrollContainerRef.current) {
      const scrollAmount = 320; // Card width + gap
      const newScrollPosition =
        scrollContainerRef.current.scrollLeft +
        (direction === 'left' ? -scrollAmount : scrollAmount);

      scrollContainerRef.current.scrollTo({
        left: newScrollPosition,
        behavior: 'smooth',
      });
    }
  };

  const toggleFavorite = (productId: string) => {
    setFavoriteIds((prev) => {
      const next = new Set(prev);
      if (next.has(productId)) {
        next.delete(productId);
      } else {
        next.add(productId);
      }
      return next;
    });
  };

  if (loading) {
    return (
      <section className="py-12 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Loading size="lg" message="Loading hot items..." />
        </div>
      </section>
    );
  }

  return (
    <section className="py-12 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-2xl lg:text-3xl font-display font-bold text-dark uppercase tracking-wide">
            HOT ITEM
          </h2>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-2">
            <button
              onClick={() => scroll('left')}
              className="w-9 h-9 rounded-full border border-gray-300 flex items-center justify-center hover:bg-gray-50 transition-colors"
              aria-label="Scroll left"
            >
              <ChevronLeft className="w-4 h-4 text-gray-700" />
            </button>
            <button
              onClick={() => scroll('right')}
              className="w-10 h-10 rounded-full bg-primary flex items-center justify-center hover:bg-primary-dark transition-all duration-200 shadow-md hover:shadow-lg"
              aria-label="Scroll right"
            >
              <ChevronRight className="w-5 h-5 text-white" />
            </button>
            <a
              href="/products"
              className="ml-2 px-7 py-3 bg-primary text-white rounded-full text-sm font-body font-semibold hover:bg-primary-dark transition-all duration-200 shadow-md hover:shadow-lg"
            >
              See All Products
            </a>
          </div>
        </div>

        {/* Carousel */}
        <div className="relative -mx-4 sm:mx-0">
          <div
            ref={scrollContainerRef}
            className="flex gap-4 overflow-x-auto scrollbar-hide scroll-smooth px-4 sm:px-0"
          >
            {products.map((product) => {
              const isFavorite = favoriteIds.has(product.id);
              return (
              <Link
                key={product.id}
                to={`/products/${product.id}`}
                className="group flex-none w-[280px] bg-white"
              >
                {/* Product Image */}
                <div className="relative aspect-square bg-gray-100 rounded-lg mb-3 overflow-hidden">
                  <img
                    src={product.images?.[0]?.image_url || placeholderImage}
                    alt={product.title}
                    crossOrigin="anonymous"
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                    onError={(e) => {
                      console.error('Image failed to load:', product.title, product.images?.[0]?.image_url);
                      e.currentTarget.src = placeholderImage;
                      e.currentTarget.onerror = null;
                    }}
                  />
                  <button
                    type="button"
                    className={`absolute top-3 right-3 w-9 h-9 rounded-full flex items-center justify-center shadow-md transition-colors duration-200 ${
                      isFavorite ? 'bg-primary text-white' : 'bg-white text-gray-500'
                    }`}
                    aria-label="Add to wishlist"
                    onClick={(event) => {
                      event.preventDefault();
                      toggleFavorite(product.id);
                    }}
                  >
                    <Heart className={`w-4 h-4 ${isFavorite ? 'fill-current' : ''}`} />
                  </button>
                </div>

                {/* Product Info */}
                <div className="text-center space-y-1">
                  <h3 className="font-body font-medium text-base text-dark line-clamp-1">
                    {product.title}
                  </h3>
                  <p className="text-sm font-body text-light">
                    {product.description ? product.description.substring(0, 30) + '...' : 'The specification here'}
                  </p>
                  <p className="text-lg font-body font-semibold text-dark pt-1">
                    ₦{(product.variants?.[0]?.price || product.base_price).toLocaleString()}
                  </p>
                </div>
              </Link>
            );
            })}
          </div>
        </div>

        {/* Mobile See All Button */}
        <div className="md:hidden text-center mt-6">
          <a
            href="/products"
            className="inline-block px-7 py-3 bg-primary text-white rounded-full text-sm font-body font-semibold hover:bg-primary-dark transition-all duration-200 shadow-md hover:shadow-lg"
          >
            See All Products
          </a>
        </div>
      </div>
    </section>
  );
}
