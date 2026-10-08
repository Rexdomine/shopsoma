import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import Login from './Login';
import Register from './Register';
import VendorLogin from './VendorLogin';

const mockLogin = vi.fn();
const mockRegister = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../../context/AuthContext', () => ({
  useAuth: () => ({
    user: null,
    isAuthenticated: false,
    login: mockLogin,
    register: mockRegister,
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

vi.mock('../../services/vendorService', () => ({
  vendorService: {
    getProfile: vi.fn().mockResolvedValue({ is_onboarding: false }),
  },
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('Registration Validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
  });

  it('renders sign up button enabled by default and shows field validation errors when submitted empty', async () => {
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    const signUpButton = screen.getByRole('button', { name: /sign up/i });
    expect(signUpButton).not.toBeDisabled();

    fireEvent.click(signUpButton);

    expect(await screen.findByText('Full name is required')).toBeInTheDocument();
    expect(screen.getByText('Email address is required')).toBeInTheDocument();
    expect(screen.getByText('Password is required')).toBeInTheDocument();
    expect(screen.getByText('Please confirm your password')).toBeInTheDocument();
    expect(screen.getByText('Please fix the errors below to continue')).toBeInTheDocument();
    expect(mockRegister).not.toHaveBeenCalled();
  });

  it('validates full name minimum length', async () => {
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    const nameInput = screen.getByLabelText(/full name/i);
    fireEvent.change(nameInput, { target: { value: 'A' } });
    fireEvent.blur(nameInput);

    expect(await screen.findByText('Full name must be at least 2 characters')).toBeInTheDocument();
  });

  it('validates email format on blur and updates when typed', async () => {
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: 'invalid-email' } });
    fireEvent.blur(emailInput);

    expect(await screen.findByText('Please enter a valid email address')).toBeInTheDocument();

    // Now correct it
    fireEvent.change(emailInput, { target: { value: 'valid@example.com' } });
    expect(screen.queryByText('Please enter a valid email address')).not.toBeInTheDocument();
  });

  it('validates password requirements and confirms matching password', async () => {
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    const passwordInput = screen.getByLabelText(/^password/i);
    const confirmInput = screen.getByLabelText(/^confirm password/i);

    // Short password
    fireEvent.change(passwordInput, { target: { value: 'short' } });
    fireEvent.blur(passwordInput);

    expect(await screen.findByText('Password must be at least 8 characters')).toBeInTheDocument();

    // Missing uppercase
    fireEvent.change(passwordInput, { target: { value: 'password123' } });
    expect(await screen.findByText('Password must include at least one uppercase letter')).toBeInTheDocument();

    // Missing number
    fireEvent.change(passwordInput, { target: { value: 'PasswordLetters' } });
    expect(await screen.findByText('Password must include at least one number')).toBeInTheDocument();

    // Valid password
    fireEvent.change(passwordInput, { target: { value: 'Password123' } });
    expect(screen.queryByText(/Password must/i)).not.toBeInTheDocument();

    // Mismatched confirm password
    fireEvent.change(confirmInput, { target: { value: 'Password456' } });
    fireEvent.blur(confirmInput);
    expect(await screen.findByText('Passwords do not match')).toBeInTheDocument();

    // Matched confirm password
    fireEvent.change(confirmInput, { target: { value: 'Password123' } });
    expect(screen.queryByText('Passwords do not match')).not.toBeInTheDocument();
  });

  it('submits successfully when form is valid', async () => {
    mockRegister.mockResolvedValueOnce({ user: { id: '1' } });

    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/full name/i), { target: { value: 'John Doe' } });
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: 'john@example.com' } });
    fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'Password123' } });
    fireEvent.change(screen.getByLabelText(/^confirm password/i), { target: { value: 'Password123' } });

    fireEvent.click(screen.getByRole('button', { name: /sign up/i }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        full_name: 'John Doe',
        email: 'john@example.com',
        password: 'Password123',
        date_of_birth: undefined,
        role: 'customer',
      });
    });
  });

  it('validates guest checkout on Register page', async () => {
    render(
      <MemoryRouter>
        <Register />
      </MemoryRouter>
    );

    const guestButton = screen.getByRole('button', { name: /continue as guest/i });
    expect(guestButton).not.toBeDisabled();

    // Click without entering email
    fireEvent.click(guestButton);
    expect(await screen.findByText('Email address is required')).toBeInTheDocument();

    // Invalid email
    const guestInput = screen.getByLabelText(/^email$/i);
    fireEvent.change(guestInput, { target: { value: 'not-an-email' } });
    fireEvent.click(guestButton);
    expect(await screen.findByText('Please enter a valid email address')).toBeInTheDocument();

    // Valid email
    fireEvent.change(guestInput, { target: { value: 'guest@example.com' } });
    fireEvent.click(guestButton);

    await waitFor(() => {
      expect(sessionStorage.getItem('shopsoma_guest_email')).toBe('guest@example.com');
      expect(mockNavigate).toHaveBeenCalledWith('/cart', {
        state: { guestEmail: 'guest@example.com', guestNewsletter: false },
      });
    });
  });
});

describe('Login Validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login button enabled by default and shows validation errors when submitted empty', async () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const loginButton = screen.getByRole('button', { name: /^login$/i });
    expect(loginButton).not.toBeDisabled();

    fireEvent.click(loginButton);

    expect(await screen.findByText('Email address is required')).toBeInTheDocument();
    expect(screen.getByText('Password is required')).toBeInTheDocument();
    expect(screen.getByText('Please fix the errors below to continue')).toBeInTheDocument();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('validates email format on blur and submit', async () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: 'bademail' } });
    fireEvent.blur(emailInput);

    expect(await screen.findByText('Please enter a valid email address')).toBeInTheDocument();
  });

  it('submits successfully when credentials are provided', async () => {
    mockLogin.mockResolvedValueOnce({ user: { id: '1', role: 'customer' } });

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: 'user@example.com' } });
    fireEvent.change(screen.getByLabelText(/^password/i), { target: { value: 'password123' } });

    fireEvent.click(screen.getByRole('button', { name: /^login$/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        email: 'user@example.com',
        password: 'password123',
      });
    });
  });

  it('displays error banner and retains input values when email or password is wrong', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid email or password'));

    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const emailInput = screen.getByLabelText(/email address/i);
    const passwordInput = screen.getByLabelText(/^password/i);

    fireEvent.change(emailInput, { target: { value: 'user@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } });

    fireEvent.click(screen.getByRole('button', { name: /^login$/i }));

    expect(await screen.findByText('Invalid email or password')).toBeInTheDocument();
    expect(emailInput).toHaveValue('user@example.com');
  });

  it('validates guest checkout on Login page', async () => {
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    const guestButtons = screen.getAllByRole('button', { name: /continue as guest/i });
    const guestButton = guestButtons[0];
    expect(guestButton).not.toBeDisabled();

    // Click without entering email
    fireEvent.click(guestButton);
    expect(await screen.findByText('Email address is required')).toBeInTheDocument();

    // Invalid email
    const guestInput = screen.getByLabelText(/^email$/i);
    fireEvent.change(guestInput, { target: { value: 'invalid-guest' } });
    fireEvent.click(guestButton);
    expect(await screen.findByText('Please enter a valid email address')).toBeInTheDocument();

    // Valid email
    fireEvent.change(guestInput, { target: { value: 'guestlogin@example.com' } });
    fireEvent.click(guestButton);

    await waitFor(() => {
      expect(sessionStorage.getItem('shopsoma_guest_email')).toBe('guestlogin@example.com');
      expect(mockNavigate).toHaveBeenCalledWith('/cart', {
        state: { guestEmail: 'guestlogin@example.com', guestNewsletter: false },
      });
    });
  });
});

describe('VendorLogin Validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders login button enabled by default and shows validation errors when submitted empty', async () => {
    render(
      <MemoryRouter>
        <VendorLogin />
      </MemoryRouter>
    );

    const loginButton = screen.getByRole('button', { name: /^log in$/i });
    expect(loginButton).not.toBeDisabled();

    fireEvent.click(loginButton);

    expect(await screen.findByText('Email address is required')).toBeInTheDocument();
    expect(screen.getByText('Password is required')).toBeInTheDocument();
    expect(screen.getByText('Please fix the errors below to continue')).toBeInTheDocument();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('validates email format on blur and submit', async () => {
    render(
      <MemoryRouter>
        <VendorLogin />
      </MemoryRouter>
    );

    const emailInput = screen.getByPlaceholderText('example@mail.com');
    fireEvent.change(emailInput, { target: { value: 'not-an-email' } });
    fireEvent.blur(emailInput);

    expect(await screen.findByText('Please enter a valid email address')).toBeInTheDocument();

    // Fix it
    fireEvent.change(emailInput, { target: { value: 'vendor@example.com' } });
    expect(screen.queryByText('Please enter a valid email address')).not.toBeInTheDocument();
  });

  it('submits successfully when credentials are valid', async () => {
    mockLogin.mockResolvedValueOnce({ user: { id: 'v1', role: 'vendor' } });

    render(
      <MemoryRouter>
        <VendorLogin />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('example@mail.com'), {
      target: { value: 'vendor@example.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('Password'), {
      target: { value: 'Secret123' },
    });

    fireEvent.click(screen.getByRole('button', { name: /^log in$/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({
        email: 'vendor@example.com',
        password: 'Secret123',
      });
    });
  });

  it('displays attempt limit banner on backend auth error', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid password. 3 attempts left'));

    render(
      <MemoryRouter>
        <VendorLogin />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('example@mail.com'), {
      target: { value: 'vendor@example.com' },
    });
    fireEvent.change(screen.getByPlaceholderText('Password'), {
      target: { value: 'WrongPassword' },
    });

    fireEvent.click(screen.getByRole('button', { name: /^log in$/i }));

    expect(await screen.findByText(/Wrong password code\. 3 Attempts left/i)).toBeInTheDocument();
  });

  it('displays error banner and retains input values when email or password is wrong', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid email or password'));

    render(
      <MemoryRouter>
        <VendorLogin />
      </MemoryRouter>
    );

    const emailInput = screen.getByPlaceholderText('example@mail.com');
    const passwordInput = screen.getByPlaceholderText('Password');

    fireEvent.change(emailInput, { target: { value: 'vendor@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'WrongPassword' } });

    fireEvent.click(screen.getByRole('button', { name: /^log in$/i }));

    expect(await screen.findByText('Invalid email or password')).toBeInTheDocument();
    expect(emailInput).toHaveValue('vendor@example.com');
    expect(passwordInput).toHaveValue('WrongPassword');
  });
});
