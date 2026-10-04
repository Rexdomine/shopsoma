import { CheckCircle2, Clock3, PackageCheck, Truck, XCircle } from 'lucide-react';

/** Derived per-item made-to-order lifecycle (mirrors backend readiness_state). */
export type MadeToOrderReadinessState =
  | 'being_prepared'
  | 'ready_for_pickup'
  | 'pickup_scheduled'
  | 'picked_up'
  | 'cancelled';

const STATE_CONFIG: Record<
  MadeToOrderReadinessState,
  { label: string; className: string; Icon: typeof CheckCircle2 }
> = {
  being_prepared: {
    label: 'Not ready yet',
    className: 'bg-amber-50 text-amber-800 border-amber-200',
    Icon: Clock3,
  },
  ready_for_pickup: {
    label: 'Ready for pickup',
    className: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    Icon: CheckCircle2,
  },
  pickup_scheduled: {
    label: 'Pickup scheduled',
    className: 'bg-blue-50 text-blue-700 border-blue-200',
    Icon: Truck,
  },
  picked_up: {
    label: 'Picked up',
    className: 'bg-gray-100 text-gray-700 border-gray-200',
    Icon: PackageCheck,
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-rose-50 text-rose-700 border-rose-200',
    Icon: XCircle,
  },
};

interface MadeToOrderReadinessBadgeProps {
  state?: MadeToOrderReadinessState | null;
  /** Optional label override, e.g. "Being prepared" on the vendor page. */
  label?: string;
}

/**
 * Per-item made-to-order readiness pill shared by vendor and admin order pages.
 * Renders nothing for ready-to-wear items (state null/undefined).
 */
export default function MadeToOrderReadinessBadge({ state, label }: MadeToOrderReadinessBadgeProps) {
  if (!state) return null;
  const config = STATE_CONFIG[state];
  if (!config) return null;
  const { Icon } = config;
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${config.className}`}
      data-testid="mto-readiness-badge"
      data-state={state}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      {label ?? config.label}
    </span>
  );
}

export function MadeToOrderTag() {
  return (
    <span className="inline-flex items-center rounded-full bg-purple-50 px-2.5 py-1 text-xs font-semibold text-purple-700 border border-purple-200">
      Made to order
    </span>
  );
}
