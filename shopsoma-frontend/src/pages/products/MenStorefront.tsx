import { useEffect, useMemo, useState } from 'react';
import Loading from '../../components/common/Loading';
import { MEN_HERO_IMAGE_URL } from '../../config/constants';
import { categoryService } from '../../services/categoryService';
import ProductList from './ProductList';

export default function MenStorefront() {
  const [menCategoryId, setMenCategoryId] = useState<string | null>(null);
  const [categoryLoading, setCategoryLoading] = useState(true);

  useEffect(() => {
    const loadPrimaryCategories = async () => {
      try {
        const categories = await categoryService.getPrimaryCategories();
        const menCategory = categories.find(
          (category) => category.name?.toLowerCase() === 'men'
        );
        setMenCategoryId(menCategory?.id ?? null);
      } catch (error) {
        console.error('Failed to load primary categories for men storefront', error);
      } finally {
        setCategoryLoading(false);
      }
    };

    loadPrimaryCategories();
  }, []);

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
      heroOverride={{
        title: 'Menswear: Elevated Everyday Style',
        body: 'Discover tailored pieces, bold silhouettes and everyday staples, curated for the modern man.',
        imageUrl: MEN_HERO_IMAGE_URL,
        ctaLabel: 'Shop all menswear',
      }}
    />
  );
}
