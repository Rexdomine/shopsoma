import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import {
  orderService,
  type OrderStatus,
  type OrderTracking,
  type TrackingHistory,
} from '../../services/orderService';
import { useAuthStore } from '../../store/authStore';
import { loadCheckoutCapability } from '../../utils/checkoutCapability';
import ShipbubbleLiveMap from '../../components/orders/ShipbubbleLiveMap';
import ShipbubbleSimulatorModal from '../../components/orders/ShipbubbleSimulatorModal';

const VERTICAL_STATUS_STEPS = [
  {
    key: 'order_placed',
    label: 'Order Placed',
    description: 'Shipment registered and prepared for dispatch at origin hub',
  },
  {
    key: 'picked_up',
    label: 'Picked Up',
    description: 'Courier rider has collected the package from the hub',
  },
  {
    key: 'in_transit',
    label: 'In Transit',
    description: 'Package is moving along the interstate highway route',
  },
  {
    key: 'out_for_delivery',
    label: 'Out for Delivery',
    description: 'Courier is in your area for final doorstep delivery',
  },
  {
    key: 'delivered',
    label: 'Delivered',
    description: 'Package has been delivered and confirmed at destination',
  },
];

const STATUS_ALIASES: Record<string, string> = {
  pending: 'order_placed',
  processing: 'order_placed',
  preparing_for_pickup: 'order_placed',
  pickup_scheduled: 'order_placed',
  order_placed: 'order_placed',
  picked_up: 'picked_up',
  shipped: 'in_transit',
  in_transit: 'in_transit',
  out_for_delivery: 'out_for_delivery',
  delivered: 'delivered',
};

function normalizeStatusKey(status?: string) {
  if (!status) return 'order_placed';
  const normalized = status.toLowerCase().trim().replace(/[\s-]+/g, '_');
  return STATUS_ALIASES[normalized] || normalized;
}

function formatDisplayDate(value?: string) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function OrderMapTracking() {
  const { orderId } = useParams<{ orderId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { user } = useAuthStore();

  const [tracking, setTracking] = useState<OrderTracking | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isSimulating, setIsSimulating] = useState(false);
  const [isSimModalOpen, setIsSimModalOpen] = useState(false);
  const requestSeqRef = useRef(0);

  const fetchTracking = async (silent = false) => {
    if (!orderId) return;
    const seq = ++requestSeqRef.current;
    if (!silent) setLoading(true);
    try {
      const data = await orderService.getOrderTracking(orderId, loadCheckoutCapability(orderId));
      if (seq !== requestSeqRef.current) return;
      setTracking(data);
      setError(null);
    } catch {
      if (seq !== requestSeqRef.current) return;
      setError('Unable to load live map tracking for this order.');
    } finally {
      if (seq === requestSeqRef.current && !silent) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    void fetchTracking(false);
    const interval = window.setInterval(() => {
      void fetchTracking(true);
    }, 12000);
    return () => window.clearInterval(interval);
  }, [orderId]);

  const handleSyncShipbubble = async () => {
    if (!orderId || isSyncing) return;
    setIsSyncing(true);
    try {
      const updated = await orderService.syncOrderTracking(orderId, loadCheckoutCapability(orderId));
      setTracking(updated);
    } catch {
      // Keep current state
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSimulateShipbubble = async (statusKey: string) => {
    if (!orderId || isSimulating) return;
    setIsSimulating(true);
    try {
      const updated = await orderService.simulateOrderTracking(
        orderId,
        statusKey as OrderStatus,
        loadCheckoutCapability(orderId)
      );
      setTracking(updated);
    } catch {
      // Keep current state
    } finally {
      setIsSimulating(false);
    }
  };

  const normalizedStatus = useMemo(
    () => normalizeStatusKey(tracking?.current_status),
    [tracking?.current_status]
  );

  const activeIndex = useMemo(() => {
    const idx = VERTICAL_STATUS_STEPS.findIndex((s) => s.key === normalizedStatus);
    return idx >= 0 ? idx : 0;
  }, [normalizedStatus]);

  const sbData = tracking?.shipbubble_tracking;
  const progressPct = Math.round((sbData?.current_location?.progress ?? 0.06) * 100);

  const navState = location.state as { from?: string; fromLabel?: string } | null;
  const stateFrom = navState?.from;
  const isAdminUser = user?.role?.toLowerCase() === 'admin';
  const isFromAdmin = Boolean(
    stateFrom?.startsWith('/admin') ||
    searchParams.get('from') === 'admin' ||
    (isAdminUser && !stateFrom?.startsWith('/track'))
  );

  const backRoute =
    stateFrom ||
    (isFromAdmin && orderId
      ? `/admin/orders/${orderId}`
      : orderId
      ? ROUTES.ORDER_TRACKING.replace(':orderId', orderId)
      : ROUTES.ORDERS);

  const backLabel =
    navState?.fromLabel ||
    (isFromAdmin ? 'Back to Admin Order' : 'Back to Order Tracking');

  return (
    <div className="min-h-screen lg:h-screen bg-white flex flex-col lg:overflow-hidden">
      {/* Top Header Bar Matching Platform Style */}
      <header className="bg-white border-b border-gray-100 px-4 sm:px-8 py-4 flex items-center justify-between gap-3 shrink-0 z-20">
        <div className="flex items-center gap-3 sm:gap-4">
          <Link
            to={isFromAdmin ? '/admin/orders' : ROUTES.HOME}
            className="text-3xl sm:text-4xl text-primary leading-none shrink-0"
            style={{ fontFamily: 'Lao MN, var(--font-display, serif)' }}
            aria-label="Shopsoma home"
          >
            S
          </Link>
          <button
            type="button"
            onClick={() => navigate(backRoute)}
            className="text-xs sm:text-sm text-gray-600 hover:text-primary transition flex items-center gap-1 py-1"
          >
            <span>←</span>
            <span>{backLabel}</span>
          </button>
        </div>

        {/* Right Quick Actions Matching Platform Buttons */}
        <div className="flex items-center gap-2 sm:gap-3">
          {sbData?.is_sandbox && (
            <button
              type="button"
              onClick={() => setIsSimModalOpen(true)}
              className="px-3.5 py-2 border border-gray-200 bg-white text-gray-700 text-xs font-semibold rounded-sm hover:bg-gray-50 transition"
            >
              Simulate Tracking
            </button>
          )}
          {sbData?.tracking_url && (
            <a
              href={sbData.tracking_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hidden md:inline-flex items-center gap-1 px-3.5 py-2 border border-gray-200 bg-white text-gray-700 text-xs font-semibold rounded-sm hover:bg-gray-50 transition"
            >
              <span>ShipBubble Portal</span>
              <span>↗</span>
            </a>
          )}
          <button
            type="button"
            onClick={handleSyncShipbubble}
            disabled={isSyncing || isSimulating}
            className="px-4 py-2 bg-primary text-white text-xs font-semibold rounded-sm hover:bg-primary-dark transition disabled:opacity-50"
          >
            {isSyncing ? 'Syncing...' : 'Sync Status'}
          </button>
        </div>
      </header>

      {/* Main Split View: Left Clean White Sidebar + Right Full-Bleed Map */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center space-y-2">
            <p className="text-sm text-gray-500">Fetching latest map tracking updates...</p>
          </div>
        </div>
      ) : error || !tracking || !sbData ? (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-md w-full bg-white rounded-sm border border-gray-100 p-6 text-center space-y-4 shadow-sm">
            <p className="text-sm font-semibold text-gray-800">
              {error || 'Live map tracking is not available for this order.'}
            </p>
            <Link
              to={backRoute}
              className="inline-flex items-center justify-center px-4 py-2 rounded-sm bg-primary text-white text-xs font-semibold hover:bg-primary-dark transition"
            >
              ← {backLabel}
            </Link>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex flex-col lg:flex-row lg:overflow-hidden">
          {/* Left Panel: Clean White Courier Summary + Vertical Tracking Timeline */}
          <aside className="w-full lg:w-[400px] xl:w-[430px] bg-white border-b lg:border-b-0 lg:border-r border-gray-100 lg:overflow-y-auto shrink-0 p-5 sm:p-6 space-y-6">
            {/* Clean White Courier & Route Card */}
            <div className="rounded-sm border border-gray-100 bg-gray-50/60 p-4 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  {sbData.courier_image ? (
                    <img
                      src={sbData.courier_image}
                      alt={sbData.courier_name}
                      className="w-11 h-11 rounded-full object-cover bg-white border border-gray-200 shrink-0"
                    />
                  ) : (
                    <div className="w-11 h-11 rounded-full bg-primary/10 text-primary flex items-center justify-center text-sm font-semibold shrink-0">
                      SB
                    </div>
                  )}
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h1 className="text-sm font-semibold text-gray-900">
                        {sbData.courier_name}
                      </h1>
                    </div>
                    <p className="text-xs text-primary font-mono mt-0.5">
                      {sbData.shipbubble_order_id || tracking.tracking_id}
                    </p>
                  </div>
                </div>
                <span className="px-2.5 py-1 rounded-sm bg-white border border-gray-200 text-[11px] font-medium text-gray-700 shrink-0">
                  ETA: {sbData.delivery_eta}
                </span>
              </div>

              {/* Route Progress Bar */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-600">
                    {sbData.current_location.status_label}
                  </span>
                  <span className="font-semibold text-primary">{progressPct}%</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-gray-200 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-primary transition-all duration-700"
                    style={{ width: `${Math.max(6, progressPct)}%` }}
                  />
                </div>
              </div>

              {/* Origin -> Destination Endpoints */}
              <div className="grid grid-cols-2 gap-3 pt-3 border-t border-gray-200/70 text-xs">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-gray-400 font-medium">
                    Origin Hub
                  </p>
                  <p className="font-semibold text-gray-800 truncate mt-0.5">
                    {sbData.origin.city}, {sbData.origin.state}
                  </p>
                  <p className="text-[11px] text-gray-500 truncate">{sbData.origin.name}</p>
                </div>
                <div>
                  <p className="text-[10px] uppercase tracking-[0.18em] text-gray-400 font-medium">
                    Destination
                  </p>
                  <p className="font-semibold text-gray-800 truncate mt-0.5">
                    {sbData.destination.city}, {sbData.destination.state}
                  </p>
                  <p className="text-[11px] text-gray-500 truncate">{sbData.destination.name}</p>
                </div>
              </div>
            </div>

            {/* Vertical Shipment Tracking Stepper */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-[10px] sm:text-xs uppercase tracking-[0.2em] text-gray-400 font-medium">
                  Tracking Progress
                </p>
                <span className="text-xs text-gray-400">
                  Step {activeIndex + 1} of {VERTICAL_STATUS_STEPS.length}
                </span>
              </div>

              <div className="relative pl-1 pt-1">
                {VERTICAL_STATUS_STEPS.map((step, index) => {
                  const isActive = index <= activeIndex;
                  const isCurrent = index === activeIndex;
                  const isLast = index === VERTICAL_STATUS_STEPS.length - 1;

                  const matchedHistory = tracking.history?.find(
                    (h: TrackingHistory) => normalizeStatusKey(h.status) === step.key
                  );

                  return (
                    <div key={step.key} className="relative flex items-start gap-3.5 pb-6 last:pb-1">
                      {/* Vertical Connecting Line */}
                      {!isLast && (
                        <div
                          className={`absolute left-[15px] top-8 bottom-0 w-px transition-colors ${
                            index < activeIndex ? 'bg-primary' : 'bg-gray-200'
                          }`}
                        />
                      )}

                      {/* Step Circle Indicator (matches horizontal stepper style) */}
                      <span
                        className={`relative z-10 w-8 h-8 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors bg-white ${
                          isActive
                            ? 'border-primary bg-primary/10 text-primary'
                            : 'border-gray-200 text-gray-400'
                        } ${isCurrent ? 'ring-2 ring-primary/20' : ''}`}
                      >
                        <span className="text-xs font-semibold">{index + 1}</span>
                      </span>

                      {/* Step Content */}
                      <div className="flex-1 min-w-0 pt-0.5">
                        <div className="flex items-center justify-between gap-2">
                          <p
                            className={`text-xs sm:text-sm ${
                              isCurrent
                                ? 'text-primary font-semibold'
                                : isActive
                                ? 'text-gray-800 font-medium'
                                : 'text-gray-400'
                            }`}
                          >
                            {step.label}
                          </p>
                          {isCurrent && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/10 text-primary">
                              Current
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mt-0.5 leading-relaxed">
                          {step.description}
                        </p>
                        {matchedHistory?.occurred_at && isActive && (
                          <p className="text-[11px] text-gray-400 mt-1">
                            {formatDisplayDate(matchedHistory.occurred_at)}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Sandbox Simulator Trigger Button */}
            {sbData.is_sandbox && (
              <div className="pt-3 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setIsSimModalOpen(true)}
                  className="w-full py-2.5 px-4 rounded-sm border border-gray-200 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 transition"
                >
                  Simulate Tracking Status
                </button>
              </div>
            )}
          </aside>

          {/* Right Panel: Full-Bleed Edge-to-Edge Interactive Leaflet Map */}
          <main className="flex-1 min-h-[560px] lg:min-h-0 lg:h-full relative">
            <ShipbubbleLiveMap
              data={sbData}
              currentStatus={normalizedStatus}
              isSyncing={isSyncing}
              isSimulating={isSimulating}
              onSync={handleSyncShipbubble}
              onSimulate={handleSimulateShipbubble}
              fullBleed={true}
            />
          </main>
        </div>
      )}

      {sbData && (
        <ShipbubbleSimulatorModal
          isOpen={isSimModalOpen}
          onClose={() => setIsSimModalOpen(false)}
          currentStatus={normalizedStatus}
          data={sbData}
          isSimulating={isSimulating}
          onSimulate={handleSimulateShipbubble}
        />
      )}
    </div>
  );
}
