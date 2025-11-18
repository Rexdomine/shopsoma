import { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import Loading from '../common/Loading';
import ProductCard from '../products/ProductCard';

export default function BestSellers() {
  const [products, setProducts] = useState<Product[]>([]);
  const [favoriteIds, setFavoriteIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

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
                <div key={product.id} className="flex-none w-[280px]">
                  <ProductCard
                    product={product}
                    onToggleFavorite={toggleFavorite}
                    isFavorite={isFavorite}
                  />
                </div>
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
