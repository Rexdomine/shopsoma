import { useEffect, useMemo, useState } from 'react';
import Loading from '../../components/common/Loading';
import { WOMEN_HERO_IMAGE_URL, WOMEN_HERO_MOBILE_IMAGE_URL } from '../../config/constants';
import {
  DEFAULT_WOMEN_SUBCATEGORIES,
  WOMEN_CATEGORY_ID,
  WOMEN_CHILD_CATEGORIES,
  mergeSubcategoriesWithDefaults,
} from '../../config/categoryNavigation';
import { categoryService } from '../../services/categoryService';
import type { Category } from '../../types';
import ProductList from './ProductList';

export default function WomenStorefront() {
  const [womenCategoryId, setWomenCategoryId] = useState<string | null>(WOMEN_CATEGORY_ID);
  const [categoryLoading, setCategoryLoading] = useState(false);
  const [subcategories, setSubcategories] = useState<Category[]>(() => {
    const cacheKey = `shopsoma_subcategories_${WOMEN_CATEGORY_ID}`;
    const cachedRaw = typeof window !== 'undefined' ? sessionStorage.getItem(cacheKey) : null;
    if (cachedRaw) {
      try {
        const cached = JSON.parse(cachedRaw) as { categories: Category[] };
        if (cached?.categories?.length) {
          return mergeSubcategoriesWithDefaults(cached.categories, DEFAULT_WOMEN_SUBCATEGORIES);
        }
      } catch {
        sessionStorage.removeItem(cacheKey);
      }
    }
    return DEFAULT_WOMEN_SUBCATEGORIES;
  });

  useEffect(() => {
    const loadPrimaryCategories = async () => {
      const cacheKey = 'shopsoma_primary_categories';
      const cachedRaw = sessionStorage.getItem(cacheKey);
      let resolvedId: string | null = null;
      if (cachedRaw) {
        try {
          const cached = JSON.parse(cachedRaw) as { categories: { id: string; name?: string }[] };
          const cachedWomen = cached.categories.find(
            (category) => category.name?.toLowerCase() === 'women'
          );
          if (cachedWomen?.id) {
            resolvedId = cachedWomen.id;
            setWomenCategoryId(cachedWomen.id);
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
        if (womenCategory?.id) {
          setWomenCategoryId(womenCategory.id);
        }
        sessionStorage.setItem(
          cacheKey,
          JSON.stringify({ categories: categories.map(({ id, name }) => ({ id, name })) })
        );
      } catch (error) {
        if (!resolvedId) {
          console.error('Failed to load primary categories for women storefront', error);
        }
      } finally {
        setCategoryLoading(false);
      }
    };

    loadPrimaryCategories();
  }, []);

  useEffect(() => {
    const targetId = womenCategoryId || WOMEN_CATEGORY_ID;

    const loadSubcategories = async () => {
      const cacheKey = `shopsoma_subcategories_${targetId}`;
      const cachedRaw = sessionStorage.getItem(cacheKey);
      if (cachedRaw) {
        try {
          const cached = JSON.parse(cachedRaw) as { categories: Category[] };
          if (cached?.categories?.length) {
            setSubcategories(mergeSubcategoriesWithDefaults(cached.categories, DEFAULT_WOMEN_SUBCATEGORIES));
          }
        } catch {
          sessionStorage.removeItem(cacheKey);
        }
      }

      try {
        const categories = await categoryService.getSubcategories(targetId);
        const merged = mergeSubcategoriesWithDefaults(categories, DEFAULT_WOMEN_SUBCATEGORIES);
        setSubcategories(merged);
        sessionStorage.setItem(cacheKey, JSON.stringify({ categories: merged }));
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
      childCategoryOverrides={WOMEN_CHILD_CATEGORIES}
      heroOverride={{
        title: 'Womenswear for every style',
        body: 'Explore SHOPSOMA’s hand-picked selections for every style',
        imageUrl: WOMEN_HERO_IMAGE_URL,
        mobileImageUrl: WOMEN_HERO_MOBILE_IMAGE_URL,
        imagePositionClassName: 'object-[40%_0%] max-sm:object-[36%_42%]',
        ctaLabel: 'Shop all womenswear',
      }}
    />
  );
}
