import { useEffect, useMemo, useState } from 'react';
import Loading from '../../components/common/Loading';
import { categoryService } from '../../services/categoryService';
import type { Category } from '../../types';
import ProductList from './ProductList';

const SHOP_EDITS_CATEGORY_NAME = 'Shop Edits';
const SHOP_EDITS_CATEGORY_SLUG = 'shop-edits';
const OCCASION_WEAR_CATEGORY_NAME = 'Occasion Wear';
const OCCASION_WEAR_CATEGORY_SLUG = 'shop-edits-occasion-wear';

const SHOP_EDITS_TAB_CATEGORIES = [
  { name: 'Casual', slug: 'shop-edits-occasion-wear-casual' },
  { name: 'Evening', slug: 'shop-edits-occasion-wear-evening' },
  { name: 'Party', slug: 'shop-edits-occasion-wear-party' },
  { name: 'Workwear', slug: 'shop-edits-occasion-wear-workwear' },
] as const;

const matchesCategory = (
  category: Category | null | undefined,
  name: string,
  slug: string,
) => {
  if (!category) return false;
  const categoryName = category.name?.toLowerCase().trim();
  const categorySlug = category.slug?.toLowerCase().trim();
  return categoryName === name.toLowerCase() || categorySlug === slug;
};

const matchesShopEdits = (category?: Category | null) =>
  matchesCategory(category, SHOP_EDITS_CATEGORY_NAME, SHOP_EDITS_CATEGORY_SLUG);

const matchesOccasionWear = (category?: Category | null) =>
  matchesCategory(category, OCCASION_WEAR_CATEGORY_NAME, OCCASION_WEAR_CATEGORY_SLUG);

const getShopEditsTabs = (categories: Category[]) =>
  SHOP_EDITS_TAB_CATEGORIES.flatMap((tab) => {
    const category = categories.find((candidate) => matchesCategory(candidate, tab.name, tab.slug));
    return category ? [category] : [];
  });

export default function ShopEditsStorefront() {
  const [shopEditsCategoryId, setShopEditsCategoryId] = useState<string | null>(null);
  const [categoryLoading, setCategoryLoading] = useState(true);
  const [categoryUnavailable, setCategoryUnavailable] = useState(false);
  const [subcategories, setSubcategories] = useState<Category[]>([]);

  useEffect(() => {
    let isCurrent = true;
    const loadShopEditsCategories = async () => {
      try {
        const primaryCategories = await categoryService.getPrimaryCategories();
        let shopEditsCategory = primaryCategories.find((category) => matchesShopEdits(category));
        if (!shopEditsCategory) {
          const allCategories = await categoryService.getAllCategories();
          shopEditsCategory = allCategories.find((category) => matchesShopEdits(category));
        }

        if (!shopEditsCategory) {
          if (isCurrent) {
            setCategoryUnavailable(true);
          }
          return;
        }

        const occasionWearCategories = await categoryService.getSubcategories(shopEditsCategory.id);
        const occasionWearCategory = occasionWearCategories.find((category) => matchesOccasionWear(category));
        if (!occasionWearCategory) {
          if (isCurrent) {
            setCategoryUnavailable(true);
          }
          return;
        }

        const occasionWearChildren = await categoryService.getSubcategories(occasionWearCategory.id);
        const tabs = getShopEditsTabs(occasionWearChildren);
        if (tabs.length !== SHOP_EDITS_TAB_CATEGORIES.length) {
          if (isCurrent) {
            setCategoryUnavailable(true);
          }
          return;
        }

        if (isCurrent) {
          setShopEditsCategoryId(shopEditsCategory.id);
          setSubcategories(tabs);
        }
      } catch (error) {
        if (isCurrent) {
          setCategoryUnavailable(true);
          console.error('Failed to load primary categories for shop edits storefront', error);
        }
      } finally {
        if (isCurrent) {
          setCategoryLoading(false);
        }
      }
    };

    loadShopEditsCategories();
    return () => {
      isCurrent = false;
    };
  }, []);

  const initialParams = useMemo(
    () => (shopEditsCategoryId ? { category_id: shopEditsCategoryId } : undefined),
    [shopEditsCategoryId]
  );

  if (categoryLoading && !shopEditsCategoryId) {
    return <Loading fullScreen message="Loading shop edits..." />;
  }

  if (categoryUnavailable) {
    return <div role="alert">Shop Edits are temporarily unavailable.</div>;
  }

  return (
    <ProductList
      presetCategory="Shop Edits"
      initialParams={initialParams}
      categoryNav={subcategories}
      categoryNavAsTabs
      heroOverride={{
        title: 'Shop Edits: Curated Discoveries',
        body: 'A rotating curation of elevated essentials, seasonal selections and statement finds.',
        imageUrl: '/images/hero/demo-image-2.png',
        ctaLabel: 'Shop all edits',
      }}
    />
  );
}
