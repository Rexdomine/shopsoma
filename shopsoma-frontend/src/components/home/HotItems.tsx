import { useEffect, useState, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import ProductCard from '../products/ProductCard';
import Loading from '../common/Loading';
import { ROUTES } from '../../config/constants';

export default function HotItems() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadHotItems();
  }, []);

  const loadHotItems = async () => {
    try {
      setLoading(true);
      // Get products sorted by popularity or recent
      const response = await productService.getProducts({
        page_size: 12,
        sort_by: 'created_at',
        sort_order: 'desc',
      });
      setProducts(response.products);
    } catch (err) {
      console.error('Failed to load hot items:', err);
    } finally {
      setLoading(false);
    }
  };

  const scroll = (direction: 'left' | 'right') => {
    if (scrollContainerRef.current) {
      const scrollAmount = 400;
      const newScrollLeft =
        scrollContainerRef.current.scrollLeft +
        (direction === 'left' ? -scrollAmount : scrollAmount);

      scrollContainerRef.current.scrollTo({
        left: newScrollLeft,
        behavior: 'smooth',
      });
    }
  };

  const handleToggleFavorite = (productId: string) => {
    console.log('Toggle favorite:', productId);
    // TODO: Implement favorites functionality
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

  if (products.length === 0) {
    return null;
  }

  return (
    <section className="py-12 bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Section Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-1">
              HOT ITEM
            </h2>
            <p className="text-sm text-gray-600">Trending products right now</p>
          </div>

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
            <Link
              to={ROUTES.PRODUCTS}
              className="ml-2 px-7 py-3 bg-primary text-white rounded-full text-sm font-body font-semibold hover:bg-primary-dark transition-all duration-200 shadow-md hover:shadow-lg"
            >
              See All Products
            </Link>
          </div>
        </div>

        {/* Carousel */}
        <div className="relative -mx-4 sm:mx-0">
          <div
            ref={scrollContainerRef}
            className="flex gap-4 overflow-x-auto scrollbar-hide scroll-smooth px-4 sm:px-0"
            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
          >
            {products.map((product) => (
              <div key={product.id} className="flex-none w-64">
                <ProductCard
                  product={product}
                  onToggleFavorite={handleToggleFavorite}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Mobile See All Button */}
        <div className="md:hidden text-center mt-6">
          <Link
            to={ROUTES.PRODUCTS}
            className="inline-block px-7 py-3 bg-primary text-white rounded-full text-sm font-body font-semibold hover:bg-primary-dark transition-all duration-200 shadow-md hover:shadow-lg"
          >
            See All Products
          </Link>
        </div>
      </div>
    </section>
  );
}
