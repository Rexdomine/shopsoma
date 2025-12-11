import ProductList from './ProductList';
import { MEN_HERO_IMAGE_URL } from '../../config/constants';

export default function MenStorefront() {
  return (
    <ProductList
      presetCategory="Men"
      initialParams={{ search: 'Men' }}
      heroOverride={{
        title: 'Menswear: Elevated Everyday Style',
        body: 'Discover tailored pieces, bold silhouettes and everyday staples, curated for the modern man.',
        imageUrl: MEN_HERO_IMAGE_URL,
        ctaLabel: 'Shop all menswear',
      }}
    />
  );
}
