import { useEffect, useMemo, useState } from 'react';
import Loading from '../../components/common/Loading';
import { categoryService } from '../../services/categoryService';
import type { Category } from '../../types';
import ProductList from './ProductList';

const SHOP_EDITS_CATEGORY_NAME = 'Shop Edits';
const SHOP_EDITS_CATEGORY_SLUG = 'shop-edits';

const matchesShopEdits = (category?: Category | null) => {
  if (!category) return false;
  const name = category.name?.toLowerCase().trim();
  const slug = category.slug?.toLowerCase().trim();
  return name === SHOP_EDITS_CATEGORY_NAME.toLowerCase() || slug === SHOP_EDITS_CATEGORY_SLUG;
};

export default function ShopEditsStorefront() {
  const [shopEditsCategoryId, setShopEditsCategoryId] = useState<string | null>(null);
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
          const cachedEdit = cached.categories.find((category) => {
            const name = category.name?.toLowerCase().trim();
            return name === SHOP_EDITS_CATEGORY_NAME.toLowerCase() || name === SHOP_EDITS_CATEGORY_SLUG;
          });
          if (cachedEdit?.id) {
            setShopEditsCategoryId(cachedEdit.id);
            setCategoryLoading(false);
            hasCached = true;
          }
        } catch {
          sessionStorage.removeItem(cacheKey);
        }
      }

      try {
        const categories = await categoryService.getPrimaryCategories();
        let shopEditsCategory = categories.find((category) => matchesShopEdits(category));
        if (!shopEditsCategory) {
          const allCategories = await categoryService.getAllCategories();
          shopEditsCategory = allCategories.find((category) => matchesShopEdits(category));
        }
        setShopEditsCategoryId(shopEditsCategory?.id ?? null);
        sessionStorage.setItem(
          cacheKey,
          JSON.stringify({ categories: categories.map(({ id, name }) => ({ id, name })) })
        );
      } catch (error) {
        if (!hasCached) {
          console.error('Failed to load primary categories for shop edits storefront', error);
        }
      } finally {
        setCategoryLoading(false);
      }
    };

    loadPrimaryCategories();
  }, []);

  useEffect(() => {
    if (!shopEditsCategoryId) return;

    const loadSubcategories = async () => {
      const cacheKey = `shopsoma_subcategories_${shopEditsCategoryId}`;
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
        const categories = await categoryService.getSubcategories(shopEditsCategoryId);
        setSubcategories(categories);
        sessionStorage.setItem(cacheKey, JSON.stringify({ categories }));
      } catch (error) {
        console.error('Failed to load shop edits subcategories for storefront', error);
      }
    };

    loadSubcategories();
  }, [shopEditsCategoryId]);

  const initialParams = useMemo(
    () => (shopEditsCategoryId ? { category_id: shopEditsCategoryId } : undefined),
    [shopEditsCategoryId]
  );

  if (categoryLoading && !shopEditsCategoryId) {
    return <Loading fullScreen message="Loading shop edits..." />;
  }

  return (
    <ProductList
      presetCategory="Shop Edits"
      initialParams={initialParams}
      categoryNav={subcategories}
      heroOverride={{
        title: 'Shop Edits: Curated Discoveries',
        body: 'A rotating curation of elevated essentials, seasonal selections and statement finds.',
        imageUrl: '/images/hero/demo-image-2.png',
        ctaLabel: 'Shop all edits',
      }}
    />
  );
}
