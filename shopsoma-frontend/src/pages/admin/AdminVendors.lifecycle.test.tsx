import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AdminVendors from './AdminVendors';

const mocks = vi.hoisted(() => ({
  listVendors: vi.fn(),
  bulkUpdateUserStatus: vi.fn(),
  toggleUserStatus: vi.fn(),
  restoreVendorStore: vi.fn(),
  updateVendorFeaturedStorefront: vi.fn(),
  resendVendorActivationForVendor: vi.fn(),
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
  role: 'vendor',
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
  activation_resend_eligible: false,
};

const eligibleInactiveVendor = {
  ...vendor,
  id: 'vendor-eligible-inactive',
  user_id: 'eligible-inactive-user',
  email: 'eligible@example.com',
  is_active: false,
  activation_resend_eligible: true,
};
const actingAdminVendor = {
  ...vendor,
  id: 'vendor-admin',
  user_id: 'admin-user',
  email: 'admin@example.com',
  role: 'admin',
  activation_resend_eligible: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listVendors.mockResolvedValue({ items: [vendor, actingAdminVendor], total: 2, total_pages: 1 });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

it('prevents selecting the acting admin vendor account and exposes account status', async () => {
  render(<AdminVendors />);

  expect(await screen.findByRole('checkbox', { name: 'Select admin@example.com' })).toBeDisabled();
  expect(screen.queryByTitle('Mark as test account')).not.toBeInTheDocument();
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

it('hides resend for ineligible vendors', async () => {
  mocks.listVendors.mockResolvedValue({ items: [{ ...vendor, activation_resend_eligible: false }, actingAdminVendor], total: 2, total_pages: 1 });
  render(<AdminVendors />);
  expect(await screen.findAllByText('Vendor One')).not.toHaveLength(0);
  expect(screen.queryByRole('button', { name: 'Resend activation' })).not.toBeInTheDocument();
});

it('respects confirmation cancellation', async () => {
  mocks.listVendors.mockResolvedValue({ items: [eligibleInactiveVendor, actingAdminVendor], total: 2, total_pages: 1 });
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<AdminVendors />);
  fireEvent.click(await screen.findByRole('button', { name: 'Resend activation' }));
  expect(window.confirm).toHaveBeenCalled();
  expect(mocks.resendVendorActivationForVendor).not.toHaveBeenCalled();
});

it('prevents duplicate resends while pending, refreshes, and reports provider acceptance', async () => {
  let resolveRequest!: () => void;
  mocks.listVendors.mockResolvedValue({ items: [eligibleInactiveVendor, actingAdminVendor], total: 2, total_pages: 1 });
  mocks.resendVendorActivationForVendor.mockReturnValue(new Promise<void>((resolve) => { resolveRequest = resolve; }));
  render(<AdminVendors />);
  const resend = await screen.findByRole('button', { name: 'Resend activation' });
  fireEvent.click(resend);
  fireEvent.click(resend);
  expect(mocks.resendVendorActivationForVendor).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'Sending…' })).toBeDisabled();
  resolveRequest();
  expect(await screen.findByRole('alert')).toHaveTextContent('accepted by the email provider');
  await waitFor(() => expect(mocks.listVendors).toHaveBeenCalledTimes(2));
});

it('shows cooldown errors and keeps resend usable after a 429', async () => {
  mocks.listVendors.mockResolvedValue({ items: [eligibleInactiveVendor, actingAdminVendor], total: 2, total_pages: 1 });
  mocks.resendVendorActivationForVendor.mockRejectedValue({ response: { status: 429, data: { detail: 'Try again in 30 seconds' } } });
  render(<AdminVendors />);
  const resend = await screen.findByRole('button', { name: 'Resend activation' });
  fireEvent.click(resend);
  expect(await screen.findByRole('alert')).toHaveTextContent('Try again in 30 seconds');
  fireEvent.click(resend);
  await waitFor(() => expect(mocks.resendVendorActivationForVendor).toHaveBeenCalledTimes(2));
});

it('shows a generic error and keeps resend usable after an ambiguous 503', async () => {
  mocks.listVendors.mockResolvedValue({ items: [eligibleInactiveVendor, actingAdminVendor], total: 2, total_pages: 1 });
  mocks.resendVendorActivationForVendor.mockRejectedValue({ response: { status: 503, data: {} } });
  render(<AdminVendors />);
  const resend = await screen.findByRole('button', { name: 'Resend activation' });
  fireEvent.click(resend);
  expect(await screen.findByRole('alert')).toHaveTextContent('Failed to resend activation email. Please try again.');
  fireEvent.click(resend);
  await waitFor(() => expect(mocks.resendVendorActivationForVendor).toHaveBeenCalledTimes(2));
});
