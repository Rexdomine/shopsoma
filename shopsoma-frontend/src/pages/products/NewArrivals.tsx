import ProductList from './ProductList';

export default function NewArrivals() {
  return (
    <ProductList
      heroOverride={{
        title: 'New Arrivals',
        body: 'Discover the latest drops across Shopsoma, curated fresh for you.',
        imageUrl: '/images/hero/demo-image-2.png',
        ctaLabel: 'Shop new arrivals',
      }}
      initialParams={{ sort_by: 'created_at', sort_order: 'desc' }}
    />
  );
}
