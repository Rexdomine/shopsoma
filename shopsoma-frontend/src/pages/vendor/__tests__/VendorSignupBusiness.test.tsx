import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import VendorSignupBusiness from '../VendorSignupBusiness';
import { vendorApplicationService } from '../../../services/vendorApplicationService';
import { ROUTES } from '../../../config/constants';

const mockNavigate = vi.fn();

const mockPersonalInfo = {
  firstName: 'Amara',
  lastName: 'Okonkwo',
  email: 'amara@example.com',
  phoneCode: '+234',
  phoneNumber: '08012345678',
};

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useLocation: () => ({ state: mockPersonalInfo }),
  };
});

vi.mock('../../../services/vendorApplicationService', () => ({
  vendorApplicationService: {
    submitApplication: vi.fn(),
  },
}));

describe('VendorSignupBusiness - Step 2 Validation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an active, clickable submit button and a back button', () => {
    render(
      <MemoryRouter>
        <VendorSignupBusiness />
      </MemoryRouter>
    );

    const submitBtn = screen.getByRole('button', { name: /Submit Application/i });
    const backBtn = screen.getByRole('button', { name: /Back to Personal Info/i });

    expect(submitBtn).toBeInTheDocument();
    expect(submitBtn).not.toBeDisabled();
    expect(backBtn).toBeInTheDocument();
  });

  it('displays clear error messages and validation summary when clicking Submit with empty required fields', async () => {
    render(
      <MemoryRouter>
        <VendorSignupBusiness />
      </MemoryRouter>
    );

    const submitBtn = screen.getByRole('button', { name: /Submit Application/i });
    fireEvent.click(submitBtn);

    // API submission must not be called
    expect(vendorApplicationService.submitApplication).not.toHaveBeenCalled();

    // Summary alert
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/Please complete all required fields:/i)).toBeInTheDocument();

    // Inline errors and summary list
    expect(screen.getAllByText('Business name is required').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Business location address is required').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Please select at least one product/service category').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Please select what percentage of your products are made locally').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Please specify how many years you have been in business').length).toBeGreaterThanOrEqual(1);
  });

  it('submits application successfully and navigates to thank you page when all fields are valid', async () => {
    vi.mocked(vendorApplicationService.submitApplication).mockResolvedValueOnce({
      id: 'app-1',
      first_name: 'Amara',
      last_name: 'Okonkwo',
      email: 'amara@example.com',
      business_name: 'Amara Designs',
      status: 'pending_review',
      created_at: new Date().toISOString(),
    });

    render(
      <MemoryRouter>
        <VendorSignupBusiness />
      </MemoryRouter>
    );

    // Fill Business Name
    fireEvent.change(screen.getByPlaceholderText('Business Name'), {
      target: { value: 'Amara Designs' },
    });

    // Fill Location
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. 12 Broad Street/i), {
      target: { value: '12 Broad Street, Lagos' },
    });

    // Select category (checkbox)
    const womensCheckbox = screen.getByLabelText(/Women's Fashion/i);
    fireEvent.click(womensCheckbox);

    // Select locality (radio)
    const localityRadio = screen.getByLabelText(/We source all our products locally - 100%/i);
    fireEvent.click(localityRadio);

    // Fill Years
    fireEvent.change(screen.getByPlaceholderText(/e\.g\., 3 years/i), {
      target: { value: '3 years' },
    });

    // Click submit
    const submitBtn = screen.getByRole('button', { name: /Submit Application/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(vendorApplicationService.submitApplication).toHaveBeenCalledWith({
        firstName: 'Amara',
        lastName: 'Okonkwo',
        email: 'amara@example.com',
        phoneCountryCode: '+234',
        phoneNumber: '08012345678',
        businessName: 'Amara Designs',
        businessLocation: '12 Broad Street, Lagos',
        isBusinessRegistered: undefined,
        productCategories: ['womens'],
        localProductionLevel: 'all',
        yearsInBusiness: '3 years',
        brandStory: undefined,
        websiteLink: undefined,
        socialMediaHandles: undefined,
      });
      expect(mockNavigate).toHaveBeenCalledWith(ROUTES.VENDOR_SIGNUP_THANK_YOU, { replace: true });
    });
  });

  it('displays server error banner if API submission fails', async () => {
    vi.mocked(vendorApplicationService.submitApplication).mockRejectedValueOnce({
      response: {
        data: {
          detail: 'An application with this email already exists.',
        },
      },
    });

    render(
      <MemoryRouter>
        <VendorSignupBusiness />
      </MemoryRouter>
    );

    // Fill all required fields
    fireEvent.change(screen.getByPlaceholderText('Business Name'), { target: { value: 'Amara Designs' } });
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. 12 Broad Street/i), { target: { value: '12 Broad Street, Lagos' } });
    fireEvent.click(screen.getByLabelText(/Women's Fashion/i));
    fireEvent.click(screen.getByLabelText(/We source all our products locally - 100%/i));
    fireEvent.change(screen.getByPlaceholderText(/e\.g\., 3 years/i), { target: { value: '3 years' } });

    // Click submit
    const submitBtn = screen.getByRole('button', { name: /Submit Application/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText('An application with this email already exists.')).toBeInTheDocument();
    });
  });
});
