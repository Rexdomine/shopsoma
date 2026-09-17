import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AdminVendors from './AdminVendors';

const mocks = vi.hoisted(() => ({
  listVendors: vi.fn(),
  bulkUpdateUserStatus: vi.fn(),
  toggleUserStatus: vi.fn(),
  restoreVendorStore: vi.fn(),
  updateVendorFeaturedStorefront: vi.fn(),
}));

vi.mock('../../components/admin/AdminSidebar', () => ({ default: () => null }));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'admin-user' } }),
}));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('../../services/adminService', () => ({ adminService: mocks }));

const vendor = {
  id: 'vendor-1',
  user_id: 'vendor-user',
  business_name: 'Vendor One',
  email: 'vendor@example.com',
  full_name: 'Vendor One',
  approved: true,
  commission_rate: 10,
  is_active: true,
  is_onboarding: false,
  brand_info_completed: true,
  payout_info_completed: true,
  total_products: 1,
  total_orders: 0,
  total_revenue: 0,
  created_at: '2026-01-01T00:00:00Z',
  store_active: true,
};

const actingAdminVendor = { ...vendor, id: 'vendor-admin', user_id: 'admin-user', email: 'admin@example.com' };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listVendors.mockResolvedValue({ items: [vendor, actingAdminVendor], total: 2, total_pages: 1 });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

it('prevents selecting the acting admin vendor account and exposes account status', async () => {
  render(<AdminVendors />);

  expect(await screen.findByRole('checkbox', { name: 'Select admin@example.com' })).toBeDisabled();
  expect(screen.getAllByText('Account Active')).toHaveLength(2);
  const deactivateButtons = screen.getAllByRole('button', { name: 'Deactivate vendor account' });
  expect(deactivateButtons[0]).toBeEnabled();
  expect(deactivateButtons[1]).toBeDisabled();
});

it('keeps selection and shows API detail after a failed bulk update', async () => {
  mocks.bulkUpdateUserStatus.mockRejectedValue({ response: { data: { detail: 'Account status cannot be changed' } } });
  render(<AdminVendors />);

  fireEvent.click(await screen.findByRole('checkbox', { name: 'Select vendor@example.com' }));
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate selected' }));

  await waitFor(() => expect(mocks.bulkUpdateUserStatus).toHaveBeenCalledWith(['vendor-user'], false));
  expect(await screen.findByRole('alert')).toHaveTextContent('Account status cannot be changed');
  expect(screen.getByRole('checkbox', { name: 'Select vendor@example.com' })).toBeChecked();
});
