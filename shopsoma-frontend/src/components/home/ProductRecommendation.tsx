import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import Loading from '../common/Loading';
import { ROUTES } from '../../config/constants';
import ProductCard from '../products/ProductCard';

export default function ProductRecommendation() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadProducts();
  }, []);

  const loadProducts = async () => {
    try {
      setLoading(true);
      const data = await productService.getFeaturedProducts(8);
      setProducts(data);
      setError(null);
    } catch (err) {
      console.error('Failed to load products:', err);
      setProducts([]);
      setError("We couldn't load curated picks. Please try again shortly.");
    } finally {
      setLoading(false);
    }
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
              {products.map((product) => {
                const isFavorite = favoriteIds.has(product.id);

                return (
                  <ProductCard
                    key={product.id}
                    product={product}
                    onToggleFavorite={toggleFavorite}
                    isFavorite={isFavorite}
                  />
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
