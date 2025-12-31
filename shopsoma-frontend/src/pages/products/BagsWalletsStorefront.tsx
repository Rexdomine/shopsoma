import ProductList from './ProductList';

export default function BagsWalletsStorefront() {
  return (
    <ProductList
      presetCategory="Bags & Wallets"
      heroOverride={{
        title: 'Bags & Wallets',
        body: 'Carry the season with structured bags, soft leathers, and everyday wallets.',
        imageUrl: '/images/hero/demo-image-2.png',
        ctaLabel: 'Shop bags & wallets',
      }}
    />
  );
}
