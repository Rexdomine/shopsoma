import { useEffect, useMemo, useState } from 'react';
import Loading from '../../components/common/Loading';
import { MEN_HERO_IMAGE_URL, MEN_HERO_MOBILE_IMAGE_URL } from '../../config/constants';
import {
  DEFAULT_MEN_SUBCATEGORIES,
  MEN_CATEGORY_ID,
  MEN_CHILD_CATEGORIES,
  mergeSubcategoriesWithDefaults,
} from '../../config/categoryNavigation';
import { categoryService } from '../../services/categoryService';
import ProductList from './ProductList';
import type { Category } from '../../types';

export default function MenStorefront() {
  const [menCategoryId, setMenCategoryId] = useState<string | null>(() => {
    if (typeof window === 'undefined') return MEN_CATEGORY_ID;
    const cacheKey = 'shopsoma_primary_categories';
    const cachedRaw = sessionStorage.getItem(cacheKey);
    if (cachedRaw) {
      try {
        const cached = JSON.parse(cachedRaw) as { categories: { id: string; name?: string }[] };
        const cachedMen = cached.categories?.find(
          (category) => category.name?.toLowerCase() === 'men'
        );
        if (cachedMen?.id) {
          return cachedMen.id;
        }
      } catch {
        sessionStorage.removeItem(cacheKey);
      }
    }
    return MEN_CATEGORY_ID;
  });
  const [categoryLoading, setCategoryLoading] = useState(false);
  const [subcategories, setSubcategories] = useState<Category[]>(() => {
    const cacheKey = `shopsoma_subcategories_${MEN_CATEGORY_ID}`;
    const cachedRaw = typeof window !== 'undefined' ? sessionStorage.getItem(cacheKey) : null;
    if (cachedRaw) {
      try {
        const cached = JSON.parse(cachedRaw) as { categories: Category[] };
        if (cached?.categories?.length) {
          return mergeSubcategoriesWithDefaults(cached.categories, DEFAULT_MEN_SUBCATEGORIES);
        }
      } catch {
        sessionStorage.removeItem(cacheKey);
      }
    }
    return DEFAULT_MEN_SUBCATEGORIES;
  });

  useEffect(() => {
    const loadPrimaryCategories = async () => {
      const cacheKey = 'shopsoma_primary_categories';
      const cachedRaw = sessionStorage.getItem(cacheKey);
      let resolvedId: string | null = null;
      if (cachedRaw) {
        try {
          const cached = JSON.parse(cachedRaw) as { categories: { id: string; name?: string }[] };
          const cachedMen = cached.categories.find(
            (category) => category.name?.toLowerCase() === 'men'
          );
          if (cachedMen?.id) {
            resolvedId = cachedMen.id;
            setMenCategoryId(cachedMen.id);
          }
        } catch {
          sessionStorage.removeItem(cacheKey);
        }
      }

      try {
        const categories = await categoryService.getPrimaryCategories();
        const menCategory = categories.find(
          (category) => category.name?.toLowerCase() === 'men'
        );
        if (menCategory?.id) {
          setMenCategoryId(menCategory.id);
        }
        sessionStorage.setItem(
          cacheKey,
          JSON.stringify({ categories: categories.map(({ id, name }) => ({ id, name })) })
        );
      } catch (error) {
        if (!resolvedId) {
          console.error('Failed to load primary categories for men storefront', error);
        }
      } finally {
        setCategoryLoading(false);
      }
    };

    loadPrimaryCategories();
  }, []);

  useEffect(() => {
    const targetId = menCategoryId || MEN_CATEGORY_ID;

    const loadSubcategories = async () => {
      const cacheKey = `shopsoma_subcategories_${targetId}`;
      const cachedRaw = sessionStorage.getItem(cacheKey);
      if (cachedRaw) {
        try {
          const cached = JSON.parse(cachedRaw) as { categories: Category[] };
          if (cached?.categories?.length) {
            setSubcategories(mergeSubcategoriesWithDefaults(cached.categories, DEFAULT_MEN_SUBCATEGORIES));
          }
        } catch {
          sessionStorage.removeItem(cacheKey);
        }
      }

      try {
        const categories = await categoryService.getSubcategories(targetId);
        const merged = mergeSubcategoriesWithDefaults(categories, DEFAULT_MEN_SUBCATEGORIES);
        setSubcategories(merged);
        sessionStorage.setItem(cacheKey, JSON.stringify({ categories: merged }));
      } catch (error) {
        console.error('Failed to load men subcategories for storefront', error);
      }
    };

    loadSubcategories();
  }, [menCategoryId]);

  const initialParams = useMemo(
    () => (menCategoryId ? { category_id: menCategoryId } : undefined),
    [menCategoryId]
  );

  if (categoryLoading && !menCategoryId) {
    return <Loading fullScreen message="Loading men's collection..." />;
  }

  return (
    <ProductList
      presetCategory="Men"
      initialParams={initialParams}
      categoryNav={subcategories}
      childCategoryOverrides={MEN_CHILD_CATEGORIES}
      heroOverride={{
        title: 'Menswear for the modern man',
        body: 'Discover easy tailoring, bold silhouettes and everyday staples, curated for the modern man.',
        imageUrl: MEN_HERO_IMAGE_URL,
        mobileImageUrl: MEN_HERO_MOBILE_IMAGE_URL,
        imagePositionClassName: 'object-[40%_25%] max-sm:object-[25%_40%]',
        ctaLabel: 'Shop all menswear',
      }}
    />
  );
}
