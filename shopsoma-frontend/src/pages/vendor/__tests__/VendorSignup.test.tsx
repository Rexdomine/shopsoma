import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import VendorSignup from '../VendorSignup';
import { ROUTES } from '../../../config/constants';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: () => ({ state: null }),
  };
});

describe('VendorSignup - Step 1 Validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an active, clickable submit button instead of a disabled blurred button', () => {
    render(
      <MemoryRouter>
        <VendorSignup />
      </MemoryRouter>
    );

    const nextButton = screen.getByRole('button', { name: /Next: Business Information/i });
    expect(nextButton).toBeInTheDocument();
    expect(nextButton).not.toBeDisabled();
  });

  it('displays clear error messages and validation summary when clicking Next with empty fields', () => {
    render(
      <MemoryRouter>
        <VendorSignup />
      </MemoryRouter>
    );

    const nextButton = screen.getByRole('button', { name: /Next: Business Information/i });
    fireEvent.click(nextButton);

    // Navigation must NOT happen
    expect(mockNavigate).not.toHaveBeenCalled();

    // Summary alert
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Please fill in all required fields:/i)).toBeInTheDocument();

    // Inline field errors and summary list
    expect(screen.getAllByText('First name is required').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Last name is required').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Phone number is required').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Email address is required').length).toBeGreaterThanOrEqual(1);
  });

  it('validates email format and phone number length', () => {
    render(
      <MemoryRouter>
        <VendorSignup />
      </MemoryRouter>
    );

    const firstNameInput = screen.getByPlaceholderText('First Name');
    const lastNameInput = screen.getByPlaceholderText('Last Name');
    const phoneInput = screen.getByPlaceholderText('000 000 0000');
    const emailInput = screen.getByPlaceholderText('example@mail.com');

    fireEvent.change(firstNameInput, { target: { value: 'Amara' } });
    fireEvent.change(lastNameInput, { target: { value: 'Okonkwo' } });
    fireEvent.change(phoneInput, { target: { value: '123' } }); // too short
    fireEvent.change(emailInput, { target: { value: 'not-an-email' } }); // invalid email

    const nextButton = screen.getByRole('button', { name: /Next: Business Information/i });
    fireEvent.click(nextButton);

    expect(mockNavigate).not.toHaveBeenCalled();
    expect(screen.getAllByText('Please enter a valid phone number (7-15 digits)').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Please enter a valid email address (e.g. name@example.com)').length).toBeGreaterThanOrEqual(1);
  });

  it('navigates to business info step with correct payload when form is valid', () => {
    render(
      <MemoryRouter>
        <VendorSignup />
      </MemoryRouter>
    );

    fireEvent.change(screen.getByPlaceholderText('First Name'), { target: { value: 'Amara' } });
    fireEvent.change(screen.getByPlaceholderText('Last Name'), { target: { value: 'Okonkwo' } });
    fireEvent.change(screen.getByPlaceholderText('000 000 0000'), { target: { value: '08012345678' } });
    fireEvent.change(screen.getByPlaceholderText('example@mail.com'), { target: { value: 'amara@example.com' } });

    const nextButton = screen.getByRole('button', { name: /Next: Business Information/i });
    fireEvent.click(nextButton);

    expect(mockNavigate).toHaveBeenCalledWith(ROUTES.VENDOR_SIGNUP_BUSINESS, {
      state: {
        firstName: 'Amara',
        lastName: 'Okonkwo',
        phoneCode: '+234',
        phoneNumber: '08012345678',
        email: 'amara@example.com',
      },
    });
  });
});
