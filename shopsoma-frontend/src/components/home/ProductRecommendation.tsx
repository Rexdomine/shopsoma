import { useEffect, useState } from 'react';
import { Heart } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import Loading from '../common/Loading';
import { IMAGE_CONFIG, ROUTES } from '../../config/constants';

type RecommendedProduct = {
  id: string;
  title: string;
  description: string;
  price: number;
  comparePrice?: number | null;
  image?: string | null;
  isHighlighted?: boolean;
};

export default function ProductRecommendation() {
  const [products, setProducts] = useState<RecommendedProduct[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());

  const placeholderImage = IMAGE_CONFIG.PLACEHOLDER;

  useEffect(() => {
    loadProducts();
  }, []);

  const loadProducts = async () => {
    try {
      setLoading(true);
      const data = await productService.getFeaturedProducts(8);
      const formatted = formatProducts(data);
      setProducts(formatted);
      setError(null);
    } catch (err) {
      console.error('Failed to load products:', err);
      setProducts([]);
      setError('We couldn’t load curated picks. Please try again shortly.');
    } finally {
      setLoading(false);
    }
  };

  const formatProducts = (items: Product[]): RecommendedProduct[] => {
    return items
      .map((product) => {
        const firstVariant = product.variants?.[0];
        const price = Number(firstVariant?.price ?? product.base_price ?? 0);
        const comparePrice =
          firstVariant?.compare_at_price ?? product.compare_at_price ?? undefined;

        return {
          id: product.id,
          title: product.title,
          description:
            product.description ??
            'Thoughtfully crafted for the modern wardrobe.',
          price,
          comparePrice,
          image: product.images?.[0]?.image_url ?? null,
          isHighlighted: product.is_featured,
        };
      })
      .slice(0, 8);
  };

  const toggleFavorite = (id: string) => {
    setFavoriteIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (loading) {
    return (
      <section className="py-12 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Loading size="lg" message="Loading recommendations..." />
        </div>
      </section>
    );
  }

  return (
    <section className="py-12 bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="text-center mb-10">
          <h2 className="text-2xl lg:text-3xl font-display font-bold text-dark mb-2 tracking-wide">
            Product Recommendation
          </h2>
          <p className="text-sm text-gray-600">
            Discover what our curators are loving from the live catalog.
          </p>
          {error && (
            <p className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 inline-flex px-3 py-1 rounded-full">
              {error}
            </p>
          )}
        </div>

        {products.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            No recommendations yet. Check back after vendors upload more looks.
          </div>
        ) : (
          <>
            {/* Product Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 lg:gap-6">
              {products.map((product, index) => {
                const isFavorite = favoriteIds.has(product.id);
                const showCompare =
                  product.comparePrice !== undefined &&
                  product.comparePrice !== null &&
                  product.comparePrice > product.price;

                return (
                  <article
                    key={product.id}
                    className="group flex flex-col h-full rounded-2xl border border-gray-100 bg-white p-4 shadow-[0_12px_30px_rgba(16,94,83,0.06)] transition-all duration-300 hover:-translate-y-1 hover:shadow-[0_18px_40px_rgba(16,94,83,0.12)]"
                  >
                    <div className="relative w-full aspect-[3/4] rounded-xl overflow-hidden bg-[#f5f7f8]">
                      <Link to={`/products/${product.id}`}>
                        <img
                          src={product.image ?? placeholderImage}
                          alt={product.title}
                          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                          onError={(event) => {
                            event.currentTarget.src = placeholderImage;
                            event.currentTarget.onerror = null;
                          }}
                        />
                      </Link>
                      <button
                        type="button"
                        onClick={() => toggleFavorite(product.id)}
                        className={`absolute top-3 right-3 w-9 h-9 rounded-full flex items-center justify-center shadow-md transition-colors duration-200 ${
                          isFavorite ? 'bg-primary text-white' : 'bg-white text-gray-500'
                        }`}
                        aria-label="Toggle favorite"
                      >
                        <Heart className={`w-4 h-4 ${isFavorite ? 'fill-current' : ''}`} />
                      </button>
                    </div>

                    <div className="mt-4 space-y-2">
                      <p className="text-[11px] font-semibold tracking-[0.24em] text-gray-500 uppercase">
                        curated pick #{index + 1}
                      </p>
                      <Link
                        to={`/products/${product.id}`}
                        className="block text-sm font-display font-semibold text-dark leading-snug line-clamp-2 hover:text-primary transition-colors"
                      >
                        {product.title}
                      </Link>
                      <p className="text-sm text-gray-500 line-clamp-2 min-h-[40px]">
                        {product.description}
                      </p>
                      <div className="flex items-end gap-2">
                        <span className="text-base font-semibold text-dark">
                          ₦{product.price.toLocaleString()}
                        </span>
                        {showCompare && (
                          <span className="text-xs text-gray-400 line-through">
                            ₦{product.comparePrice?.toLocaleString()}
                          </span>
                        )}
                      </div>
                    </div>

                    <Link
                      to={`/products/${product.id}`}
                      className="mt-auto w-full rounded-full border px-4 py-2.5 text-sm font-semibold transition-colors duration-200 border-primary text-primary hover:bg-primary hover:text-white text-center"
                    >
                      Buy Now
                    </Link>
                  </article>
                );
              })}
            </div>

            {/* View All Button */}
            <div className="text-center mt-8">
              <Link
                to={ROUTES.PRODUCTS}
                className="inline-flex items-center justify-center px-6 py-2 rounded-full border border-primary text-primary text-sm font-semibold hover:bg-primary hover:text-white transition-all duration-200"
              >
                View All Products
              </Link>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
