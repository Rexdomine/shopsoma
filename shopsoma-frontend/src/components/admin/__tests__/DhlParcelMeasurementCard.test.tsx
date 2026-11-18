import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import DhlParcelMeasurementCard from '../DhlParcelMeasurementCard';
import type { DhlOperationPackage, OrderDetail } from '../../../services/adminOrderService';
import { evaluateParcel } from '../../../services/parcelMeasurementService';

const mocks = vi.hoisted(() => ({
  getShippingBoxPresets: vi.fn(),
  recordDhlParcelMeasurement: vi.fn(),
}));

vi.mock('../../../services/parcelMeasurementService', async () => {
  const actual = await vi.importActual<typeof import('../../../services/parcelMeasurementService')>(
    '../../../services/parcelMeasurementService'
  );
  return { ...actual, ...mocks };
});

const order = { id: 'order-1', order_number: 'SHP-1' } as unknown as OrderDetail;

const estimatedPkg = (overrides: Partial<DhlOperationPackage> = {}): DhlOperationPackage => ({
  package_id: 'pkg-1',
  package_version: 1,
  origin_hub_id: 'hub-1',
  package_state: 'ready',
  ready_at: '2026-11-18T10:00:00Z',
  seal_id: 'seal-1',
  intent_id: 'intent-1',
  active_booking_id: null,
  selection_eligible: false,
  selection_blockers: ['parcel_not_measured'],
  parcel: {
    measurement_source: 'estimated',
    box_preset_code: null,
    weight_kg: '1.800',
    length_cm: '35.000',
    width_cm: '28.000',
    height_cm: '12.000',
    volumetric_weight_kg: '2.36',
    billable_weight_kg: '2.5',
    estimated_contents_weight_kg: '1.800',
  },
  ...overrides,
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getShippingBoxPresets.mockResolvedValue({
    is_default: false,
    presets: [
      { code: 'SS-M', name: 'Medium box', length_cm: 40, width_cm: 30, height_cm: 15, tare_weight_kg: 0.35, is_active: true },
    ],
  });
});

afterEach(() => cleanup());

describe('evaluateParcel (mirrors backend DHL rules)', () => {
  it('rounds up to whole cm, orders longest first and computes billable weight', () => {
    const result = evaluateParcel({ weight_kg: '1.2', length_cm: '14.1', width_cm: '39.2', height_cm: '29.6' });
    expect(result.errors).toEqual([]);
    expect(result.dims).toEqual([40, 30, 15]);
    expect(result.volumetricKg).toBe(3.6);
    expect(result.billableKg).toBe(4);
  });

  it('rejects pieces DHL Express will not accept', () => {
    expect(evaluateParcel({ weight_kg: '71', length_cm: '40', width_cm: '30', height_cm: '15' }).errors[0]).toMatch(/70 kg/);
    expect(evaluateParcel({ weight_kg: '2', length_cm: '121', width_cm: '30', height_cm: '15' }).errors[0]).toMatch(/Longest side 121 cm/);
    expect(evaluateParcel({ weight_kg: '2', length_cm: '100', width_cm: '81', height_cm: '15' }).errors[0]).toMatch(/Second side 81 cm/);
  });
});

describe('DhlParcelMeasurementCard', () => {
  it('flags an estimated parcel and saves the scale weight with the selected box', async () => {
    const onOrderChange = vi.fn();
    const fresh = { ...order, dhl_operations: { packages: [], bookings: [] } } as unknown as OrderDetail;
    mocks.recordDhlParcelMeasurement.mockResolvedValue(fresh);
    render(<DhlParcelMeasurementCard order={order} pkg={estimatedPkg()} onOrderChange={onOrderChange} />);

    expect(screen.getByText('Estimated — not yet measured')).toBeInTheDocument();
    const select = await screen.findByLabelText('ShopSoma box');
    await screen.findByRole('option', { name: /Medium box/ });
    fireEvent.change(select, { target: { value: 'SS-M' } });

    // Box dimensions are filled from the preset and locked.
    expect(screen.getByLabelText('Length (cm)')).toHaveValue(40);
    expect(screen.getByLabelText('Length (cm)')).toBeDisabled();
    // Suggestion = catalog contents + empty box weight.
    expect(screen.getByText(/~2\.15 kg/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Scale weight (kg)'), { target: { value: '2.137' } });
    expect(screen.getByText(/billable 4 kg/)).toBeInTheDocument();

    const save = screen.getByRole('button', { name: 'Save parcel measurements' });
    expect(save).toBeDisabled(); // requires the "weighed on scale" confirmation
    fireEvent.click(screen.getByLabelText(/I weighed the sealed parcel/));
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => expect(mocks.recordDhlParcelMeasurement).toHaveBeenCalledWith('order-1', {
      box_preset_code: 'SS-M',
      weight_kg: '2.137',
      length_cm: '40',
      width_cm: '30',
      height_cm: '15',
    }));
    expect(onOrderChange).toHaveBeenCalledWith(fresh);
  });

  it('blocks saving values DHL would reject and shows the backend reason on failure', async () => {
    mocks.recordDhlParcelMeasurement.mockRejectedValue({
      response: { data: { detail: 'a DHL shipment already exists for this parcel; cancel it with DHL before re-measuring' } },
    });
    render(<DhlParcelMeasurementCard order={order} pkg={estimatedPkg()} onOrderChange={vi.fn()} />);
    await screen.findByRole('option', { name: /Medium box/ });
    fireEvent.change(screen.getByLabelText('ShopSoma box'), { target: { value: '__custom__' } });
    fireEvent.change(screen.getByLabelText('Length (cm)'), { target: { value: '130' } });
    fireEvent.change(screen.getByLabelText('Width (cm)'), { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText('Height (cm)'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('Scale weight (kg)'), { target: { value: '3' } });
    fireEvent.click(screen.getByLabelText(/I weighed the sealed parcel/));

    expect(screen.getByText(/Longest side 130 cm exceeds/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save parcel measurements' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Length (cm)'), { target: { value: '50' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save parcel measurements' }));
    expect(await screen.findByText(/already exists for this parcel/)).toBeInTheDocument();
  });

  it('shows booked measurements read-only', async () => {
    const pkg = estimatedPkg({
      selection_blockers: ['active_booking_exists'],
      parcel: { ...estimatedPkg().parcel!, measurement_source: 'hub_measured', box_preset_code: 'SS-M' },
    });
    render(<DhlParcelMeasurementCard order={order} pkg={pkg} onOrderChange={vi.fn()} />);
    expect(screen.getByText('Hub measured')).toBeInTheDocument();
    expect(screen.getByText(/can no longer be changed/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save parcel measurements' })).not.toBeInTheDocument();
    expect(screen.queryByText('Re-measure parcel')).not.toBeInTheDocument();
  });
});
