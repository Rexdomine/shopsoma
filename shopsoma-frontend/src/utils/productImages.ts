import { API_BASE_URL } from '../config/constants';
import type { Product } from '../types';

export interface ProductImageSource {
  src: string;
  fallbackSrc?: string;
}

export function normalizeProductImageUrl(url?: string | null) {
  const value = url?.trim();
  if (!value || value === 'undefined' || value === 'null') {
    return '';
  }
  if (/^(https?:)?\/\//.test(value) || value.startsWith('data:') || value.startsWith('blob:')) {
    return value;
  }
  if (value.startsWith('/')) {
    const apiOrigin = API_BASE_URL.replace(/\/api\/v\d+\/?$/, '');
    return `${apiOrigin}${value}`;
  }
  return value;
}

export function getProductImageSources(product: Product): ProductImageSource[] {
  const productSources: ProductImageSource[] = [...(product.images ?? [])]
    .sort((a, b) => {
      if (a.is_primary !== b.is_primary) {
        return a.is_primary ? -1 : 1;
      }
      return (a.display_order ?? 0) - (b.display_order ?? 0);
    })
    .reduce<ProductImageSource[]>((sources, image) => {
      const thumbnail = normalizeProductImageUrl(image.thumbnail_url);
      const original = normalizeProductImageUrl(image.image_url);
      if (!thumbnail && !original) {
        return sources;
      }
      sources.push({
        src: thumbnail || original,
        fallbackSrc: thumbnail && original && thumbnail !== original ? original : undefined,
      });
      return sources;
    }, []);

  const variationSources: ProductImageSource[] = (product.variations ?? [])
    .flatMap((variation) => variation.images ?? [])
    .map(normalizeProductImageUrl)
    .filter(Boolean)
    .map((src) => ({ src }));

  return [...productSources, ...variationSources];
}

export function getProductImageSource(product: Product): ProductImageSource | null {
  return getProductImageSources(product)[0] ?? null;
}
