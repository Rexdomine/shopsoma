import ProductList from './ProductList';

export default function PerfumesStorefront() {
  return (
    <ProductList
      presetCategory="Perfumes"
      heroOverride={{
        title: 'Perfumes: Signature Scents',
        body: 'Explore fragrances that linger, from fresh florals to bold, smoky blends.',
        imageUrl: '/images/hero/shop-edits-2088.jpg',
        imagePositionClassName: 'object-center sm:object-top',
        ctaLabel: 'Shop perfumes',
      }}
    />
  );
}
