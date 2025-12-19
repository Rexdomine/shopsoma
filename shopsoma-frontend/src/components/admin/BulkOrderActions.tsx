/**
 * Bulk Order Actions Component
 * Bulk actions for selected orders
 */
import React, { useState } from 'react';
import type { FulfillmentStatus } from '../../services/adminOrderService';

interface BulkOrderActionsProps {
  selectedOrderIds: string[];
  onBulkUpdate: (status: FulfillmentStatus, notes?: string) => Promise<void>;
  onClearSelection: () => void;
  loading?: boolean;
}

export default function BulkOrderActions({
  selectedOrderIds,
  onBulkUpdate,
  onClearSelection,
  loading,
}: BulkOrderActionsProps) {
  const [selectedStatus, setSelectedStatus] = useState<FulfillmentStatus | ''>('');
  const [notes, setNotes] = useState('');
  const [showNotesInput, setShowNotesInput] = useState(false);

  const handleUpdate = async () => {
    if (!selectedStatus) {
      alert('Please select a status');
      return;
    }

    try {
      await onBulkUpdate(selectedStatus as FulfillmentStatus, notes || undefined);
      setSelectedStatus('');
      setNotes('');
      setShowNotesInput(false);
    } catch (error) {
      console.error('Bulk update failed:', error);
    }
  };

  if (selectedOrderIds.length === 0) {
    return null;
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-4 mb-6">
      <div className="flex items-center gap-4 flex-wrap">
        {/* Selection Info */}
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-900">
            {selectedOrderIds.length} order{selectedOrderIds.length !== 1 ? 's' : ''} selected
          </span>
          <button
            onClick={onClearSelection}
            disabled={loading}
            className="text-sm text-gray-600 hover:text-gray-900"
          >
            Clear
          </button>
        </div>

        {/* Status Selector */}
        <div className="flex items-center gap-2 flex-1">
          <label className="text-sm text-gray-700 font-medium">
            Update status:
          </label>
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value as FulfillmentStatus | '')}
            disabled={loading}
            className="px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
          >
            <option value="">Select status...</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="shipped">Shipped</option>
            <option value="delivered">Delivered</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>

        {/* Notes Toggle */}
        <button
          onClick={() => setShowNotesInput(!showNotesInput)}
          disabled={loading}
          className="text-sm text-gray-600 hover:text-gray-900"
        >
          {showNotesInput ? 'Hide notes' : 'Add notes'}
        </button>

        {/* Apply Button */}
        <button
          onClick={handleUpdate}
          disabled={loading || !selectedStatus}
          className="px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0d4a41] disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Updating...' : 'Apply'}
        </button>
      </div>

      {/* Notes Input */}
      {showNotesInput && (
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Admin Notes (optional)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            disabled={loading}
            placeholder="Add notes about this bulk update..."
            rows={2}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
          />
        </div>
      )}
    </div>
  );
}
