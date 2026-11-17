import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AdminMarketing from './AdminMarketing';

const mocks = vi.hoisted(() => ({
  listPromoCodes: vi.fn(),
  createPromoCode: vi.fn(),
  updatePromoCode: vi.fn(),
  deletePromoCode: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('../../components/admin/AdminSidebar', () => ({
  default: () => <aside data-testid="admin-sidebar" />,
}));

vi.mock('../../hooks/useToast', () => ({
  useToast: () => ({
    toasts: [],
    hideToast: vi.fn(),
    success: mocks.toastSuccess,
    error: mocks.toastError,
  }),
}));

vi.mock('../../services/promoCodeService', () => ({
  promoCodeService: {
    listPromoCodes: mocks.listPromoCodes,
    createPromoCode: mocks.createPromoCode,
    updatePromoCode: mocks.updatePromoCode,
    deletePromoCode: mocks.deletePromoCode,
  },
}));

const samplePromo = {
  id: 'promo-1',
  code: 'WELCOME10',
  description: 'Welcome 10% off',
  discount_type: 'percentage' as const,
  discount_value: 10,
  min_purchase_amount: 5000,
  max_discount_amount: 3000,
  usage_limit: 100,
  usage_limit_per_user: 1,
  usage_count: 4,
  valid_from: '2026-01-01T00:00:00Z',
  valid_until: '2030-12-31T23:59:59Z',
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('AdminMarketing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listPromoCodes.mockResolvedValue({
      promo_codes: [samplePromo],
      total: 1,
    });
  });

  it('loads and displays discount codes and creates a new code', async () => {
    const createdPromo = {
      ...samplePromo,
      id: 'promo-2',
      code: 'SAVE2500',
      description: 'Flat NGN discount',
      discount_type: 'fixed_amount' as const,
      discount_value: 2500,
      max_discount_amount: null,
      usage_count: 0,
    };
    mocks.createPromoCode.mockResolvedValueOnce(createdPromo);

    render(
      <MemoryRouter>
        <AdminMarketing />
      </MemoryRouter>,
    );

    expect(await screen.findByText('WELCOME10')).toBeInTheDocument();
    expect(screen.getByText('10% off')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Create Discount Code/i }));
    fireEvent.change(screen.getByLabelText(/Promo Code \*/i), { target: { value: 'save2500' } });
    fireEvent.change(screen.getByLabelText(/Discount Type \*/i), { target: { value: 'fixed_amount' } });
    fireEvent.change(screen.getByLabelText(/Discount Amount/i), { target: { value: '2500' } });
    fireEvent.change(screen.getByLabelText(/Description/i), { target: { value: 'Flat NGN discount' } });

    fireEvent.click(screen.getByRole('button', { name: 'Create Code' }));

    await waitFor(() => {
      expect(mocks.createPromoCode).toHaveBeenCalledWith(
        expect.objectContaining({
          code: 'SAVE2500',
          discount_type: 'fixed_amount',
          discount_value: 2500,
          is_active: true,
        }),
      );
    });
    expect(await screen.findByText('SAVE2500')).toBeInTheDocument();
  });

  it('toggles promo active status and edits/deletes an existing code', async () => {
    mocks.updatePromoCode.mockResolvedValueOnce({
      ...samplePromo,
      is_active: false,
    });
    mocks.deletePromoCode.mockResolvedValueOnce(undefined);

    render(
      <MemoryRouter>
        <AdminMarketing />
      </MemoryRouter>,
    );

    await screen.findByText('WELCOME10');
    fireEvent.click(screen.getByRole('button', { name: 'Deactivate' }));

    await waitFor(() => {
      expect(mocks.updatePromoCode).toHaveBeenCalledWith('promo-1', { is_active: false });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Delete WELCOME10' }));
    fireEvent.click(screen.getByRole('button', { name: 'Delete Code' }));

    await waitFor(() => {
      expect(mocks.deletePromoCode).toHaveBeenCalledWith('promo-1');
    });
    await waitFor(() => {
      expect(screen.queryByText('WELCOME10')).not.toBeInTheDocument();
    });
  });
});
