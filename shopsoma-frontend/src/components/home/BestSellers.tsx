import { useEffect, useState, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import Loading from '../common/Loading';
import ProductCard from '../products/ProductCard';
import { useWishlistActions } from '../../hooks/useWishlistActions';
import { useAuth } from '../../context/AuthContext';
import { getPreferences, type PreferenceData } from '../../services/preferenceService';
import { personalizeProducts } from '../../utils/preferenceHelpers';
import { usePreferenceStore } from '../../store/preferenceStore';

export default function BestSellers() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [preferenceMeta, setPreferenceMeta] = useState<{ designersActive: boolean; designerNames: string[] }>({
    designersActive: false,
    designerNames: [],
  });
  const [preference, setPreference] = useState<PreferenceData | null>(null);
  const [preferencesReady, setPreferencesReady] = useState(false);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const { favorites, toggleFavorite } = useWishlistActions();
  const { isAuthenticated } = useAuth();
  const setStoredInterest = usePreferenceStore((state) => state.setInterest);
  const setStoredCurrency = usePreferenceStore((state) => state.setCurrency);
  const setStoredDesigners = usePreferenceStore((state) => state.setDesigners);
  const setStoredCategories = usePreferenceStore((state) => state.setCategories);

  useEffect(() => {
    let cancelled = false;

    const hydratePreferences = async () => {
      setPreferencesReady(false);
      if (!isAuthenticated) {
        if (!cancelled) {
          setPreference(null);
          setPreferenceMeta({ designersActive: false, designerNames: [] });
          setPreferencesReady(true);
        }
        return;
      }

      try {
        const pref = await getPreferences();
        if (cancelled) return;
        const resolvedInterest = pref.interest === 'menswear' ? 'menswear' : 'womenswear';
        const resolvedCurrency = pref.preferredCurrency?.toUpperCase() === 'USD' ? 'USD' : 'NGN';
        const resolvedDesigners = pref.favoriteDesigners ?? [];
        const resolvedCategories = pref.favoriteCategories ?? [];

        setStoredInterest(resolvedInterest);
        setStoredCurrency(resolvedCurrency);
        setStoredDesigners(resolvedDesigners);
        setStoredCategories(resolvedCategories);

        setPreference({
          interest: resolvedInterest,
          preferredLanguage: pref.preferredLanguage,
          preferredCurrency: resolvedCurrency,
          favoriteDesigners: resolvedDesigners,
          favoriteCategories: resolvedCategories,
        });

        setPreferenceMeta({
          designersActive: resolvedDesigners.length > 0,
          designerNames: resolvedDesigners,
        });
      } catch (prefError) {
        console.error('Failed to load preferences for hot items:', prefError);
        if (!cancelled) {
          setPreference(null);
          setPreferenceMeta({ designersActive: false, designerNames: [] });
        }
      } finally {
        if (!cancelled) {
          setPreferencesReady(true);
        }
      }
    };

    hydratePreferences();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, setStoredInterest, setStoredCurrency, setStoredDesigners, setStoredCategories]);

  useEffect(() => {
    let cancelled = false;
    const loadHotItems = async () => {
      if (!preferencesReady) return;
      try {
        setLoading(true);
        const response = await productService.getProducts({
          page_size: 12,
          sort_by: 'orders_count',
          sort_order: 'desc',
        });
        const personalized = preference ? personalizeProducts(response.products, preference) : response.products;
        if (!cancelled) {
          setProducts(personalized);
        }
      } catch (err) {
        console.error('Failed to load hot items:', err);
        if (!cancelled) {
          setProducts([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadHotItems();
    return () => {
      cancelled = true;
    };
  }, [preference, preferencesReady]);

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

        {/* Empty State */}
        {products.length === 0 ? (
          <div className="text-center py-16 text-gray-500">
            {preferenceMeta.designersActive ? (
              <>
                <p className="text-base font-semibold text-dark">
                  We&apos;re curating looks from your favourite designers.
                </p>
                <p className="mt-2 text-sm text-gray-500">
                  {preferenceMeta.designerNames.join(', ')} have no collections live at the moment. Check back soon for
                  fresh arrivals tailored to you.
                </p>
              </>
            ) : (
              'No hot items available at the moment. Check back soon!'
            )}
          </div>
        ) : (
          <>
            {/* Carousel */}
            <div className="relative -mx-4 sm:mx-0">
              <div
                ref={scrollContainerRef}
                className="flex gap-4 overflow-x-auto scrollbar-hide scroll-smooth px-4 sm:px-0"
              >
                {products.map((product) => (
                  <div key={product.id} className="flex-none w-[280px]">
                    <ProductCard
                      product={product}
                      onToggleFavorite={toggleFavorite}
                      isFavorite={favorites.has(product.id)}
                    />
                  </div>
                ))}
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
          </>
        )}
      </div>
    </section>
  );
}
