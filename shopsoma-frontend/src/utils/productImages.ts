import { API_BASE_URL } from '../config/constants';
import type { Product } from '../types';

export interface ProductImageSource {
  src: string;
  fallbackSrc?: string;
}

export type ProductImageQuality = 'thumbnail' | 'high';

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

export function optimizeCloudinaryUrl(
  url: string,
  quality: ProductImageQuality = 'thumbnail',
): { src: string; fallbackSrc?: string } {
  if (!url || !url.includes('res.cloudinary.com')) {
    return { src: url };
  }

  const isCloudinaryUpload = /^(https?:\/\/res\.cloudinary\.com\/[^/]+\/image\/upload\/)(.*)$/i;
  const match = url.match(isCloudinaryUpload);
  if (!match) {
    return { src: url };
  }

  const prefix = match[1];
  const rest = match[2];

  const transformMatch = rest.match(/^((?:[a-z]_[^/]+,?)+)\/(.*)$/i);
  let existingTransforms = '';
  let pathAfterTransforms = rest;

  if (transformMatch) {
    existingTransforms = transformMatch[1];
    pathAfterTransforms = transformMatch[2];
  }

  const isHeic = /\.(heic|heif)(\?.*)?$/i.test(url);
  const targetWidth = quality === 'thumbnail' ? 400 : 1600;
  const autoTransform = `c_limit,w_${targetWidth},f_auto,q_auto`;

  let transformsToUse = autoTransform;
  if (existingTransforms) {
    if (existingTransforms.includes('f_auto') && existingTransforms.includes('w_')) {
      transformsToUse = existingTransforms;
    } else {
      transformsToUse = `${existingTransforms},${autoTransform}`;
    }
  }

  const optimizedSrc = `${prefix}${transformsToUse}/${pathAfterTransforms}`;

  let fallbackSrc: string | undefined;
  if (isHeic) {
    const jpgPath = pathAfterTransforms.replace(/\.(heic|heif)(\?.*)?$/i, '.jpg$2');
    fallbackSrc = `${prefix}c_limit,w_${targetWidth},f_jpg,q_auto/${jpgPath}`;
  } else if (!existingTransforms.includes('f_auto')) {
    fallbackSrc = url;
  }

  return {
    src: optimizedSrc,
    fallbackSrc: fallbackSrc !== optimizedSrc ? fallbackSrc : undefined,
  };
}

export function getProductImageSources(
  product: Product,
  quality: ProductImageQuality = 'thumbnail',
): ProductImageSource[] {
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
      const useHighQuality = quality === 'high';
      const rawSrc = useHighQuality ? original || thumbnail : thumbnail || original;
      const rawFallback = useHighQuality
        ? original && thumbnail && original !== thumbnail ? thumbnail : undefined
        : thumbnail && original && thumbnail !== original ? original : undefined;

      const cld = optimizeCloudinaryUrl(rawSrc, quality);
      sources.push({
        src: cld.src,
        fallbackSrc: cld.fallbackSrc || rawFallback,
      });
      return sources;
    }, []);

  const variationSources: ProductImageSource[] = (product.variations ?? [])
    .flatMap((variation) => variation.images ?? [])
    .map(normalizeProductImageUrl)
    .filter(Boolean)
    .map((src) => {
      const cld = optimizeCloudinaryUrl(src, quality);
      return { src: cld.src, fallbackSrc: cld.fallbackSrc };
    });

  return [...productSources, ...variationSources];
}

export function getProductImageSource(
  product: Product,
  quality: ProductImageQuality = 'thumbnail',
): ProductImageSource | null {
  return getProductImageSources(product, quality)[0] ?? null;
}

export function getOptimizedImageUrl(
  url?: string | null,
  quality: ProductImageQuality = 'high',
): { src: string; fallbackSrc?: string } {
  const normalized = normalizeProductImageUrl(url);
  if (!normalized) {
    return { src: '' };
  }
  return optimizeCloudinaryUrl(normalized, quality);
}

