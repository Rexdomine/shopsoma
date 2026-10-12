import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BrandInfoSettings from './BrandInfoSettings';
import { ROUTES } from '../../config/constants';
import type { VendorProfile } from '../../services/vendorService';

const mockProfile: VendorProfile = {
  id: 'vendor-123',
  user_id: 'user-123',
  business_name: 'Original Brand Name',
  business_description: 'Luxury artisanal fashion',
  business_address: '12 Marina Street, Lagos',
  business_phone: '+2348012345678',
  logo_url: 'https://example.com/logo.png',
  featured_storefront_image_url: 'https://example.com/storefront.webp',
  returning_address: '12 Marina Street, Lagos',
  open_days: ['MON', 'TUE', 'WED', 'THU', 'FRI'],
  open_hour: '09:00',
  close_hour: '17:00',
  secondary_contacts: [],
  kyc_status: 'approved',
  kyc_submitted_at: '2026-01-01T00:00:00Z',
  bank_name: 'Access Bank',
  bank_account_number: '0123456789',
  bank_account_name: 'Original Brand Name',
  commission_rate: '12.50',
  approved: true,
  approved_at: '2026-01-01T00:00:00Z',
  store_active: true,
  store_paused_at: null,
  store_deleted_at: null,
  is_onboarding: false,
  brand_info_completed: true,
  payout_info_completed: true,
  onboarding_completed_at: '2026-01-01T00:00:00Z',
  total_products: 5,
  total_orders: 10,
  total_revenue: '500000.00',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockUpdateProfileContext = vi.fn();
const mockUpdateProfileApi = vi.fn();

let currentProfile = { ...mockProfile };

vi.mock('../../context/VendorContext', () => ({
  useVendor: () => ({
    vendorProfile: currentProfile,
    updateProfile: (updated: VendorProfile) => {
      currentProfile = { ...updated };
      mockUpdateProfileContext(updated);
    },
    isOnboarding: false,
    brandInfoCompleted: true,
    payoutInfoCompleted: true,
    refreshProfile: vi.fn(),
    isLoading: false,
  }),
}));

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: {
      id: 'user-123',
      email: 'vendor@example.com',
      full_name: 'Vendor Owner',
      role: 'vendor',
    },
    logout: vi.fn(),
  }),
}));

vi.mock('../../components/vendor/VendorSidebar', () => ({
  default: () => <div data-testid="mock-sidebar">Mock Sidebar</div>,
}));

vi.mock('../../services/vendorPaymentMethodsService', () => ({
  vendorPaymentMethodsService: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn().mockResolvedValue({}),
    setDefault: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('../../services/vendorService', () => ({
  vendorService: {
    getProfile: vi.fn().mockImplementation(() => Promise.resolve(currentProfile)),
    updateProfile: (...args: any[]) => mockUpdateProfileApi(...args),
    saveBrandInfo: vi.fn().mockImplementation(() => Promise.resolve(currentProfile)),
    savePayoutInfo: vi.fn().mockImplementation(() => Promise.resolve(currentProfile)),
    pauseStore: vi.fn().mockImplementation(() => Promise.resolve(currentProfile)),
    activateStore: vi.fn().mockImplementation(() => Promise.resolve(currentProfile)),
    deleteStore: vi.fn().mockImplementation(() => Promise.resolve(currentProfile)),
  },
}));

function renderBrandInfoSettings() {
  return render(
    <MemoryRouter initialEntries={[ROUTES.VENDOR_BRAND_INFO]}>
      <BrandInfoSettings />
    </MemoryRouter>
  );
}

describe('BrandInfoSettings - Brand Name Editing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentProfile = { ...mockProfile };
  });

  it('renders read-only state with Edit button and without the support restriction message', () => {
    renderBrandInfoSettings();

    const input = screen.getByRole('textbox', { name: /brand name/i });
    expect(input).toBeDisabled();
    expect(input).toHaveValue('Original Brand Name');

    const editBtn = screen.getByRole('button', { name: /edit brand name/i });
    expect(editBtn).toBeInTheDocument();

    // Verify old restriction message is removed
    expect(
      screen.queryByText(/The brand name cannot be changed without contacting the Support team/i)
    ).not.toBeInTheDocument();
  });

  it('enters edit mode when clicking Edit button and shows Save and Cancel actions', () => {
    renderBrandInfoSettings();

    const editBtn = screen.getByRole('button', { name: /edit brand name/i });
    fireEvent.click(editBtn);

    const input = screen.getByRole('textbox', { name: /brand name/i });
    expect(input).toBeEnabled();
    expect(input).toHaveValue('Original Brand Name');

    expect(screen.getByRole('button', { name: /save brand name/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel brand name/i })).toBeInTheDocument();
  });

  it('cancels edit mode and restores the previously saved value', () => {
    renderBrandInfoSettings();

    // Enter edit mode
    fireEvent.click(screen.getByRole('button', { name: /edit brand name/i }));
    const input = screen.getByRole('textbox', { name: /brand name/i });

    // Modify input
    fireEvent.change(input, { target: { value: 'Something Else' } });
    expect(input).toHaveValue('Something Else');

    // Click Cancel
    fireEvent.click(screen.getByRole('button', { name: /cancel brand name/i }));

    // Back to read-only state with original value
    const restoredInput = screen.getByRole('textbox', { name: /brand name/i });
    expect(restoredInput).toBeDisabled();
    expect(restoredInput).toHaveValue('Original Brand Name');
    expect(mockUpdateProfileApi).not.toHaveBeenCalled();
  });

  it('validates and rejects blank or whitespace-only input', async () => {
    renderBrandInfoSettings();

    fireEvent.click(screen.getByRole('button', { name: /edit brand name/i }));
    const input = screen.getByRole('textbox', { name: /brand name/i });

    // Try whitespace-only
    fireEvent.change(input, { target: { value: '    ' } });
    fireEvent.click(screen.getByRole('button', { name: /save brand name/i }));

    expect(await screen.findByText('Brand name cannot be blank.')).toBeInTheDocument();
    expect(mockUpdateProfileApi).not.toHaveBeenCalled();
  });

  it('validates and rejects too-short (< 2 chars) and too-long (> 255 chars) input', async () => {
    renderBrandInfoSettings();

    fireEvent.click(screen.getByRole('button', { name: /edit brand name/i }));
    const input = screen.getByRole('textbox', { name: /brand name/i });

    // 1 character
    fireEvent.change(input, { target: { value: 'A' } });
    fireEvent.click(screen.getByRole('button', { name: /save brand name/i }));

    expect(
      await screen.findByText('Brand name must be between 2 and 255 characters.')
    ).toBeInTheDocument();
    expect(mockUpdateProfileApi).not.toHaveBeenCalled();

    // 256 characters
    fireEvent.change(input, { target: { value: 'A'.repeat(256) } });
    fireEvent.click(screen.getByRole('button', { name: /save brand name/i }));

    expect(
      await screen.findByText('Brand name must be between 2 and 255 characters.')
    ).toBeInTheDocument();
    expect(mockUpdateProfileApi).not.toHaveBeenCalled();
  });

  it('successfully saves valid trimmed brand name, updates context without page reload, and exits edit mode', async () => {
    const updatedProfileResult: VendorProfile = {
      ...mockProfile,
      business_name: 'Luxe Lagos Couture',
    };
    mockUpdateProfileApi.mockResolvedValueOnce(updatedProfileResult);

    const { rerender } = renderBrandInfoSettings();

    fireEvent.click(screen.getByRole('button', { name: /edit brand name/i }));
    const input = screen.getByRole('textbox', { name: /brand name/i });

    // Input with leading/trailing spaces
    fireEvent.change(input, { target: { value: '   Luxe Lagos Couture   ' } });
    fireEvent.click(screen.getByRole('button', { name: /save brand name/i }));

    await waitFor(() => {
      expect(mockUpdateProfileApi).toHaveBeenCalledWith({
        business_name: 'Luxe Lagos Couture',
      });
    });

    expect(mockUpdateProfileContext).toHaveBeenCalledWith(updatedProfileResult);

    // Re-render to simulate context update
    rerender(
      <MemoryRouter initialEntries={[ROUTES.VENDOR_BRAND_INFO]}>
        <BrandInfoSettings />
      </MemoryRouter>
    );

    // Should return to read-only state with updated value
    await waitFor(() => {
      const readOnlyInput = screen.getByRole('textbox', { name: /brand name/i });
      expect(readOnlyInput).toBeDisabled();
      expect(readOnlyInput).toHaveValue('Luxe Lagos Couture');
    });

    expect(screen.getByText('Brand name updated successfully!')).toBeInTheDocument();
  });

  it('shows loading state while saving is in flight', async () => {
    let resolveSave: (value: any) => void;
    mockUpdateProfileApi.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSave = resolve;
      })
    );

    renderBrandInfoSettings();

    fireEvent.click(screen.getByRole('button', { name: /edit brand name/i }));
    const input = screen.getByRole('textbox', { name: /brand name/i });

    fireEvent.change(input, { target: { value: 'New Brand' } });
    fireEvent.click(screen.getByRole('button', { name: /save brand name/i }));

    // Should show Saving... and be disabled
    expect(screen.getByText(/Saving\.\.\./i)).toBeInTheDocument();
    expect(input).toBeDisabled();
    expect(screen.getByRole('button', { name: /cancel brand name/i })).toBeDisabled();

    // Resolve save
    resolveSave!({ ...mockProfile, business_name: 'New Brand' });

    await waitFor(() => {
      expect(screen.queryByText(/Saving\.\.\./i)).not.toBeInTheDocument();
    });
  });

  it('handles API error gracefully and remains in edit mode', async () => {
    mockUpdateProfileApi.mockRejectedValueOnce(
      new Error('Brand name already in use by another merchant.')
    );

    renderBrandInfoSettings();

    fireEvent.click(screen.getByRole('button', { name: /edit brand name/i }));
    const input = screen.getByRole('textbox', { name: /brand name/i });

    fireEvent.change(input, { target: { value: 'Existing Brand' } });
    fireEvent.click(screen.getByRole('button', { name: /save brand name/i }));

    const errorElements = await screen.findAllByText('Brand name already in use by another merchant.');
    expect(errorElements.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('alert')).toHaveTextContent('Brand name already in use by another merchant.');

    // Field should remain in edit mode so user can modify and retry
    expect(input).toBeEnabled();
    expect(screen.getByRole('button', { name: /save brand name/i })).toBeInTheDocument();
  });
});
