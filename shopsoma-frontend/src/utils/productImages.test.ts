import { beforeEach, describe, expect, it } from 'vitest';
import { getProductImageSource, getProductImageSources, normalizeProductImageUrl } from './productImages';
import type { Product } from '../types';

const storage = {
  clear: () => undefined,
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
};

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', { configurable: true, value: storage });
  Object.defineProperty(window, 'sessionStorage', { configurable: true, value: storage });
});

const product = (images: Product['images']): Product => ({
  id: 'product-1',
  title: 'Test product',
  description: '',
  category_id: null,
  base_price: 100,
  compare_at_price: null,
  currency: 'NGN',
  total_stock: 1,
  status: 'active',
  moderation_status: 'approved',
  moderation_notes: null,
  is_featured: false,
  product_type: 'single',
  made_to_order: false,
  made_to_order_timeline: null,
  images,
  variations: [],
  variants: [],
} as unknown as Product);

describe('product image source contract', () => {
  it('normalizes API-root-relative URLs to the API origin', () => {
    expect(normalizeProductImageUrl('/uploads/products/primary.jpg')).toMatch(
      /\/uploads\/products\/primary\.jpg$/,
    );
    expect(normalizeProductImageUrl('https://cdn.example.test/primary.jpg')).toBe(
      'https://cdn.example.test/primary.jpg',
    );
  });

  it('selects the primary image before array order and display order', () => {
    const source = getProductImageSource(product([
      { id: 'second', product_id: 'product-1', image_url: '/uploads/second.jpg', thumbnail_url: undefined, display_order: 0, is_primary: false },
      { id: 'primary', product_id: 'product-1', image_url: '/uploads/primary.jpg', thumbnail_url: undefined, display_order: 4, is_primary: true },
    ]));
    expect(source?.src).toMatch(/\/uploads\/primary\.jpg$/);
  });

  it('keeps thumbnails as the default for small surfaces', () => {
    const source = getProductImageSource(product([
      { id: 'primary', product_id: 'product-1', image_url: '/uploads/primary.jpg', thumbnail_url: '/uploads/primary-thumb.jpg', display_order: 0, is_primary: true },
    ]));

    expect(source?.src).toMatch(/primary-thumb\.jpg$/);
    expect(source?.fallbackSrc).toMatch(/primary\.jpg$/);
  });

  it('selects the original image for high-resolution surfaces', () => {
    const source = getProductImageSource(product([
      { id: 'primary', product_id: 'product-1', image_url: '/uploads/primary.jpg', thumbnail_url: '/uploads/primary-thumb.jpg', display_order: 0, is_primary: true },
    ]), 'high');

    expect(source?.src).toMatch(/primary\.jpg$/);
    expect(source?.fallbackSrc).toMatch(/primary-thumb\.jpg$/);
  });

  it('preserves high-resolution selection for every gallery image', () => {
    const sources = getProductImageSources(product([
      { id: 'primary', product_id: 'product-1', image_url: '/uploads/primary.jpg', thumbnail_url: '/uploads/primary-thumb.jpg', display_order: 0, is_primary: true },
      { id: 'secondary', product_id: 'product-1', image_url: '/uploads/secondary.jpg', thumbnail_url: '/uploads/secondary-thumb.jpg', display_order: 1, is_primary: false },
    ]), 'high');

    expect(sources.map((source) => source.src)).toEqual([
      expect.stringMatching(/primary\.jpg$/),
      expect.stringMatching(/secondary\.jpg$/),
    ]);
  });
});
