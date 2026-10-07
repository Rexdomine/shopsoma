import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Header from './Header';

const mockNavigate = vi.fn();
const mockLogout = vi.fn();

let mockAuthUser: any = null;
let mockIsAuthenticated = false;

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: mockAuthUser,
    isAuthenticated: mockIsAuthenticated,
    logout: mockLogout,
  }),
}));

vi.mock('../../store/currencyStore', () => ({
  useCurrencyStore: () => ({
    currentCurrency: 'NGN',
    setCurrency: vi.fn(),
    commerceFeatures: { usd_switching_enabled: true },
  }),
}));

vi.mock('../../store/preferenceStore', () => ({
  usePreferenceStore: () => vi.fn(),
}));

vi.mock('../../store/cartStore', () => ({
  useCartStore: (selector: (state: { cart: { summary: { itemCount: number } } }) => unknown) =>
    selector({ cart: { summary: { itemCount: 2 } } }),
}));

describe('Header Account Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders guest menu in account dropdown when not logged in', () => {
    mockIsAuthenticated = false;
    mockAuthUser = null;

    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>
    );

    const accountButton = screen.getByRole('button', { name: 'Account' });
    expect(accountButton).toBeInTheDocument();

    // Dropdown is not visible initially
    expect(screen.queryByText('Sign In')).not.toBeInTheDocument();

    // Click to open dropdown
    fireEvent.click(accountButton);

    expect(screen.getByRole('link', { name: 'Sign In' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Create Account' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Track an Order' })).toBeInTheDocument();
  });

  it('renders customer account dropdown with My Orders when authenticated', async () => {
    mockIsAuthenticated = true;
    mockAuthUser = {
      id: 'customer-1',
      email: 'customer@shopsoma.com',
      full_name: 'Kayode Atteh',
      role: 'customer',
    };

    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>
    );

    const accountButton = screen.getByRole('button', { name: 'Account' });
    expect(accountButton).toHaveTextContent('KA'); // initials

    // Click to open dropdown
    fireEvent.click(accountButton);

    expect(screen.getByText('Kayode Atteh')).toBeInTheDocument();
    expect(screen.getByText('customer@shopsoma.com')).toBeInTheDocument();

    const myOrdersLink = screen.getByRole('link', { name: /My Orders/i });
    expect(myOrdersLink).toBeInTheDocument();
    expect(myOrdersLink).toHaveAttribute('href', '/orders');

    const accountDetailsLink = screen.getByRole('link', { name: /Account Details/i });
    expect(accountDetailsLink).toBeInTheDocument();
    expect(accountDetailsLink).toHaveAttribute('href', '/profile');

    const signOutBtn = screen.getByRole('button', { name: /Sign Out/i });
    expect(signOutBtn).toBeInTheDocument();
    fireEvent.click(signOutBtn);
    expect(mockLogout).toHaveBeenCalled();
  });

  it('renders My Orders in mobile drawer when authenticated', () => {
    mockIsAuthenticated = true;
    mockAuthUser = {
      id: 'customer-1',
      email: 'customer@shopsoma.com',
      full_name: 'Kayode Atteh',
      role: 'customer',
    };

    render(
      <MemoryRouter>
        <Header />
      </MemoryRouter>
    );

    // Open mobile menu
    const menuButton = screen.getByLabelText('Open menu');
    fireEvent.click(menuButton);

    const mobileMyOrdersLinks = screen.getAllByRole('link', { name: /My Orders/i });
    expect(mobileMyOrdersLinks.length).toBeGreaterThan(0);
    expect(mobileMyOrdersLinks[0]).toHaveAttribute('href', '/orders');
  });
});
