import { useMemo } from 'react';
import ProductList from './ProductList';

export default function NewArrivals() {
  const initialParams = useMemo(
    () => ({ sort_by: 'created_at', sort_order: 'desc' }),
    []
  );

  return (
    <ProductList
      heroOverride={{
        title: 'New Arrivals',
        body: 'Discover the latest drops across Shopsoma, curated fresh for you.',
        imageUrl: '/images/hero/demo-image-2.png',
        ctaLabel: 'Shop new arrivals',
      }}
      initialParams={initialParams}
    />
  );
}
