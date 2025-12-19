import { useState } from 'react';
import { X } from 'lucide-react';
import { collectionService } from '../../services/collectionService';
import type { Collection } from '../../types';

interface CollectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCollectionCreated: (collection: Collection) => void;
}

export default function CollectionModal({ isOpen, onClose, onCollectionCreated }: CollectionModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError('Collection name is required');
      return;
    }

    try {
      setIsSubmitting(true);
      setError('');

      const newCollection = await collectionService.createCollection({
        name: name.trim(),
        description: description.trim() || undefined,
      });

      // Reset form
      setName('');
      setDescription('');

      // Notify parent component
      onCollectionCreated(newCollection);

      // Close modal
      onClose();
    } catch (err: any) {
      console.error('Error creating collection:', err);
      setError(err.response?.data?.detail || 'Failed to create collection. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    if (!isSubmitting) {
      setName('');
      setDescription('');
      setError('');
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl p-6 m-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-semibold text-gray-900">Create New Collection</h2>
          <button
            type="button"
            onClick={handleClose}
            disabled={isSubmitting}
            className="p-2 hover:bg-gray-100 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Error Message */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Collection Name */}
          <div>
            <label htmlFor="collection-name" className="block text-sm font-medium text-gray-700 mb-2">
              Collection Name <span className="text-red-500">*</span>
            </label>
            <input
              id="collection-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g., Summer 2024, New Arrivals"
              disabled={isSubmitting}
              className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed transition"
              maxLength={100}
              required
            />
            <p className="mt-1.5 text-xs text-gray-500">
              Give your collection a memorable name
            </p>
          </div>

          {/* Description (Optional) */}
          <div>
            <label htmlFor="collection-description" className="block text-sm font-medium text-gray-700 mb-2">
              Description <span className="text-gray-400 text-xs">(Optional)</span>
            </label>
            <textarea
              id="collection-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe your collection..."
              disabled={isSubmitting}
              rows={3}
              className="w-full rounded-lg border border-gray-300 bg-white px-4 py-3 text-sm focus:outline-none focus:border-[#105E53] focus:ring-2 focus:ring-[#105E53]/20 disabled:opacity-50 disabled:cursor-not-allowed transition resize-none"
            />
            <p className="mt-1.5 text-xs text-gray-500">
              Add details about this collection
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || !name.trim()}
              className="flex-1 px-4 py-2.5 bg-[#105E53] text-white rounded-lg text-sm font-medium hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Creating...
                </>
              ) : (
                'Create Collection'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
