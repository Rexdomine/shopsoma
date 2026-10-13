import { useMemo } from 'react';
import ProductList from './ProductList';

export default function NewArrivals() {
  const initialParams = useMemo(
    () => ({ sort_by: 'created_at', sort_order: 'desc' } as const),
    []
  );

  return (
    <ProductList
      heroOverride={{
        title: 'New Arrivals',
        body: 'Discover the latest drops across Shopsoma, curated fresh for you.',
        imageUrl: '/images/hero/shop-edits-2088.jpg',
        imagePositionClassName: 'object-center sm:object-top',
        ctaLabel: 'Shop new arrivals',
      }}
      initialParams={initialParams}
    />
  );
}
