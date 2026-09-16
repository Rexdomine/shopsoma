import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import VendorOtp from './VendorOtp';

const { initiateActivationMock } = vi.hoisted(() => ({
  initiateActivationMock: vi.fn(),
}));

vi.mock('../../services/vendorActivationService', () => ({
  vendorActivationService: {
    initiateActivation: initiateActivationMock,
    resendOTP: vi.fn(),
    verifyOTP: vi.fn(),
  },
}));

describe('VendorOtp', () => {
  beforeEach(() => {
    initiateActivationMock.mockReset();
  });

  it('shows a retryable delivery failure instead of an invalid-link screen', async () => {
    initiateActivationMock
      .mockRejectedValueOnce(new Error('Unable to send verification code. Please try again.'))
      .mockResolvedValueOnce({
        message: 'Verification code sent successfully',
        masked_email: 'v***@example.com',
        token: 'activation-token',
      });

    render(
      <MemoryRouter initialEntries={['/vendor/otp?email=vendor@example.com']}>
        <VendorOtp />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Activation Email Unavailable' })).toBeInTheDocument();
    });
    expect(screen.getByText('Unable to send verification code. Please try again.')).toBeInTheDocument();
    expect(screen.queryByText('Invalid Activation Link')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Try Again' }));

    await waitFor(() => expect(initiateActivationMock).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('We sent you a code')).toBeInTheDocument();
  });
});
