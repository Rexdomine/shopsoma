import ProductList from './ProductList';
import { WOMEN_HERO_IMAGE_URL } from '../../config/constants';

export default function WomenStorefront() {
  return (
    <ProductList
      presetCategory="Women"
      initialParams={{ search: 'Women' }}
      heroOverride={{
        title: 'Womenswear: Effortless Elegance',
        body: 'Explore statement pieces, refined tailoring and everyday essentials crafted for modern women.',
        imageUrl: WOMEN_HERO_IMAGE_URL,
        ctaLabel: 'Shop all womenswear',
      }}
    />
  );
}
