import { useEffect, useMemo, useState } from 'react';
import Loading from '../../components/common/Loading';
import { WOMEN_HERO_IMAGE_URL } from '../../config/constants';
import { categoryService } from '../../services/categoryService';
import type { Category } from '../../types';
import ProductList from './ProductList';

export default function WomenStorefront() {
  const [womenCategoryId, setWomenCategoryId] = useState<string | null>(null);
  const [categoryLoading, setCategoryLoading] = useState(true);
  const [subcategories, setSubcategories] = useState<Category[]>([]);

  useEffect(() => {
    const loadPrimaryCategories = async () => {
      const cacheKey = 'shopsoma_primary_categories';
      const cachedRaw = sessionStorage.getItem(cacheKey);
      let hasCached = false;
      if (cachedRaw) {
        try {
          const cached = JSON.parse(cachedRaw) as { categories: { id: string; name?: string }[] };
          const cachedWomen = cached.categories.find(
            (category) => category.name?.toLowerCase() === 'women'
          );
          if (cachedWomen?.id) {
            setWomenCategoryId(cachedWomen.id);
            setCategoryLoading(false);
            hasCached = true;
          }
        } catch {
          sessionStorage.removeItem(cacheKey);
        }
      }

      try {
        const categories = await categoryService.getPrimaryCategories();
        const womenCategory = categories.find(
          (category) => category.name?.toLowerCase() === 'women'
        );
        setWomenCategoryId(womenCategory?.id ?? null);
        sessionStorage.setItem(
          cacheKey,
          JSON.stringify({ categories: categories.map(({ id, name }) => ({ id, name })) })
        );
      } catch (error) {
        if (!hasCached) {
          console.error('Failed to load primary categories for women storefront', error);
        }
      } finally {
        setCategoryLoading(false);
      }
    };

    loadPrimaryCategories();
  }, []);

  useEffect(() => {
    if (!womenCategoryId) return;

    const loadSubcategories = async () => {
      const cacheKey = `shopsoma_subcategories_${womenCategoryId}`;
      const cachedRaw = sessionStorage.getItem(cacheKey);
      if (cachedRaw) {
        try {
          const cached = JSON.parse(cachedRaw) as { categories: Category[] };
          if (cached?.categories?.length) {
            setSubcategories(cached.categories);
          }
        } catch {
          sessionStorage.removeItem(cacheKey);
        }
      }

      try {
        const categories = await categoryService.getSubcategories(womenCategoryId);
        setSubcategories(categories);
        sessionStorage.setItem(cacheKey, JSON.stringify({ categories }));
      } catch (error) {
        console.error('Failed to load women subcategories for storefront', error);
      }
    };

    loadSubcategories();
  }, [womenCategoryId]);

  const initialParams = useMemo(
    () => (womenCategoryId ? { category_id: womenCategoryId } : undefined),
    [womenCategoryId]
  );

  if (categoryLoading && !womenCategoryId) {
    return <Loading fullScreen message="Loading women's collection..." />;
  }

  return (
    <ProductList
      presetCategory="Women"
      initialParams={initialParams}
      categoryNav={subcategories}
      heroOverride={{
        title: 'Womenswear: Effortless Elegance',
        body: 'Explore statement pieces, refined tailoring and everyday essentials crafted for modern women.',
        imageUrl: WOMEN_HERO_IMAGE_URL,
        ctaLabel: 'Shop all womenswear',
      }}
    />
  );
}
