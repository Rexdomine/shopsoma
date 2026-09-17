import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import AdminDashboard from './AdminDashboard';

vi.mock('../../components/admin/AdminSidebar', () => ({
  default: () => <aside aria-label="Admin navigation" className="w-full md:min-h-screen md:sticky" />,
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
    expect(screen.queryByRole('link', { name: /^Analytics/ })).not.toBeInTheDocument();
  });

  it('stacks the sidebar and overview content on small screens', () => {
    render(
      <MemoryRouter>
        <AdminDashboard />
      </MemoryRouter>,
    );

    expect(screen.getByRole('main')).toHaveClass('flex-1');
    expect(screen.getByRole('main').parentElement).toHaveClass('flex', 'flex-col', 'md:flex-row');
    expect(screen.getByRole('main').previousElementSibling).toHaveClass('w-full', 'md:sticky', 'md:min-h-screen');
  });
});
