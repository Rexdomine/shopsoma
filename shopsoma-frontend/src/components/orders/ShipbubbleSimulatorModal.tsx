import { useEffect, useState } from 'react';
import type { ShipbubbleTrackingData } from '../../services/orderService';

export interface SimulationStepOption {
  key: string;
  label: string;
  progress: number;
  locationPreview: string;
  description: string;
}

interface ShipbubbleSimulatorModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentStatus: string;
  data: ShipbubbleTrackingData;
  isSimulating: boolean;
  onSimulate: (statusKey: string) => Promise<void> | void;
}

export default function ShipbubbleSimulatorModal({
  isOpen,
  onClose,
  currentStatus,
  data,
  isSimulating,
  onSimulate,
}: ShipbubbleSimulatorModalProps) {
  const [selectedStatus, setSelectedStatus] = useState<string>(currentStatus || 'order_placed');

  useEffect(() => {
    if (isOpen && currentStatus) {
      setSelectedStatus(currentStatus);
    }
  }, [isOpen, currentStatus]);

  if (!isOpen) return null;

  const steps: SimulationStepOption[] = [
    {
      key: 'order_placed',
      label: 'Order Placed',
      progress: 6,
      locationPreview: `${data.origin.name} (${data.origin.city})`,
      description: `Shipment registered with ${data.courier_name} at ${data.origin.city} Hub`,
    },
    {
      key: 'picked_up',
      label: 'Picked Up',
      progress: 28,
      locationPreview: `Departing ${data.origin.city}, ${data.origin.state}`,
      description: `Picked up by ${data.courier_name} — departing ${data.origin.city}`,
    },
    {
      key: 'in_transit',
      label: 'In Transit',
      progress: 60,
      locationPreview: `Mid-route (${data.origin.city} → ${data.destination.city})`,
      description: `In transit with ${data.courier_name} (${data.origin.city} → ${data.destination.city})`,
    },
    {
      key: 'out_for_delivery',
      label: 'Out for Delivery',
      progress: 88,
      locationPreview: `Approaching ${data.destination.city}, ${data.destination.state}`,
      description: `${data.courier_name} rider is out for delivery in ${data.destination.city}`,
    },
    {
      key: 'delivered',
      label: 'Delivered',
      progress: 100,
      locationPreview: `${data.destination.address}`,
      description: `Delivered by ${data.courier_name} in ${data.destination.city}`,
    },
  ];

  const handleApply = async () => {
    await onSimulate(selectedStatus);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 z-[1000]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="shipbubble-sim-modal-title"
    >
      <div className="bg-white rounded-sm sm:rounded-md max-w-lg w-full max-h-[90vh] overflow-y-auto shadow-xl border border-gray-100">
        {/* Modal Header matching Order Details Modal */}
        <div className="sticky top-0 bg-white border-b border-gray-200 px-4 sm:px-6 py-3.5 sm:py-4 flex items-center justify-between z-10">
          <div>
            <h2 id="shipbubble-sim-modal-title" className="text-base sm:text-lg font-semibold text-dark">
              Simulate Tracking Status
            </h2>
            <p className="text-xs text-gray-500 mt-0.5">
              {data.courier_name} • <span className="font-mono text-primary">{data.shipbubble_order_id || 'Sandbox'}</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSimulating}
            className="text-gray-400 hover:text-gray-600 text-2xl leading-none p-1"
            aria-label="Close modal"
          >
            ×
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-4 sm:p-6 space-y-4">
          <p className="text-xs text-gray-600 leading-relaxed">
            Select a tracking milestone below to simulate courier movement from{' '}
            <strong className="text-gray-900">{data.origin.city}</strong> to{' '}
            <strong className="text-gray-900">{data.destination.city}</strong>:
          </p>

          <div className="space-y-2">
            {steps.map((step, idx) => {
              const isSelected = selectedStatus === step.key;
              const isCurrent = currentStatus === step.key;

              return (
                <button
                  key={step.key}
                  type="button"
                  onClick={() => setSelectedStatus(step.key)}
                  disabled={isSimulating}
                  className={`w-full text-left rounded-sm p-3.5 border transition flex items-start gap-3 ${
                    isSelected
                      ? 'border-primary bg-primary/5'
                      : 'border-gray-200 bg-white hover:bg-gray-50'
                  }`}
                >
                  <span
                    className={`w-7 h-7 rounded-full border-2 flex items-center justify-center text-xs font-semibold shrink-0 mt-0.5 ${
                      isSelected
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-gray-200 text-gray-500'
                    }`}
                  >
                    {idx + 1}
                  </span>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span
                        className={`text-xs sm:text-sm font-semibold ${
                          isSelected ? 'text-primary' : 'text-gray-900'
                        }`}
                      >
                        {step.label}
                      </span>
                      <div className="flex items-center gap-1.5">
                        {isCurrent && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-700">
                            Current
                          </span>
                        )}
                        <span className="text-[11px] text-gray-500 font-medium">
                          {step.progress}%
                        </span>
                      </div>
                    </div>
                    <p className="text-xs text-gray-600 mt-1">{step.description}</p>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Modal Footer Actions */}
          <div className="pt-3 border-t border-gray-100 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isSimulating}
              className="px-4 py-2 rounded-sm border border-gray-200 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-50 transition disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleApply}
              disabled={isSimulating}
              className="px-4 py-2 rounded-sm bg-primary text-white text-xs font-semibold hover:bg-primary-dark transition disabled:opacity-50"
            >
              {isSimulating ? 'Updating...' : 'Update Status'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
