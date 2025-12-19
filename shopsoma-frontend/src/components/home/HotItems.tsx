import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import ProductCard from '../products/ProductCard';
import Loading from '../common/Loading';
import { ROUTES } from '../../config/constants';
import { useWishlistActions } from '../../hooks/useWishlistActions';
import { useAuth } from '../../context/AuthContext';
import { getPreferences, type PreferenceData } from '../../services/preferenceService';
import { personalizeProducts } from '../../utils/preferenceHelpers';
import { usePreferenceStore } from '../../store/preferenceStore';

export default function HotItems() {
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
          sort_by: 'created_at',
          sort_order: 'desc',
        });
        const items = preference ? personalizeProducts(response.products, preference) : response.products;
        if (!cancelled) {
          setProducts(items);
        }
      } catch (err) {
        console.error('Failed to load hot items:', err);
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

  if (loading) {
    return (
      <section className="py-12 bg-[var(--color-card-bg)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <Loading size="lg" message="Loading hot items..." />
        </div>
      </section>
    );
  }

  if (products.length === 0) {
    if (preferenceMeta.designersActive) {
      return (
        <section className="py-12 bg-[var(--color-section-alt-bg)]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <h2 className="text-2xl lg:text-3xl font-bold text-gray-900 mb-3">HOT ITEM</h2>
            <p className="text-sm text-gray-600 max-w-2xl mx-auto">
              We&apos;re keeping this space reserved for {preferenceMeta.designerNames.join(', ')}.
              Their collections are being refreshed—check back shortly for hot drops tailored to you.
            </p>
          </div>
        </section>
      );
    }
    return null;
  }

  return (
    <section className="py-12 bg-[var(--color-card-bg)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl lg:text-3xl font-display font-bold text-dark mb-1">HOT ITEM</h2>
            <p className="text-sm font-ui text-gray-700">Trending products right now</p>
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
              className="w-10 h-10 rounded-full bg-cta flex items-center justify-center hover:bg-cta-dark transition-all duration-200 shadow-md hover:shadow-lg"
              aria-label="Scroll right"
            >
              <ChevronRight className="w-5 h-5 text-white" />
            </button>
            <Link
              to={ROUTES.PRODUCTS}
              className="ml-2 px-7 py-3 bg-cta text-[var(--color-cta-text)] rounded-full text-sm font-ui font-semibold hover:bg-cta-dark transition-all duration-200 shadow-md hover:shadow-lg border border-cta"
            >
              See All Products
            </Link>
          </div>
        </div>

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
                  onToggleFavorite={toggleFavorite}
                  isFavorite={favorites.has(product.id)}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="md:hidden text-center mt-6">
          <Link
            to={ROUTES.PRODUCTS}
            className="inline-block px-7 py-3 bg-cta text-[var(--color-cta-text)] rounded-full text-sm font-ui font-semibold hover:bg-cta-dark transition-all duration-200 shadow-md hover:shadow-lg border border-cta"
          >
            See All Products
          </Link>
        </div>
      </div>
    </section>
  );
}
