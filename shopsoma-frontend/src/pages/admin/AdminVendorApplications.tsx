import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Check, X, Eye, AlertCircle, CheckCircle, Clock, FileText, Mail } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { adminService, type VendorApplication } from '../../services/adminService';

export default function AdminVendorApplications() {
  const navigate = useNavigate();
  const [applications, setApplications] = useState<VendorApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('pending_review');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const pageSize = 20;

  useEffect(() => {
    loadApplications();
  }, [page, statusFilter, search]);

  const loadApplications = async () => {
    try {
      setLoading(true);
      const response = await adminService.listVendorApplications({
        page,
        page_size: pageSize,
        status: statusFilter,
        search: search || undefined,
      });

      setApplications(response.items);
      setTotal(response.total);
      setTotalPages(response.total_pages);
    } catch (error: any) {
      console.error('Failed to load applications:', error);
      showMessage('error', 'Failed to load applications');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async (applicationId: string) => {
    if (!confirm('Are you sure you want to approve this vendor application? This will create a vendor account and send activation instructions.')) {
      return;
    }

    try {
      setActionLoading(applicationId);
      await adminService.approveVendorApplication(applicationId, 'Application approved by admin');
      showMessage('success', 'Application approved successfully! Vendor will receive activation email.');
      loadApplications();
    } catch (error: any) {
      console.error('Failed to approve application:', error);
      showMessage('error', error?.message || 'Failed to approve application');
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async (applicationId: string) => {
    const reason = prompt('Please provide a reason for rejection (optional):');
    if (reason === null) return; // User canceled

    try {
      setActionLoading(applicationId);
      await adminService.rejectVendorApplication(applicationId, reason || 'Application rejected by admin');
      showMessage('success', 'Application rejected successfully');
      loadApplications();
    } catch (error: any) {
      console.error('Failed to reject application:', error);
      showMessage('error', error?.message || 'Failed to reject application');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResendActivation = async (application: VendorApplication) => {
    if (!confirm(`Resend activation email to ${application.email}?`)) {
      return;
    }

    try {
      setActionLoading(application.id);
      const response = await adminService.resendVendorActivation(application.id);
      const setupSuffix = response.account_already_setup
        ? ' This account is already set up, so the invite link will direct them to reset password/contact admin guidance.'
        : '';
      showMessage('success', `Activation email sent to ${response.email}.${setupSuffix}`);
      loadApplications();
    } catch (error: any) {
      console.error('Failed to resend activation email:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to resend activation email';
      showMessage('error', errorMessage);
    } finally {
      setActionLoading(null);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const canResendActivation = (app: VendorApplication) => {
    return app.status === 'approved';
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending_review':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
            <Clock className="w-3 h-3" />
            Pending Review
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircle className="w-3 h-3" />
            Approved
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
            <AlertCircle className="w-3 h-3" />
            Rejected
          </span>
        );
      default:
        return <span className="text-gray-500 text-xs">{status}</span>;
    }
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex">
      <AdminSidebar activeSection="vendor-applications" />

      <main className="flex-1 p-8 space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-3xl font-display text-gray-900 mb-2">Vendor Applications</h1>
          <p className="text-gray-600 font-ui">Review and approve vendor applications from /vendor/signup</p>
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

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by name, email, or business..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="w-full pl-10 pr-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui"
              />
            </div>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              className="px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent font-ui bg-gray-50"
            >
              <option value="pending_review">Pending Review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>

          {/* Results count */}
          <div className="text-sm text-gray-600 font-ui">
            Showing {applications.length} of {total} applications
          </div>
        </div>

        {/* Applications list */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {loading ? (
            <div className="p-12 text-center">
              <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#105E53] mx-auto"></div>
              <p className="mt-4 text-gray-600 font-ui">Loading applications...</p>
            </div>
          ) : applications.length === 0 ? (
            <div className="p-12 text-center">
              <FileText className="w-16 h-16 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-600 font-ui">No applications found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-200">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Applicant
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Business
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Categories
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Submitted
                    </th>
                    <th className="px-6 py-4 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {applications.map((app) => (
                    <tr key={app.id} className="hover:bg-gray-50 transition">
                      <td className="px-6 py-4">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            {app.first_name} {app.last_name}
                          </p>
                          <p className="text-xs text-gray-500">{app.email}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div>
                          <p className="text-sm font-medium text-gray-900">{app.business_name}</p>
                          <p className="text-xs text-gray-500">{app.business_location}</p>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex flex-wrap gap-1">
                          {app.product_categories.slice(0, 2).map((cat, idx) => (
                            <span
                              key={idx}
                              className="inline-block px-2 py-0.5 rounded text-xs bg-blue-100 text-blue-800"
                            >
                              {cat}
                            </span>
                          ))}
                          {app.product_categories.length > 2 && (
                            <span className="inline-block px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600">
                              +{app.product_categories.length - 2}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">{getStatusBadge(app.status)}</td>
                      <td className="px-6 py-4">
                        <p className="text-sm text-gray-600">
                          {new Date(app.created_at).toLocaleDateString()}
                        </p>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => navigate(`/admin/vendor-applications/${app.id}`)}
                            className="p-2 text-gray-600 hover:text-[#105E53] hover:bg-gray-100 rounded-lg transition"
                            title="View details"
                          >
                            <Eye className="w-4 h-4" />
                          </button>

                          {app.status === 'pending_review' && (
                            <>
                              <button
                                onClick={() => handleApprove(app.id)}
                                disabled={actionLoading === app.id}
                                className="p-2 text-green-600 hover:text-green-700 hover:bg-green-50 rounded-lg transition disabled:opacity-50"
                                title="Approve"
                              >
                                <Check className="w-4 h-4" />
                              </button>
                              <button
                                onClick={() => handleReject(app.id)}
                                disabled={actionLoading === app.id}
                                className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition disabled:opacity-50"
                                title="Reject"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </>
                          )}

                          {canResendActivation(app) && (
                            <button
                              onClick={() => handleResendActivation(app)}
                              disabled={actionLoading === app.id}
                              className="p-2 text-[#105E53] hover:text-[#0c4c45] hover:bg-[#eef5f4] rounded-lg transition disabled:opacity-50"
                              title="Resend activation email"
                            >
                              <Mail className="w-4 h-4" />
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
    </div>
  );
}
