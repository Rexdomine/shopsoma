import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import Loading from '../../components/common/Loading';
import NotFound from '../errors/NotFound';
import ProductList from '../products/ProductList';
import {
  designerService,
  getDesignerCampaignImageUrl,
  type Designer,
} from '../../services/designerService';
import type { Category } from '../../types';

export default function DesignerStorefront() {
  const { designerId } = useParams<{ designerId: string }>();
  const [designer, setDesigner] = useState<Designer | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let isCurrent = true;

    const loadDesigner = async () => {
      if (!designerId) {
        if (isCurrent) {
          setDesigner(null);
          setNotFound(true);
          setLoading(false);
        }
        return;
      }

      try {
        setLoading(true);
        setNotFound(false);
        const data = await designerService.getDesigner(designerId);
        if (!isCurrent) return;
        setDesigner(data);
      } catch (err) {
        if (!isCurrent) return;
        console.error('Failed to load designer storefront', err);
        setDesigner(null);
        setNotFound(true);
      } finally {
        if (isCurrent) {
          setLoading(false);
        }
      }
    };

    loadDesigner();
    return () => {
      isCurrent = false;
    };
  }, [designerId]);

  const initialParams = useMemo(
    () => (designer ? { vendor_id: designer.id } : undefined),
    [designer],
  );

  const designerCategories = useMemo<Category[]>(() => {
    if (!designer?.categories?.length) return [];
    return designer.categories
      .filter((category) => category.is_active && category.name)
      .map((category) => ({
        id: category.id,
        name: category.name,
        slug: category.slug,
        display_order: category.display_order ?? 0,
        is_active: category.is_active ?? true,
        created_at: designer.created_at,
        updated_at: designer.created_at,
      }));
  }, [designer]);

  if (loading) {
    return <Loading fullScreen message="Loading designer storefront..." />;
  }

  if (notFound || !designer) {
    return <NotFound />;
  }

  const campaignImageUrl = getDesignerCampaignImageUrl(designer);
  const brandDescription =
    designer.business_description?.trim() ||
    `Explore the curated collection from ${designer.business_name} on SHOPSOMA.`;

  return (
    <ProductList
      initialParams={initialParams}
      categoryNav={designerCategories}
      categoryNavAsTabs
      heroOverride={{
        title: designer.business_name,
        body: brandDescription,
        imageUrl: campaignImageUrl,
        imagePositionClassName: 'object-center sm:object-top',
        ctaLabel: 'Shop Collection',
      }}
    />
  );
}
