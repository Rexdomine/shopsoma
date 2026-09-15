import type { ReactNode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Home from '../Home';

const { getProductsMock, getFeaturedProductsMock, getFeaturedRotationSettingsMock } = vi.hoisted(() => ({
  getProductsMock: vi.fn(),
  getFeaturedProductsMock: vi.fn(),
  getFeaturedRotationSettingsMock: vi.fn(),
}));

vi.mock('../../components/layout/Layout', () => ({
  default: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

vi.mock('../../services/productService', () => ({
  productService: {
    getProducts: getProductsMock,
    getFeaturedProducts: getFeaturedProductsMock,
  },
}));

vi.mock('../../services/settingsService', () => ({
  getFeaturedRotationSettings: getFeaturedRotationSettingsMock,
}));

vi.mock('../../hooks/useWishlistActions', () => ({
  useWishlistActions: () => ({
    favorites: new Set<string>(),
    toggleFavorite: vi.fn(),
    loadingIds: new Set<string>(),
  }),
}));

vi.mock('../../hooks/useCurrency', () => ({
  useCurrency: () => ({
    currentCurrency: 'NGN',
    exchangeRates: { NGN: 1, USD: 0.001 },
  }),
}));

vi.mock('../../utils/pricing', () => ({
  formatPriceWithConversion: () => '₦0',
}));

vi.mock('../../utils/productImages', () => ({
  getProductImageSource: () => ({ src: '/placeholder.svg' }),
  getProductImageSources: () => [{ src: '/placeholder.svg' }],
}));

describe('Home', () => {
  beforeEach(() => {
    getProductsMock.mockReset();
    getFeaturedProductsMock.mockReset();
    getFeaturedRotationSettingsMock.mockReset();
    getProductsMock.mockResolvedValue({ products: [] });
    getFeaturedProductsMock.mockResolvedValue([]);
    getFeaturedRotationSettingsMock.mockResolvedValue({ rotation_minutes: 10 });
  });

  it('presents a premium three-image campaign hero with accessible navigation', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    const hero = screen.getByRole('region', { name: 'Orange Culture campaign' });
    expect(hero).toHaveAttribute('aria-roledescription', 'carousel');
    expect(screen.getByRole('img', { name: /campaign look 1/i })).toBeInTheDocument();
    expect(screen.queryByRole('img', { name: /campaign look 3/i })).not.toBeInTheDocument();
    expect(screen.getByText('Orange Culture: A night Beyond')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /pause automatic campaign slideshow/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/1 \/ 3/)).not.toBeInTheDocument();
  });

  it('skips a failed deferred slide during automatic rotation', () => {
    vi.useFakeTimers();
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    act(() => vi.advanceTimersByTime(6500));
    const failedSecondSlide = screen.getByAltText(/campaign look 2/i);
    expect(failedSecondSlide).toHaveAttribute(
      'alt',
      'Orange Culture campaign look 2: two models in an intimate editorial interior'
    );
    fireEvent.error(failedSecondSlide);

    act(() => vi.advanceTimersByTime(6500));
    expect(screen.getByAltText(/campaign look 3/i)).toBeInTheDocument();
    vi.useRealTimers();
  });

  it('retries a skipped slide after a short cooldown', () => {
    vi.useFakeTimers();
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    act(() => vi.advanceTimersByTime(6500));
    fireEvent.error(screen.getByAltText(/campaign look 2/i));
    act(() => vi.advanceTimersByTime(15000));

    expect(screen.getByAltText(/campaign look 2/i)).toHaveAttribute('loading', 'eager');
    vi.useRealTimers();
  });

  it('shows the Drive-supplied shop by category strip in the requested order', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    const categoryImages = screen.getAllByRole('img').filter((image) =>
      ['Casual', 'Occasion', 'Party', 'Workwear'].includes(image.getAttribute('alt') || '')
    );
    expect(categoryImages.map((image) => image.getAttribute('alt'))).toEqual(['Casual', 'Occasion', 'Party', 'Workwear']);
    expect(categoryImages.map((image) => image.getAttribute('src'))).toEqual([
      '/images/category-strip/casual-1-900.webp',
      '/images/category-strip/occasion-900.webp',
      '/images/category-strip/party-900.webp',
      '/images/category-strip/workwear-900.webp',
    ]);
    expect(categoryImages.every((image) => image.getAttribute('loading') === 'lazy')).toBe(true);
    expect(categoryImages.every((image) => image.getAttribute('decoding') === 'async')).toBe(true);
    expect(categoryImages.every((image) => image.getAttribute('sizes') === '(min-width: 768px) 25vw, 50vw')).toBe(true);
    expect(categoryImages.every((image) => (image.getAttribute('srcset') || '').includes('480w') && (image.getAttribute('srcset') || '').includes('900w'))).toBe(true);

    expect(screen.queryByText('Dresses')).not.toBeInTheDocument();
    expect(screen.queryByText('Occasion wear')).not.toBeInTheDocument();
  });

  it('uses the approved responsive Kilentar editorial image', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    const editorialImage = screen.getByRole('img', { name: 'Kilentar: Avant Premier' });
    expect(editorialImage).toHaveAttribute('src', '/images/editorial/kilentar-avant-premier-1440.webp');
    expect(editorialImage).toHaveAttribute('srcset', expect.stringContaining('kilentar-avant-premier-720.webp 720w'));
    expect(editorialImage).toHaveAttribute('srcset', expect.stringContaining('kilentar-avant-premier-1440.webp 1440w'));
    expect(editorialImage).toHaveAttribute('sizes', '(min-width: 1024px) 896px, 100vw');
    expect(editorialImage).toHaveAttribute('loading', 'lazy');
    expect(editorialImage).toHaveAttribute('decoding', 'async');
  });
});
