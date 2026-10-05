import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import Login from './Login';
import Register from './Register';

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    login: vi.fn(),
    register: vi.fn(),
  }),
}));

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({
    toasts: [],
    error: vi.fn(),
    success: vi.fn(),
    warning: vi.fn(),
    hideToast: vi.fn(),
  }),
}));

describe('Social Sign-in Visibility', () => {
  it('does not display Google or Apple sign-in options on the Login page', () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    expect(screen.queryByText(/Sign in with Google/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sign in with Apple/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Or sign in with/i)).not.toBeInTheDocument();
  });

  it('does not display Google or Apple sign-in options on the Register page', () => {
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    expect(screen.queryByText(/Sign up with Google/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Sign in with Apple/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Or continue with/i)).not.toBeInTheDocument();
  });
});
