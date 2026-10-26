import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import VendorSidebar from './VendorSidebar';

vi.mock('../../context/VendorContext', () => ({
  useVendor: () => ({
    vendorProfile: {
      id: 'vendor-1',
      business_name: 'Custom Brand Name',
      logo_url: null,
      is_onboarding: false,
    },
    isOnboarding: false,
  }),
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: {
      full_name: 'John Doe',
      email: 'vendor@example.com',
    },
    logout: vi.fn(),
  }),
}));

vi.mock('../../services/vendorService', () => ({
  vendorService: {
    getDashboardMetrics: vi.fn().mockResolvedValue({
      total_orders: 5,
      completed_orders: 2,
    }),
  },
}));

describe('VendorSidebar - Brand Name Display', () => {
  it('displays the vendor business_name in the sidebar profile card', async () => {
    render(
      <MemoryRouter>
        <VendorSidebar />
      </MemoryRouter>
    );

    const matches = await screen.findAllByText('Custom Brand Name');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('applies truncation and min-w-0 to avoid vendor name overflowing card', async () => {
    render(
      <MemoryRouter>
        <VendorSidebar />
      </MemoryRouter>
    );

    const nameElements = await screen.findAllByText('Custom Brand Name');
    const desktopName = nameElements[nameElements.length - 1];

    expect(desktopName.className).toContain('truncate');
    expect(desktopName.getAttribute('title')).toBe('Custom Brand Name');
    expect(desktopName.parentElement?.className).toContain('min-w-0');
    expect(desktopName.parentElement?.className).toContain('flex-1');
  });
});
