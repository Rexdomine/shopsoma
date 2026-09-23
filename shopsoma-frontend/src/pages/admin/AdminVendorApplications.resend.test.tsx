import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AdminVendorApplications from './AdminVendorApplications';
import AdminVendorApplicationDetail from './AdminVendorApplicationDetail';

const mocks = vi.hoisted(() => ({
  listVendorApplications: vi.fn(), getVendorApplication: vi.fn(), resendVendorActivation: vi.fn(),
  approveVendorApplication: vi.fn(), rejectVendorApplication: vi.fn(), deleteVendorApplication: vi.fn(),
}));
vi.mock('../../components/admin/AdminSidebar', () => ({ default: () => null }));
vi.mock('../../services/adminService', () => ({ adminService: mocks }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn(), useParams: () => ({ id: 'app-1' }) }));

const application = {
  id: 'app-1', first_name: 'Ada', last_name: 'Lovelace', email: 'ada@example.com', phone_country_code: '+1', phone_number: '555',
  business_name: 'Analytical Engines', business_location: 'London', is_business_registered: true, product_categories: ['Fashion'],
  local_production_level: 'high', years_in_business: '2', status: 'approved', created_at: '2026-01-01T00:00:00Z',
  activation_resend_eligible: false,
};
const response = { message: 'accepted', email: application.email };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listVendorApplications.mockResolvedValue({ items: [application], total: 1, total_pages: 1 });
  mocks.getVendorApplication.mockResolvedValue(application);
  mocks.resendVendorActivation.mockResolvedValue(response);
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

it('list hides resend when ineligible and shows accepted-provider success when eligible', async () => {
  render(<AdminVendorApplications />);
  await screen.findByText('Ada Lovelace');
  expect(screen.queryByTitle('Resend activation email')).not.toBeInTheDocument();

  mocks.listVendorApplications.mockResolvedValue({ items: [{ ...application, activation_resend_eligible: true }], total: 1, total_pages: 1 });
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'approved' } });
  const resend = await screen.findByTitle('Resend activation email');
  fireEvent.click(resend);
  expect(window.confirm).toHaveBeenCalledWith('Resend activation email to ada@example.com?');
  await screen.findByText(/accepted by the provider/);
  expect(mocks.resendVendorActivation).toHaveBeenCalledTimes(1);
});

it('list honors confirmation cancellation, pending duplicate guard, and cooldown errors', async () => {
  mocks.listVendorApplications.mockResolvedValue({ items: [{ ...application, activation_resend_eligible: true }], total: 1, total_pages: 1 });
  vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<AdminVendorApplications />);
  const resend = await screen.findByTitle('Resend activation email');
  fireEvent.click(resend);
  expect(mocks.resendVendorActivation).not.toHaveBeenCalled();

  vi.spyOn(window, 'confirm').mockReturnValue(true);
  let reject!: (error: unknown) => void;
  mocks.resendVendorActivation.mockReturnValue(new Promise((_, r) => { reject = r; }));
  fireEvent.click(resend); fireEvent.click(resend);
  expect(mocks.resendVendorActivation).toHaveBeenCalledTimes(1);
  reject({ response: { data: { detail: 'Try again in 30 seconds' } } });
  await screen.findByText('Try again in 30 seconds');
});

it('detail gates ineligible applications and sends eligible applications', async () => {
  render(<AdminVendorApplicationDetail />);
  await screen.findByText('Vendor Application');
  expect(screen.queryByRole('button', { name: /Resend Approval Email/ })).not.toBeInTheDocument();

  // The detail endpoint is authoritative; remount with an eligible response.
  mocks.getVendorApplication.mockResolvedValue({ ...application, activation_resend_eligible: true });
  render(<AdminVendorApplicationDetail />);
  const resend = await screen.findByRole('button', { name: /Resend Approval Email/ });
  fireEvent.click(resend);
  await screen.findByText(/accepted by the provider/);
});
