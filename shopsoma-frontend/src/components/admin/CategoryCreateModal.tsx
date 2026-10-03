import React, { useState, useEffect } from 'react';
import { X, Loader2, Plus, Layers, Folder, Tag } from 'lucide-react';
import { categoryService } from '../../services/categoryService';
import type { Category } from '../../types';

interface CategoryCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (newCategory: Category) => void;
  defaultLevel?: 'primary' | 'subcategory' | 'child';
  preselectedPrimaryId?: string;
  preselectedSubcategoryId?: string;
}

export default function CategoryCreateModal({
  isOpen,
  onClose,
  onSuccess,
  defaultLevel = 'primary',
  preselectedPrimaryId = '',
  preselectedSubcategoryId = '',
}: CategoryCreateModalProps) {
  const [level, setLevel] = useState<'primary' | 'subcategory' | 'child'>(defaultLevel);
  const [primaryCategories, setPrimaryCategories] = useState<Category[]>([]);
  const [subcategories, setSubcategories] = useState<Category[]>([]);

  const [selectedPrimaryId, setSelectedPrimaryId] = useState(preselectedPrimaryId);
  const [selectedSubcategoryId, setSelectedSubcategoryId] = useState(preselectedSubcategoryId);

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [displayOrder, setDisplayOrder] = useState<number>(0);
  const [isActive, setIsActive] = useState(true);

  const [loadingParents, setLoadingParents] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Sync default level when opened
  useEffect(() => {
    if (isOpen) {
      setLevel(defaultLevel);
      setSelectedPrimaryId(preselectedPrimaryId);
      setSelectedSubcategoryId(preselectedSubcategoryId);
      setName('');
      setSlug('');
      setDescription('');
      setDisplayOrder(0);
      setIsActive(true);
      setErrorMessage(null);
    }
  }, [isOpen, defaultLevel, preselectedPrimaryId, preselectedSubcategoryId]);

  // Load primary categories from DB when modal opens or when level needs them
  useEffect(() => {
    if (!isOpen) return;

    let isMounted = true;
    const fetchRoots = async () => {
      try {
        setLoadingParents(true);
        const data = await categoryService.getPrimaryCategories();
        if (isMounted) {
          // Filter out internal editorial shop-edits
          const valid = (data || []).filter(
            (c) => c.slug !== 'shop-edits' && !c.slug.startsWith('shop-edits-')
          );
          setPrimaryCategories(valid);
        }
      } catch (err) {
        console.error('Failed to load primary categories', err);
      } finally {
        if (isMounted) setLoadingParents(false);
      }
    };

    fetchRoots();
    return () => {
      isMounted = false;
    };
  }, [isOpen]);

  // Load subcategories when selectedPrimaryId changes and level is 'child'
  useEffect(() => {
    if (!isOpen || !selectedPrimaryId || level !== 'child') {
      if (level !== 'child') setSubcategories([]);
      return;
    }

    let isMounted = true;
    const fetchSubs = async () => {
      try {
        setLoadingParents(true);
        const data = await categoryService.getSubcategories(selectedPrimaryId);
        if (isMounted) {
          setSubcategories(data || []);
        }
      } catch (err) {
        console.error('Failed to load subcategories', err);
      } finally {
        if (isMounted) setLoadingParents(false);
      }
    };

    fetchSubs();
    return () => {
      isMounted = false;
    };
  }, [isOpen, selectedPrimaryId, level]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setErrorMessage('Category name is required.');
      return;
    }

    let parentId: string | null = null;
    if (level === 'subcategory') {
      if (!selectedPrimaryId) {
        setErrorMessage('Please select a Primary Category.');
        return;
      }
      parentId = selectedPrimaryId;
    } else if (level === 'child') {
      if (!selectedPrimaryId) {
        setErrorMessage('Please select a Primary Category.');
        return;
      }
      if (!selectedSubcategoryId) {
        setErrorMessage('Please select a Subcategory.');
        return;
      }
      parentId = selectedSubcategoryId;
    }

    try {
      setSubmitting(true);
      const created = await categoryService.createCategory({
        name: trimmedName,
        parent_id: parentId,
        slug: slug.trim() || undefined,
        description: description.trim() || undefined,
        display_order: displayOrder,
        is_active: isActive,
      });

      onSuccess(created);
      onClose();
    } catch (err: any) {
      console.error('Failed to create category:', err);
      const msg = err.response?.data?.detail || err.message || 'Failed to create category.';
      setErrorMessage(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl border border-gray-100 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 bg-gray-50/50">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-[#105E53]/10 text-[#105E53]">
              <Plus className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">
                {level === 'primary' && 'Add Primary Category'}
                {level === 'subcategory' && 'Add Subcategory'}
                {level === 'child' && 'Add Child Category'}
              </h2>
              <p className="text-xs text-gray-500">
                Data will be persisted to the database and immediately available
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
          {errorMessage && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
              {errorMessage}
            </div>
          )}

          {/* Level Switcher */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wider text-gray-500 mb-2">
              Category Level
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => {
                  setLevel('primary');
                  setErrorMessage(null);
                }}
                className={`py-2 px-3 text-xs font-medium rounded-lg border text-center transition flex flex-col items-center gap-1 ${
                  level === 'primary'
                    ? 'border-[#105E53] bg-[#105E53]/5 text-[#105E53] font-semibold'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Layers className="w-4 h-4" />
                Primary
              </button>
              <button
                type="button"
                onClick={() => {
                  setLevel('subcategory');
                  setErrorMessage(null);
                }}
                className={`py-2 px-3 text-xs font-medium rounded-lg border text-center transition flex flex-col items-center gap-1 ${
                  level === 'subcategory'
                    ? 'border-[#105E53] bg-[#105E53]/5 text-[#105E53] font-semibold'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Folder className="w-4 h-4" />
                Subcategory
              </button>
              <button
                type="button"
                onClick={() => {
                  setLevel('child');
                  setErrorMessage(null);
                }}
                className={`py-2 px-3 text-xs font-medium rounded-lg border text-center transition flex flex-col items-center gap-1 ${
                  level === 'child'
                    ? 'border-[#105E53] bg-[#105E53]/5 text-[#105E53] font-semibold'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Tag className="w-4 h-4" />
                Child Category
              </button>
            </div>
          </div>

          {/* If Subcategory or Child: Select Primary Category */}
          {(level === 'subcategory' || level === 'child') && (
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Parent Primary Category *
              </label>
              <select
                value={selectedPrimaryId}
                onChange={(e) => {
                  setSelectedPrimaryId(e.target.value);
                  setSelectedSubcategoryId('');
                }}
                disabled={loadingParents}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
                required
              >
                <option value="">Select a Primary Category</option>
                {primaryCategories.map((cat) => (
                  <option key={cat.id} value={cat.id}>
                    {cat.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* If Child: Select Subcategory */}
          {level === 'child' && (
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Parent Subcategory *
              </label>
              <select
                value={selectedSubcategoryId}
                onChange={(e) => setSelectedSubcategoryId(e.target.value)}
                disabled={!selectedPrimaryId || loadingParents}
                className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53] disabled:bg-gray-100 disabled:text-gray-400"
                required
              >
                <option value="">
                  {!selectedPrimaryId
                    ? 'Select Primary Category first'
                    : subcategories.length === 0
                    ? 'No subcategories available'
                    : 'Select a Subcategory'}
                </option>
                {subcategories.map((sub) => (
                  <option key={sub.id} value={sub.id}>
                    {sub.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Category Name *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={
                level === 'primary'
                  ? 'e.g., Kids, Beauty, Home & Living'
                  : level === 'subcategory'
                  ? 'e.g., Tops, Dresses, Activewear'
                  : 'e.g., T-Shirts, Shirts, Jeans'
              }
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
              required
            />
          </div>

          {/* Slug (Optional) */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Slug <span className="text-gray-400 font-normal">(optional, auto-generated from name if blank)</span>
            </label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              placeholder="e.g., kids-tops"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1">
              Description <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              placeholder="Brief description of this category..."
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Display Order */}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Display Order
              </label>
              <input
                type="number"
                min="0"
                value={displayOrder}
                onChange={(e) => setDisplayOrder(parseInt(e.target.value) || 0)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
              />
            </div>

            {/* Is Active */}
            <div className="flex items-center gap-2 pt-6">
              <input
                type="checkbox"
                id="is_active_checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
              />
              <label htmlFor="is_active_checkbox" className="text-sm font-medium text-gray-700 cursor-pointer">
                Active Category
              </label>
            </div>
          </div>

          {/* Buttons */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !name.trim()}
              className="rounded-lg bg-[#105E53] px-5 py-2 text-sm font-medium text-white hover:bg-[#0d4a42] transition disabled:opacity-50 flex items-center gap-2 shadow-sm"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving...
                </>
              ) : (
                'Create Category'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
