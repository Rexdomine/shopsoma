import type { ReactNode } from 'react';
import { render, screen } from '@testing-library/react';
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

  it('shows the updated shop by category labels', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    );

    expect(screen.getByText('Dresses')).toBeInTheDocument();
    expect(screen.getByText('Occasion wear')).toBeInTheDocument();
    expect(screen.getByText('Workwear')).toBeInTheDocument();
    expect(screen.getByText('Casual')).toBeInTheDocument();

    expect(screen.queryByText('Gowns')).not.toBeInTheDocument();
    expect(screen.queryByText('Hand stitched')).not.toBeInTheDocument();
    expect(screen.queryByText('Strong Construction')).not.toBeInTheDocument();
    expect(screen.queryByText('Cotton')).not.toBeInTheDocument();
  });
});
