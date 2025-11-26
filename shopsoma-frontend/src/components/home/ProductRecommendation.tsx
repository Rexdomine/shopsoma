import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Product } from '../../types';
import { productService } from '../../services/productService';
import Loading from '../common/Loading';
import { ROUTES } from '../../config/constants';
import ProductCard from '../products/ProductCard';
import { useWishlistActions } from '../../hooks/useWishlistActions';
import { useAuth } from '../../context/AuthContext';
import { getPreferences, type PreferenceData } from '../../services/preferenceService';
import { personalizeProducts } from '../../utils/preferenceHelpers';
import { usePreferenceStore } from '../../store/preferenceStore';

export default function ProductRecommendation() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [preferenceMeta, setPreferenceMeta] = useState<{ designersActive: boolean; designerNames: string[] }>({
    designersActive: false,
    designerNames: [],
  });
  const [preference, setPreference] = useState<PreferenceData | null>(null);
  const [preferencesReady, setPreferencesReady] = useState(false);
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
        console.error('Failed to load preferences for recommendations:', prefError);
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
    const loadProducts = async () => {
      if (!preferencesReady) return;
      try {
        setLoading(true);
        const data = await productService.getFeaturedProducts(8);
        const personalized = preference ? personalizeProducts(data, preference) : data;
        if (!cancelled) {
          setProducts(personalized);
          setError(null);
        }
      } catch (err) {
        console.error('Failed to load products:', err);
        if (!cancelled) {
          setProducts([]);
          setError("We couldn't load curated picks. Please try again shortly.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadProducts();
    return () => {
      cancelled = true;
    };
  }, [preference, preferencesReady]);

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
              'No recommendations yet. Check back after vendors upload more looks.'
            )}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 lg:gap-6">
              {products.map((product) => (
                <ProductCard
                  key={product.id}
                  product={product}
                  onToggleFavorite={toggleFavorite}
                  isFavorite={favorites.has(product.id)}
                />
              ))}
            </div>

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
