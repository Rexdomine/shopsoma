import ProductList from './ProductList';

export default function BagsWalletsStorefront() {
  return (
    <ProductList
      presetCategory="Bags & Wallets"
      heroOverride={{
        title: 'Bags & Wallets',
        body: 'Carry the season with structured bags, soft leathers, and everyday wallets.',
        imageUrl: '/images/hero/shop-edits-2088.jpg',
        imagePositionClassName: 'object-center sm:object-top',
        ctaLabel: 'Shop bags & wallets',
      }}
    />
  );
}
