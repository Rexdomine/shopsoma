import ProductList from './ProductList';

export default function PerfumesStorefront() {
  return (
    <ProductList
      presetCategory="Perfumes"
      heroOverride={{
        title: 'Perfumes: Signature Scents',
        body: 'Explore fragrances that linger, from fresh florals to bold, smoky blends.',
        imageUrl: '/images/hero/demo-image-2.png',
        ctaLabel: 'Shop perfumes',
      }}
    />
  );
}
