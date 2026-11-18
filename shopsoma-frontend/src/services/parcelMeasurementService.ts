/**
 * Hub parcel measurement + ShopSoma shipping box presets.
 *
 * DHL bills the greater of actual and volumetric weight, so the hub records the
 * real scale weight and box dimensions of the sealed parcel before booking.
 * The rules below mirror the backend (app/services/dhl/parcel_limits.py) for
 * instant feedback; the backend remains authoritative.
 */
import api from './api';
import type { OrderDetail } from './adminOrderService';

export interface ShippingBoxPreset {
  code: string;
  name: string;
  length_cm: number | string;
  width_cm: number | string;
  height_cm: number | string;
  tare_weight_kg: number | string;
  is_active: boolean;
}

export interface ShippingBoxPresetsResponse {
  presets: ShippingBoxPreset[];
  is_default: boolean;
}

export interface ParcelMeasurementInput {
  box_preset_code?: string | null;
  weight_kg: string;
  length_cm: string;
  width_cm: string;
  height_cm: string;
}

export const DHL_MIN_PIECE_WEIGHT_KG = 0.01;
export const DHL_MAX_PIECE_WEIGHT_KG = 70;
export const DHL_MAX_LONGEST_SIDE_CM = 120;
export const DHL_MAX_OTHER_SIDE_CM = 80;
export const DHL_VOLUMETRIC_DIVISOR = 5000;

export interface ParcelEvaluation {
  errors: string[];
  /** Whole centimetres, longest side first (as DHL will receive them). */
  dims: [number, number, number] | null;
  weightKg: number | null;
  volumetricKg: number | null;
  billableKg: number | null;
}

const toNumber = (value: string | number | null | undefined): number | null => {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : NaN;
};

export function evaluateParcel(input: Pick<ParcelMeasurementInput, 'weight_kg' | 'length_cm' | 'width_cm' | 'height_cm'>): ParcelEvaluation {
  const errors: string[] = [];
  const weight = toNumber(input.weight_kg);
  const raw = [toNumber(input.length_cm), toNumber(input.width_cm), toNumber(input.height_cm)];
  if (weight === null) errors.push('Enter the scale weight');
  else if (Number.isNaN(weight)) errors.push('Weight must be a number');
  else if (weight < DHL_MIN_PIECE_WEIGHT_KG) errors.push(`Weight must be at least ${DHL_MIN_PIECE_WEIGHT_KG} kg`);
  else if (weight > DHL_MAX_PIECE_WEIGHT_KG) errors.push(`Weight exceeds the DHL Express ${DHL_MAX_PIECE_WEIGHT_KG} kg per-piece limit; split the order into smaller parcels`);
  ['Length', 'Width', 'Height'].forEach((label, index) => {
    const value = raw[index];
    if (value === null) errors.push(`Enter the ${label.toLowerCase()}`);
    else if (Number.isNaN(value) || value <= 0) errors.push(`${label} must be greater than 0 cm`);
  });
  if (errors.length) return { errors, dims: null, weightKg: null, volumetricKg: null, billableKg: null };
  const dims = (raw as number[]).map(v => Math.ceil(v)).sort((a, b) => b - a) as [number, number, number];
  if (dims[0] > DHL_MAX_LONGEST_SIDE_CM) errors.push(`Longest side ${dims[0]} cm exceeds the DHL Express ${DHL_MAX_LONGEST_SIDE_CM} cm limit`);
  if (dims[1] > DHL_MAX_OTHER_SIDE_CM) errors.push(`Second side ${dims[1]} cm exceeds the DHL Express ${DHL_MAX_OTHER_SIDE_CM} cm limit`);
  const volumetricKg = Math.ceil((dims[0] * dims[1] * dims[2]) / DHL_VOLUMETRIC_DIVISOR * 100) / 100;
  const billableKg = Math.max(1, Math.ceil(Math.max(weight as number, volumetricKg) / 0.5)) * 0.5;
  return { errors, dims, weightKg: weight as number, volumetricKg, billableKg };
}

export const getShippingBoxPresets = async (): Promise<ShippingBoxPresetsResponse> => {
  const response = await api.get<ShippingBoxPresetsResponse>('/settings/admin/shipping-boxes');
  return response.data;
};

export const updateShippingBoxPresets = async (
  presets: ShippingBoxPreset[]
): Promise<ShippingBoxPresetsResponse> => {
  const response = await api.put<ShippingBoxPresetsResponse>('/settings/admin/shipping-boxes', { presets });
  return response.data;
};

export const recordDhlParcelMeasurement = async (
  orderId: string,
  data: ParcelMeasurementInput
): Promise<OrderDetail> => {
  const response = await api.post<OrderDetail>(
    `/admin/orders/${orderId}/dhl/parcel-measurement`, data, { timeout: 30000 }
  );
  return response.data;
};

/** Human-readable reason from a FastAPI error (string or {message, errors}). */
export function describeApiError(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'errors' in detail && Array.isArray((detail as { errors: unknown }).errors)) {
    return ((detail as { errors: string[] }).errors).join('. ');
  }
  if (Array.isArray(detail)) {
    return detail.map(d => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : '')).filter(Boolean).join('. ') || fallback;
  }
  return fallback;
}
