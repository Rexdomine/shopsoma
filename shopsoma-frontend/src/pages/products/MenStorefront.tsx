import { useEffect, useMemo, useState } from 'react';
import Loading from '../../components/common/Loading';
import { MEN_HERO_IMAGE_URL, MEN_HERO_MOBILE_IMAGE_URL } from '../../config/constants';
import { categoryService } from '../../services/categoryService';
import ProductList from './ProductList';
import type { Category } from '../../types';

export default function MenStorefront() {
  const [menCategoryId, setMenCategoryId] = useState<string | null>(null);
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
          const cachedMen = cached.categories.find(
            (category) => category.name?.toLowerCase() === 'men'
          );
          if (cachedMen?.id) {
            setMenCategoryId(cachedMen.id);
            setCategoryLoading(false);
            hasCached = true;
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
        setMenCategoryId(menCategory?.id ?? null);
        sessionStorage.setItem(
          cacheKey,
          JSON.stringify({ categories: categories.map(({ id, name }) => ({ id, name })) })
        );
      } catch (error) {
        if (!hasCached) {
          console.error('Failed to load primary categories for men storefront', error);
        }
      } finally {
        setCategoryLoading(false);
      }
    };

    loadPrimaryCategories();
  }, []);

  useEffect(() => {
    if (!menCategoryId) return;

    const loadSubcategories = async () => {
      const cacheKey = `shopsoma_subcategories_${menCategoryId}`;
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
        const categories = await categoryService.getSubcategories(menCategoryId);
        setSubcategories(categories);
        sessionStorage.setItem(cacheKey, JSON.stringify({ categories }));
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
      heroOverride={{
        title: 'Menswear for the modern man',
        body: 'Easy tailoring, confident silhouettes and everyday staples, selected for the modern man.',
        imageUrl: MEN_HERO_IMAGE_URL,
        mobileImageUrl: MEN_HERO_MOBILE_IMAGE_URL,
        imagePositionClassName: 'object-[40%_25%] max-sm:object-[25%_40%]',
        ctaLabel: 'Shop all menswear',
      }}
    />
  );
}
