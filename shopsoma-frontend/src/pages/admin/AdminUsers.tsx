import { useState, useEffect } from 'react';
import { Search, Trash2, Power, PowerOff, AlertCircle, CheckCircle, Users, Mail, CheckCircle as VerifiedIcon, Key } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { adminService, type UserListItem } from '../../services/adminService';
import { useAuth } from '../../context/AuthContext';

export default function AdminUsers() {
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [roleFilter, setRoleFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<UserListItem | null>(null);
  const [newPassword, setNewPassword] = useState('');

  const { user } = useAuth();

  const pageSize = 20;

  useEffect(() => {
    loadUsers();
  }, [page, roleFilter, statusFilter, search]);

  const loadUsers = async () => {
    try {
      setLoading(true);

      const filters: any = {
        page,
        page_size: pageSize,
        search: search || undefined,
      };

      if (roleFilter !== 'all') filters.role = roleFilter;
      if (statusFilter !== 'all') filters.is_active = statusFilter === 'active';

      const response = await adminService.listUsers(filters);
      setUsers(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (err: any) {
      showMessage('error', err.message || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleStatus = async (userId: string, currentStatus: boolean) => {
    try {
      setActionLoading(userId);
      await adminService.toggleUserStatus(userId, !currentStatus);
      showMessage('success', `User ${!currentStatus ? 'activated' : 'deactivated'} successfully`);
      loadUsers();
    } catch (err: any) {
      showMessage('error', err.message || 'Failed to toggle user status');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    try {
      setActionLoading(userId);
      await adminService.deleteUser(userId);
      showMessage('success', 'User deleted successfully');
      setDeleteConfirm(null);
      loadUsers();
    } catch (err: any) {
      showMessage('error', err.message || 'Failed to delete user');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResetPassword = async () => {
    if (!resetPasswordUser || !newPassword) return;

    if (newPassword.length < 8) {
      showMessage('error', 'Password must be at least 8 characters');
      return;
    }

    try {
      setActionLoading(resetPasswordUser.id);
      await adminService.resetUserPassword(resetPasswordUser.id, newPassword);
      showMessage('success', `Password reset successfully for ${resetPasswordUser.email}`);
      setResetPasswordUser(null);
      setNewPassword('');
    } catch (err: any) {
      showMessage('error', err?.response?.data?.detail || err.message || 'Failed to reset password');
    } finally {
      setActionLoading(null);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getRoleBadge = (role: string) => {
    switch (role) {
      case 'admin':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
            Admin
          </span>
        );
      case 'vendor':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            Vendor
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
            Customer
          </span>
        );
    }
  };

  return (
    <div className="min-h-screen bg-[#F9FAFB] flex">
      <AdminSidebar activeSection="users" />

      <main className="flex-1 p-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-display text-gray-900 mb-2">User Management</h1>
          <p className="text-gray-600 font-ui">Manage user accounts and permissions</p>
        </div>

        {/* Message */}
        {message && (
          <div
            className={`rounded-xl p-4 flex items-center gap-3 ${
              message.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-800'
                : 'bg-red-50 border border-red-200 text-red-800'
            }`}
          >
            {message.type === 'success' ? (
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
            ) : (
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
            )}
            <p className="text-sm font-medium">{message.text}</p>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Total Users</p>
                <p className="text-2xl font-display text-gray-900 mt-1">{total}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-[#105E53]/10 flex items-center justify-center">
                <Users className="w-6 h-6 text-[#105E53]" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Active Users</p>
                <p className="text-2xl font-display text-gray-900 mt-1">
                  {users.filter((u) => u.is_active).length}
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-green-100 flex items-center justify-center">
                <CheckCircle className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Verified Emails</p>
                <p className="text-2xl font-display text-gray-900 mt-1">
                  {users.filter((u) => u.email_verified).length}
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-blue-100 flex items-center justify-center">
                <VerifiedIcon className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Vendors</p>
                <p className="text-2xl font-display text-gray-900 mt-1">
                  {users.filter((u) => u.role === 'vendor').length}
                </p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-purple-100 flex items-center justify-center">
                <Mail className="w-6 h-6 text-purple-600" />
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by name or email..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui"
              />
            </div>

            {/* Role Filter */}
            <select
              value={roleFilter}
              onChange={(e) => {
                setRoleFilter(e.target.value);
                setPage(1);
              }}
              className="px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui bg-gray-50"
            >
              <option value="all">All Roles</option>
              <option value="customer">Customer</option>
              <option value="vendor">Vendor</option>
              <option value="admin">Admin</option>
            </select>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui bg-gray-50"
            >
              <option value="all">All Status</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-gray-600 font-ui">
            Showing {users.length} of {total} users
          </div>
        </div>

        {/* Users table */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-12 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#105E53] mx-auto"></div>
              <p className="mt-4 text-gray-600 font-ui">Loading users...</p>
            </div>
          ) : users.length === 0 ? (
            <div className="p-12 text-center">
              <Users className="w-16 h-16 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-600 font-ui">No users found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      User
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Role
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Verified
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Joined
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Last Login
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {users.map((u) => (
                    <tr key={u.id} className="hover:bg-gray-50 transition">
                      <td className="px-6 py-4">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">{u.full_name}</p>
                          <p className="text-xs text-gray-500">{u.email}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4">{getRoleBadge(u.role)}</td>
                      <td className="px-6 py-4">
                        {u.is_active ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-700">
                            <CheckCircle className="w-3 h-3" />
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-700">
                            Inactive
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span className="text-sm text-gray-900">
                          {u.email_verified ? (
                            <CheckCircle className="w-4 h-4 text-green-600" />
                          ) : (
                            <span className="text-gray-400">✗</span>
                          )}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-600">{formatDate(u.created_at)}</td>
                      <td className="px-6 py-4 text-sm text-gray-600">{formatDate(u.last_login)}</td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          {/* Reset Password Button */}
                          <button
                            onClick={() => setResetPasswordUser(u)}
                            disabled={u.id === user?.id || actionLoading === u.id}
                            className="p-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                            title={u.id === user?.id ? 'Cannot reset your own password' : 'Reset user password'}
                          >
                            <Key className="w-4 h-4" />
                          </button>

                          {/* Toggle Status Button */}
                          <button
                            onClick={() => handleToggleStatus(u.id, u.is_active)}
                            disabled={u.id === user?.id || actionLoading === u.id}
                            className={`p-2 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed ${
                              u.is_active
                                ? 'text-orange-600 hover:text-orange-700 hover:bg-orange-50'
                                : 'text-green-600 hover:text-green-700 hover:bg-green-50'
                            }`}
                            title={
                              u.id === user?.id
                                ? 'Cannot modify your own status'
                                : u.is_active
                                ? 'Deactivate user'
                                : 'Activate user'
                            }
                          >
                            {u.is_active ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />}
                          </button>

                          {/* Delete Button */}
                          {deleteConfirm === u.id ? (
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleDeleteUser(u.id)}
                                disabled={actionLoading === u.id}
                                className="px-3 py-1.5 text-xs font-semibold bg-red-600 text-white rounded-lg hover:bg-red-700 transition disabled:opacity-50"
                              >
                                Confirm
                              </button>
                              <button
                                onClick={() => setDeleteConfirm(null)}
                                className="px-3 py-1.5 text-xs font-semibold border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition"
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              onClick={() => setDeleteConfirm(u.id)}
                              disabled={u.id === user?.id}
                              className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
                              title={u.id === user?.id ? 'Cannot delete your own account' : 'Delete user'}
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Previous
            </button>
            <span className="px-4 py-2 text-sm text-gray-600 font-ui">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="px-4 py-2 border border-gray-200 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              Next
            </button>
          </div>
        )}
      </main>

      {/* Password Reset Modal */}
      {resetPasswordUser && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
            <h3 className="text-xl font-display text-gray-900 mb-2">Reset Password</h3>
            <p className="text-sm text-gray-600 mb-4">
              Set a new password for <span className="font-semibold">{resetPasswordUser.email}</span>
            </p>

            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter new password (min 8 characters)"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
                autoFocus
              />
              <p className="text-xs text-gray-500 mt-1">Minimum 8 characters required</p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={handleResetPassword}
                disabled={!newPassword || newPassword.length < 8 || actionLoading === resetPasswordUser.id}
                className="flex-1 px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0c4c45] transition disabled:opacity-50 disabled:cursor-not-allowed font-medium"
              >
                {actionLoading === resetPasswordUser.id ? 'Resetting...' : 'Reset Password'}
              </button>
              <button
                onClick={() => {
                  setResetPasswordUser(null);
                  setNewPassword('');
                }}
                disabled={actionLoading === resetPasswordUser.id}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 font-medium"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
