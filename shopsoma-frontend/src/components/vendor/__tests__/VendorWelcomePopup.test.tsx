import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import VendorWelcomePopup from '../VendorWelcomePopup';

describe('VendorWelcomePopup', () => {
  it('does not render when closed', () => {
    render(
      <VendorWelcomePopup
        isOpen={false}
        onClose={vi.fn()}
        onCompleteProfile={vi.fn()}
      />
    );

    expect(screen.queryByText('Welcome to Shopsoma')).not.toBeInTheDocument();
  });

  it('calls the completion CTA when the vendor chooses to complete profile', () => {
    const onCompleteProfile = vi.fn();

    render(
      <VendorWelcomePopup
        isOpen
        onClose={vi.fn()}
        onCompleteProfile={onCompleteProfile}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /complete profile/i }));

    expect(onCompleteProfile).toHaveBeenCalledTimes(1);
  });
});
