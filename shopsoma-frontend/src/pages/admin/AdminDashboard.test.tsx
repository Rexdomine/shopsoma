import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import AdminDashboard from './AdminDashboard';

vi.mock('../../components/admin/AdminSidebar', () => ({
  default: () => <aside aria-label="Admin navigation" />,
}));

describe('AdminDashboard', () => {
  it('links the overview workspaces to existing admin destinations', () => {
    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Vendor Applications/ })).toHaveAttribute('href', '/admin/vendor-applications');
    expect(screen.getByRole('link', { name: /^Vendors/ })).toHaveAttribute('href', '/admin/vendors');
    expect(screen.getByRole('link', { name: /^Users/ })).toHaveAttribute('href', '/admin/users');
    expect(screen.getByRole('link', { name: /^Orders/ })).toHaveAttribute('href', '/admin/orders');
    expect(screen.getByRole('link', { name: /^Products/ })).toHaveAttribute('href', '/admin/products');
    expect(screen.getByRole('link', { name: /^Payouts/ })).toHaveAttribute('href', '/admin/payouts');
    expect(screen.getByRole('link', { name: /^Settings/ })).toHaveAttribute('href', '/admin/settings');
  });
});
