import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import Loading from '../../components/common/Loading';
import NotFound from '../errors/NotFound';
import { categoryService } from '../../services/categoryService';
import type { Category } from '../../types';
import ProductList from './ProductList';

export default function CategoryStorefront() {
  const { slug } = useParams<{ slug: string }>();
  const [category, setCategory] = useState<Category | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let mounted = true;
    setCategory(null);
    setError(false);
    setLoading(true);

    const loadCategory = async () => {
      if (!slug) {
        setError(true);
        setLoading(false);
        return;
      }

      try {
        const categories = await categoryService.getAllCategories();
        const match = categories.find((candidate) => candidate.slug === slug);
        if (!mounted) return;
        setCategory(match ?? null);
        setError(!match);
      } catch {
        if (mounted) setError(true);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadCategory();
    return () => {
      mounted = false;
    };
  }, [slug]);

  if (loading) {
    return <Loading fullScreen message="Loading category..." />;
  }

  if (error || !category) {
    return <NotFound />;
  }

  return (
    <ProductList
      presetCategory={category.name}
      initialParams={{ category_id: category.id }}
      heroOverride={{
        title: category.name,
        body: category.description || `Explore our ${category.name.toLowerCase()} edit.`,
        imageUrl: '/images/hero/demo-image-2.png',
        ctaLabel: `Shop ${category.name.toLowerCase()}`,
      }}
    />
  );
}
