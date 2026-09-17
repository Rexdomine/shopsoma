import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AdminUsers from './AdminUsers';

const mocks = vi.hoisted(() => ({
  listUsers: vi.fn(),
  bulkUpdateUserStatus: vi.fn(),
  toggleUserStatus: vi.fn(),
  resetUserPassword: vi.fn(),
}));

vi.mock('../../components/admin/AdminSidebar', () => ({ default: () => null }));
vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'admin-user' } }),
}));
vi.mock('../../services/adminService', () => ({ adminService: mocks }));

const customer = {
  id: 'customer-user',
  full_name: 'Customer One',
  email: 'customer@example.com',
  role: 'customer',
  is_active: true,
  email_verified: true,
  created_at: '2026-01-01T00:00:00Z',
  last_login: null,
};

const actingAdmin = {
  id: 'admin-user',
  full_name: 'Admin One',
  email: 'admin@example.com',
  role: 'admin',
  is_active: true,
  email_verified: true,
  created_at: '2026-01-01T00:00:00Z',
  last_login: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.listUsers.mockResolvedValue({ items: [customer, actingAdmin], total: 2, total_pages: 1 });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

it('keeps the selection and shows an accessible error when bulk deactivation fails', async () => {
  mocks.bulkUpdateUserStatus.mockRejectedValue(new Error('Network unavailable'));
  render(<AdminUsers />);

  fireEvent.click(await screen.findByRole('checkbox', { name: 'Select customer@example.com' }));
  expect(screen.getByRole('checkbox', { name: 'Select admin@example.com' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Deactivate selected' }));

  await waitFor(() => expect(mocks.bulkUpdateUserStatus).toHaveBeenCalledWith(['customer-user'], false));
  expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable');
  expect(screen.getByRole('checkbox', { name: 'Select customer@example.com' })).toBeChecked();
});
