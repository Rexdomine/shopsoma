import { useState, useEffect, useMemo } from 'react';
import {
  Layers,
  Folder,
  Tag,
  Plus,
  Search,
  Edit2,
  Trash2,
  CheckCircle,
  XCircle,
  Loader2,
  ChevronRight,
  AlertCircle,
} from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import CategoryCreateModal from '../../components/admin/CategoryCreateModal';
import { categoryService } from '../../services/categoryService';
import type { Category } from '../../types';
import { useToast } from '../../hooks/useToast';
import ToastContainer from '../../components/ui/ToastContainer';

export default function AdminCategories() {
  const { toasts, hideToast, success, error } = useToast();

  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selectedLevel, setSelectedLevel] = useState<'all' | 'primary' | 'subcategory' | 'child'>('all');
  const [selectedParentFilter, setSelectedParentFilter] = useState<string>('all');

  // Create Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createModalLevel, setCreateModalLevel] = useState<'primary' | 'subcategory' | 'child'>('primary');
  const [createModalPrimaryId, setCreateModalPrimaryId] = useState<string>('');
  const [createModalSubId, setCreateModalSubId] = useState<string>('');

  // Edit Modal state
  const [editingCategory, setEditingCategory] = useState<Category | null>(null);
  const [editName, setEditName] = useState('');
  const [editSlug, setEditSlug] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [editDisplayOrder, setEditDisplayOrder] = useState<number>(0);
  const [editIsActive, setEditIsActive] = useState<boolean>(true);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete confirmation state
  const [deletingCategory, setDeletingCategory] = useState<Category | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Load all categories from API
  const loadCategories = async () => {
    try {
      setLoading(true);
      const data = await categoryService.getAdminCategories();
      setCategories(Array.isArray(data) ? data : []);
    } catch (err: any) {
      console.error('Failed to load admin categories:', err);
      error('Failed to load categories. Please try refreshing.', 'Error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCategories();
  }, []);

  // Compute counts
  const stats = useMemo(() => {
    const total = categories.length;
    const primary = categories.filter((c) => c.level === 'primary' || !c.parent_id).length;
    const sub = categories.filter((c) => c.level === 'subcategory').length;
    const child = categories.filter((c) => c.level === 'child').length;
    return { total, primary, sub, child };
  }, [categories]);

  // Primary categories for filtering and mapping
  const primaryCategoriesList = useMemo(
    () => categories.filter((c) => c.level === 'primary' || !c.parent_id),
    [categories]
  );

  // Filtered categories
  const filteredCategories = useMemo(() => {
    return categories.filter((cat) => {
      // Level filter
      if (selectedLevel === 'primary' && (cat.level !== 'primary' && cat.parent_id)) return false;
      if (selectedLevel === 'subcategory' && cat.level !== 'subcategory') return false;
      if (selectedLevel === 'child' && cat.level !== 'child') return false;

      // Parent filter
      if (selectedParentFilter !== 'all' && cat.parent_id !== selectedParentFilter) {
        return false;
      }

      // Search filter
      if (search.trim()) {
        const query = search.toLowerCase();
        const matchesName = cat.name.toLowerCase().includes(query);
        const matchesSlug = cat.slug.toLowerCase().includes(query);
        const matchesParent = cat.parent_name?.toLowerCase().includes(query);
        return matchesName || matchesSlug || matchesParent;
      }

      return true;
    });
  }, [categories, selectedLevel, selectedParentFilter, search]);

  // Open create modal with prefilled hierarchy
  const handleOpenAddPrimary = () => {
    setCreateModalLevel('primary');
    setCreateModalPrimaryId('');
    setCreateModalSubId('');
    setShowCreateModal(true);
  };

  const handleOpenAddSubcategory = (primaryId?: string) => {
    setCreateModalLevel('subcategory');
    setCreateModalPrimaryId(primaryId || '');
    setCreateModalSubId('');
    setShowCreateModal(true);
  };

  const handleOpenAddChild = (primaryId?: string, subId?: string) => {
    setCreateModalLevel('child');
    setCreateModalPrimaryId(primaryId || '');
    setCreateModalSubId(subId || '');
    setShowCreateModal(true);
  };

  const handleCategoryCreated = (newCat: Category) => {
    success(`Category "${newCat.name}" added successfully!`, 'Success');
    loadCategories();
  };

  // Open edit modal
  const handleOpenEdit = (category: Category) => {
    setEditingCategory(category);
    setEditName(category.name);
    setEditSlug(category.slug);
    setEditDescription(category.description || '');
    setEditDisplayOrder(category.display_order || 0);
    setEditIsActive(category.is_active);
    setEditError(null);
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingCategory) return;

    const trimmed = editName.trim();
    if (!trimmed) {
      setEditError('Category name is required.');
      return;
    }

    try {
      setSavingEdit(true);
      setEditError(null);
      await categoryService.updateCategory(editingCategory.id, {
        name: trimmed,
        slug: editSlug.trim() || undefined,
        description: editDescription.trim() || undefined,
        display_order: editDisplayOrder,
        is_active: editIsActive,
      });

      success(`Category "${trimmed}" updated!`, 'Success');
      setEditingCategory(null);
      loadCategories();
    } catch (err: any) {
      console.error('Failed to update category:', err);
      const msg = err.response?.data?.detail || err.message || 'Failed to update category.';
      setEditError(typeof msg === 'string' ? msg : JSON.stringify(msg));
    } finally {
      setSavingEdit(false);
    }
  };

  // Delete category
  const handleDeleteCategory = async () => {
    if (!deletingCategory) return;

    try {
      setDeleting(true);
      await categoryService.deleteCategory(deletingCategory.id);
      success(`Category "${deletingCategory.name}" deleted.`, 'Success');
      setDeletingCategory(null);
      loadCategories();
    } catch (err: any) {
      console.error('Failed to delete category:', err);
      const msg = err.response?.data?.detail || err.message || 'Failed to delete category.';
      error(typeof msg === 'string' ? msg : JSON.stringify(msg), 'Cannot Delete');
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-gray-50">
      <AdminSidebar activeSection="categories" />
      <ToastContainer toasts={toasts} onClose={hideToast} />

      <main className="flex-1 p-6 lg:p-8 max-w-7xl mx-auto w-full">
        {/* Top Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 tracking-tight">
              Category Management
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Create, organize, and manage 3-level categories (Primary, Subcategory, Child Category) stored in the database.
            </p>
          </div>

          {/* Quick Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleOpenAddPrimary}
              className="inline-flex items-center gap-2 rounded-lg bg-[#105E53] px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-[#0d4a42] transition"
            >
              <Plus className="w-4 h-4" />
              Add Primary Category
            </button>
            <button
              onClick={() => handleOpenAddSubcategory()}
              className="inline-flex items-center gap-2 rounded-lg border border-[#105E53] bg-white px-4 py-2 text-sm font-medium text-[#105E53] shadow-sm hover:bg-[#105E53]/5 transition"
            >
              <Plus className="w-4 h-4" />
              Add Subcategory
            </button>
            <button
              onClick={() => handleOpenAddChild()}
              className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 transition"
            >
              <Plus className="w-4 h-4" />
              Add Child Category
            </button>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                Total Categories
              </span>
              <Layers className="w-5 h-5 text-gray-400" />
            </div>
            <div className="mt-2 text-2xl font-bold text-gray-900">{stats.total}</div>
            <p className="text-xs text-gray-400 mt-1">In active database</p>
          </div>

          <div className="rounded-xl border border-blue-100 bg-blue-50/40 p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-blue-700 uppercase tracking-wider">
                Primary Categories
              </span>
              <Layers className="w-5 h-5 text-blue-600" />
            </div>
            <div className="mt-2 text-2xl font-bold text-blue-900">{stats.primary}</div>
            <p className="text-xs text-blue-600/80 mt-1">Level 1 (Men, Women, etc.)</p>
          </div>

          <div className="rounded-xl border border-purple-100 bg-purple-50/40 p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-purple-700 uppercase tracking-wider">
                Subcategories
              </span>
              <Folder className="w-5 h-5 text-purple-600" />
            </div>
            <div className="mt-2 text-2xl font-bold text-purple-900">{stats.sub}</div>
            <p className="text-xs text-purple-600/80 mt-1">Level 2 (Tops, Bottoms, etc.)</p>
          </div>

          <div className="rounded-xl border border-amber-100 bg-amber-50/40 p-4 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-amber-700 uppercase tracking-wider">
                Child Categories
              </span>
              <Tag className="w-5 h-5 text-amber-600" />
            </div>
            <div className="mt-2 text-2xl font-bold text-amber-900">{stats.child}</div>
            <p className="text-xs text-amber-600/80 mt-1">Level 3 (T-Shirts, Jeans, etc.)</p>
          </div>
        </div>

        {/* Filters and Search Bar */}
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm mb-6 space-y-4">
          <div className="flex flex-col md:flex-row gap-4 justify-between items-stretch md:items-center">
            {/* Search Input */}
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search categories by name, slug, or parent..."
                className="w-full rounded-lg border border-gray-200 pl-9 pr-4 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
              />
            </div>

            {/* Level Filter Tabs */}
            <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
              {(['all', 'primary', 'subcategory', 'child'] as const).map((lvl) => (
                <button
                  key={lvl}
                  type="button"
                  onClick={() => {
                    setSelectedLevel(lvl);
                    setSelectedParentFilter('all');
                  }}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition ${
                    selectedLevel === lvl
                      ? 'bg-white text-gray-900 shadow-sm font-semibold'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {lvl === 'all' && 'All'}
                  {lvl === 'primary' && 'Primary'}
                  {lvl === 'subcategory' && 'Subcategories'}
                  {lvl === 'child' && 'Child Categories'}
                </button>
              ))}
            </div>

            {/* Parent Primary Filter */}
            {selectedLevel !== 'primary' && (
              <div className="w-full md:w-56">
                <select
                  value={selectedParentFilter}
                  onChange={(e) => setSelectedParentFilter(e.target.value)}
                  className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700 focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
                >
                  <option value="all">Filter by Primary Parent: All</option>
                  {primaryCategoriesList.map((pc) => (
                    <option key={pc.id} value={pc.id}>
                      {pc.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        </div>

        {/* Table / List */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="py-20 flex flex-col items-center justify-center text-gray-400 gap-3">
              <Loader2 className="w-8 h-8 animate-spin text-[#105E53]" />
              <p className="text-sm">Loading database categories...</p>
            </div>
          ) : filteredCategories.length === 0 ? (
            <div className="py-20 flex flex-col items-center justify-center text-center p-6 text-gray-500">
              <AlertCircle className="w-12 h-12 text-gray-300 mb-3" />
              <p className="text-base font-semibold text-gray-800">No categories found</p>
              <p className="text-sm text-gray-500 mt-1 max-w-md">
                {search
                  ? `No categories matching "${search}". Try adjusting your filters.`
                  : 'No categories exist for the selected filter.'}
              </p>
              <div className="mt-4 flex gap-2">
                <button
                  onClick={handleOpenAddPrimary}
                  className="rounded-lg bg-[#105E53] px-4 py-2 text-xs font-medium text-white hover:bg-[#0d4a42] transition"
                >
                  + Add Primary Category
                </button>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-600">
                <thead className="bg-gray-50 text-xs font-semibold uppercase tracking-wider text-gray-500 border-b border-gray-200">
                  <tr>
                    <th scope="col" className="px-6 py-3.5">
                      Category Name & Slug
                    </th>
                    <th scope="col" className="px-6 py-3.5">
                      Level
                    </th>
                    <th scope="col" className="px-6 py-3.5">
                      Parent Category
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-center">
                      Order
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-center">
                      Status
                    </th>
                    <th scope="col" className="px-6 py-3.5 text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredCategories.map((cat) => {
                    const level = cat.level || (cat.parent_id ? 'subcategory' : 'primary');
                    return (
                      <tr key={cat.id} className="hover:bg-gray-50/75 transition">
                        <td className="px-6 py-4 font-medium text-gray-900">
                          <div className="flex items-center gap-2">
                            {level === 'primary' && <Layers className="w-4 h-4 text-blue-500 shrink-0" />}
                            {level === 'subcategory' && <Folder className="w-4 h-4 text-purple-500 shrink-0" />}
                            {level === 'child' && <Tag className="w-4 h-4 text-amber-500 shrink-0" />}
                            <div>
                              <div className="text-sm font-semibold text-gray-900">{cat.name}</div>
                              <div className="text-xs font-mono text-gray-400">/{cat.slug}</div>
                            </div>
                          </div>
                        </td>

                        <td className="px-6 py-4">
                          {level === 'primary' && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                              Primary
                            </span>
                          )}
                          {level === 'subcategory' && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                              Subcategory
                            </span>
                          )}
                          {level === 'child' && (
                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                              Child Category
                            </span>
                          )}
                        </td>

                        <td className="px-6 py-4">
                          {cat.parent_name ? (
                            <span className="inline-flex items-center gap-1 text-xs text-gray-600 bg-gray-100 px-2 py-1 rounded-md">
                              <ChevronRight className="w-3 h-3 text-gray-400" />
                              {cat.parent_name}
                            </span>
                          ) : (
                            <span className="text-xs text-gray-400 italic">None (Root)</span>
                          )}
                        </td>

                        <td className="px-6 py-4 text-center text-xs font-medium text-gray-600">
                          {cat.display_order}
                        </td>

                        <td className="px-6 py-4 text-center">
                          {cat.is_active ? (
                            <span className="inline-flex items-center gap-1 text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                              <CheckCircle className="w-3 h-3 text-emerald-600" />
                              Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full border border-gray-200">
                              <XCircle className="w-3 h-3 text-gray-400" />
                              Inactive
                            </span>
                          )}
                        </td>

                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {/* Fast-add child/sub button */}
                            {level === 'primary' && (
                              <button
                                onClick={() => handleOpenAddSubcategory(cat.id)}
                                title="Add Subcategory under this"
                                className="px-2 py-1 text-xs font-medium text-purple-700 hover:bg-purple-50 rounded border border-purple-200 transition"
                              >
                                + Sub
                              </button>
                            )}
                            {level === 'subcategory' && (
                              <button
                                onClick={() => handleOpenAddChild(cat.parent_id || undefined, cat.id)}
                                title="Add Child category under this"
                                className="px-2 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50 rounded border border-amber-200 transition"
                              >
                                + Child
                              </button>
                            )}

                            {/* Edit */}
                            <button
                              onClick={() => handleOpenEdit(cat)}
                              title="Edit Category"
                              className="p-1.5 text-gray-500 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition"
                            >
                              <Edit2 className="w-4 h-4" />
                            </button>

                            {/* Delete */}
                            <button
                              onClick={() => setDeletingCategory(cat)}
                              title="Delete Category"
                              className="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 rounded-lg transition"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>

      {/* Category Creation Modal */}
      <CategoryCreateModal
        isOpen={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onSuccess={handleCategoryCreated}
        defaultLevel={createModalLevel}
        preselectedPrimaryId={createModalPrimaryId}
        preselectedSubcategoryId={createModalSubId}
      />

      {/* Edit Category Modal */}
      {editingCategory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="relative w-full max-w-lg rounded-2xl bg-white shadow-2xl border border-gray-100 overflow-hidden">
            <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4 bg-gray-50/50">
              <h2 className="text-lg font-semibold text-gray-900">
                Edit Category: {editingCategory.name}
              </h2>
              <button
                onClick={() => setEditingCategory(null)}
                className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 transition"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="p-6 space-y-4">
              {editError && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                  {editError}
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Category Name *
                </label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Slug
                </label>
                <input
                  type="text"
                  value={editSlug}
                  onChange={(e) => setEditSlug(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Description
                </label>
                <textarea
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  rows={2}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-medium text-gray-700 mb-1">
                    Display Order
                  </label>
                  <input
                    type="number"
                    min="0"
                    value={editDisplayOrder}
                    onChange={(e) => setEditDisplayOrder(parseInt(e.target.value) || 0)}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]"
                  />
                </div>

                <div className="flex items-center gap-2 pt-6">
                  <input
                    type="checkbox"
                    id="edit_is_active_checkbox"
                    checked={editIsActive}
                    onChange={(e) => setEditIsActive(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                  />
                  <label htmlFor="edit_is_active_checkbox" className="text-sm font-medium text-gray-700 cursor-pointer">
                    Active
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setEditingCategory(null)}
                  disabled={savingEdit}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="rounded-lg bg-[#105E53] px-5 py-2 text-sm font-medium text-white hover:bg-[#0d4a42] transition disabled:opacity-50 flex items-center gap-2"
                >
                  {savingEdit ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    'Save Changes'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deletingCategory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="relative w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-gray-100">
            <h3 className="text-lg font-bold text-gray-900">Delete Category</h3>
            <p className="text-sm text-gray-600 mt-2">
              Are you sure you want to delete <strong className="text-gray-900 font-semibold">{deletingCategory.name}</strong>?
            </p>
            <p className="text-xs text-red-600 mt-2 bg-red-50 p-3 rounded-lg border border-red-200">
              Note: If this category contains subcategories or child categories, they will also be removed. Deletion will be rejected if any products are assigned to this category.
            </p>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setDeletingCategory(null)}
                disabled={deleting}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteCategory}
                disabled={deleting}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition disabled:opacity-50 flex items-center gap-2"
              >
                {deleting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  'Delete Category'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
