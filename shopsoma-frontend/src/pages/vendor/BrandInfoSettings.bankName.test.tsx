import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BrandInfoSettings from './BrandInfoSettings';
import { ROUTES } from '../../config/constants';

const { create, savePayoutInfo, profile } = vi.hoisted(() => ({
  create: vi.fn(), savePayoutInfo: vi.fn(), profile: { is_onboarding: true },
}));
vi.mock('../../context/VendorContext', () => ({ useVendor: () => ({
  vendorProfile: profile, updateProfile: vi.fn(), isOnboarding: false, brandInfoCompleted: true,
}) }));
vi.mock('../../context/AuthContext', () => ({ useAuth: () => ({ user: {} }) }));
vi.mock('../../components/vendor/VendorSidebar', () => ({ default: () => null }));
vi.mock('../../services/vendorPaymentMethodsService', () => ({
  vendorPaymentMethodsService: { list: vi.fn().mockResolvedValue([]), create },
}));
vi.mock('../../services/vendorService', () => ({ vendorService: { savePayoutInfo } }));

async function openForm(bank = 'Other') {
  render(<MemoryRouter initialEntries={[ROUTES.VENDOR_PAYOUT_INFO]}><BrandInfoSettings /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: 'Select bank' }));
  fireEvent.click(screen.getByRole('button', { name: bank }));
  fireEvent.change(screen.getByPlaceholderText('Enter your account number'), { target: { value: '1234567890' } });
  fireEvent.change(screen.getByPlaceholderText('Account holder name'), { target: { value: 'Test Vendor' } });
}

describe('custom bank name limit', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    create.mockResolvedValue({});
    savePayoutInfo.mockResolvedValue(profile);
  });

  it('sets the browser limit and saves a 100-character name to both APIs', async () => {
    await openForm();
    const input = screen.getByPlaceholderText('Enter your bank name');
    expect(input).toHaveAttribute('maxlength', '100');
    fireEvent.change(input, { target: { value: 'B'.repeat(100) } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Payment Method' }));
    await waitFor(() => expect(savePayoutInfo).toHaveBeenCalledWith(expect.objectContaining({ bank_name: 'B'.repeat(100) })));
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ bank_name: 'B'.repeat(100) }));
  });

  it('rejects an oversized value even when the browser limit is bypassed', async () => {
    await openForm();
    fireEvent.change(screen.getByPlaceholderText('Enter your bank name'), { target: { value: 'B'.repeat(101) } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Payment Method' }));
    expect(await screen.findByText('Bank name must be 100 characters or fewer.')).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
    expect(savePayoutInfo).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Add Payment Method' })).toBeEnabled();
  });

  it('still saves a preset bank', async () => {
    await openForm('Providus Bank');
    fireEvent.click(screen.getByRole('button', { name: 'Add Payment Method' }));
    await waitFor(() => expect(savePayoutInfo).toHaveBeenCalledWith(expect.objectContaining({ bank_name: 'Providus Bank' })));
  });
});
