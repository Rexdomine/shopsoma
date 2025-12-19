import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, X, AlertCircle, CheckCircle, Clock, Mail, Phone, MapPin, Building, Package, User, Trash2 } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { adminService, type VendorApplication } from '../../services/adminService';
import { ROUTES } from '../../config/constants';

export default function AdminVendorApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [application, setApplication] = useState<VendorApplication | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    if (id) {
      loadApplication();
    }
  }, [id]);

  const loadApplication = async () => {
    if (!id) return;

    try {
      setLoading(true);
      const data = await adminService.getVendorApplication(id);
      setApplication(data);
    } catch (error: any) {
      console.error('Failed to load application:', error);
      showMessage('error', 'Failed to load application details');
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!application || !confirm('Are you sure you want to approve this vendor application? This will create a vendor account and send activation instructions.')) {
      return;
    }

    try {
      setActionLoading(true);
      await adminService.approveVendorApplication(application.id, 'Application approved by admin');
      showMessage('success', 'Application approved successfully! Vendor will receive activation email.');
      setTimeout(() => navigate(ROUTES.ADMIN_VENDOR_APPLICATIONS), 2000);
    } catch (error: any) {
      console.error('Failed to approve application:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to approve application';
      showMessage('error', errorMessage);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!application) return;

    const reason = prompt('Please provide a reason for rejection (optional):');
    if (reason === null) return; // User canceled

    try {
      setActionLoading(true);
      await adminService.rejectVendorApplication(application.id, reason || 'Application rejected by admin');
      showMessage('success', 'Application rejected successfully');
      setTimeout(() => navigate(ROUTES.ADMIN_VENDOR_APPLICATIONS), 2000);
    } catch (error: any) {
      console.error('Failed to reject application:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to reject application';
      showMessage('error', errorMessage);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!application) return;

    if (!confirm(`Are you sure you want to DELETE this application from ${application.first_name} ${application.last_name}? This action CANNOT be undone and will allow this email to be used for new applications.`)) {
      return;
    }

    try {
      setActionLoading(true);
      await adminService.deleteVendorApplication(application.id);
      showMessage('success', 'Application deleted successfully');
      setTimeout(() => navigate(ROUTES.ADMIN_VENDOR_APPLICATIONS), 1500);
    } catch (error: any) {
      console.error('Failed to delete application:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || 'Failed to delete application';
      showMessage('error', errorMessage);
    } finally {
      setActionLoading(false);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'pending_review':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-amber-100 text-amber-800">
            <Clock className="w-4 h-4" />
            Pending Review
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-green-100 text-green-800">
            <CheckCircle className="w-4 h-4" />
            Approved
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-red-100 text-red-800">
            <AlertCircle className="w-4 h-4" />
            Rejected
          </span>
        );
      default:
        return <span className="text-gray-500 text-sm">{status}</span>;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex gap-8 px-8 py-6">
        <AdminSidebar activeSection="vendor-applications" />
        <main className="flex-1 max-w-[1400px]">
          <div className="p-12 text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#105E53] mx-auto"></div>
            <p className="mt-4 text-gray-600 font-ui">Loading application...</p>
          </div>
        </main>
      </div>
    );
  }

  if (!application) {
    return (
      <div className="min-h-screen bg-[#FAFAF8] flex gap-8 px-8 py-6">
        <AdminSidebar activeSection="vendor-applications" />
        <main className="flex-1 max-w-[1400px]">
          <div className="p-12 text-center">
            <AlertCircle className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-600 font-ui">Application not found</p>
            <button
              onClick={() => navigate(ROUTES.ADMIN_VENDOR_APPLICATIONS)}
              className="mt-4 px-6 py-2 bg-[#105E53] text-white rounded-full hover:bg-[#0c4c45] transition"
            >
              Back to Applications
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAF8] flex gap-8 px-8 py-6">
      <AdminSidebar activeSection="vendor-applications" />

      <main className="flex-1 space-y-6 max-w-[1400px]">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => navigate(ROUTES.ADMIN_VENDOR_APPLICATIONS)}
              className="p-2 hover:bg-gray-100 rounded-lg transition"
            >
              <ArrowLeft className="w-5 h-5 text-gray-600" />
            </button>
            <div>
              <h1 className="text-3xl font-display text-gray-900">Vendor Application</h1>
              <p className="text-sm text-gray-600 font-ui mt-1">
                Submitted {new Date(application.created_at).toLocaleDateString('en-US', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric'
                })}
              </p>
            </div>
          </div>
          <div>{getStatusBadge(application.status)}</div>
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

        {/* Actions */}
        {application.status === 'pending_review' && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-lg font-display text-gray-900 mb-4">Actions</h2>
            <div className="flex items-center gap-3">
              <button
                onClick={handleApprove}
                disabled={actionLoading}
                className="flex items-center gap-2 px-6 py-3 bg-green-600 text-white rounded-full hover:bg-green-700 transition disabled:opacity-50 disabled:cursor-not-allowed font-ui text-sm"
              >
                <Check className="w-4 h-4" />
                Approve Application
              </button>
              <button
                onClick={handleReject}
                disabled={actionLoading}
                className="flex items-center gap-2 px-6 py-3 bg-red-600 text-white rounded-full hover:bg-red-700 transition disabled:opacity-50 disabled:cursor-not-allowed font-ui text-sm"
              >
                <X className="w-4 h-4" />
                Reject Application
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-3 font-ui">
              Approving will create a vendor account and send activation instructions to {application.email}
            </p>
          </div>
        )}

        {/* Danger Zone - Delete Application */}
        <div className="bg-red-50 rounded-2xl border border-red-200 shadow-sm p-6">
          <h2 className="text-lg font-display text-red-900 mb-2 flex items-center gap-2">
            <Trash2 className="w-5 h-5" />
            Danger Zone
          </h2>
          <p className="text-sm text-red-700 mb-4 font-ui">
            Delete this application permanently. This will allow the email address to be reused for new applications. This action cannot be undone.
          </p>
          <button
            onClick={handleDelete}
            disabled={actionLoading}
            className="flex items-center gap-2 px-6 py-3 bg-red-600 text-white rounded-full hover:bg-red-700 transition disabled:opacity-50 disabled:cursor-not-allowed font-ui text-sm"
          >
            <Trash2 className="w-4 h-4" />
            Delete Application
          </button>
        </div>

        {/* Applicant Information */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-display text-gray-900 mb-4 flex items-center gap-2">
            <User className="w-5 h-5 text-[#105E53]" />
            Applicant Information
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Full Name</label>
              <p className="mt-1 text-gray-900 font-ui">{application.first_name} {application.last_name}</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Email</label>
              <div className="mt-1 flex items-center gap-2">
                <Mail className="w-4 h-4 text-gray-400" />
                <p className="text-gray-900 font-ui">{application.email}</p>
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Phone</label>
              <div className="mt-1 flex items-center gap-2">
                <Phone className="w-4 h-4 text-gray-400" />
                <p className="text-gray-900 font-ui">{application.phone_number}</p>
              </div>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Location</label>
              <div className="mt-1 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-gray-400" />
                <p className="text-gray-900 font-ui">{application.business_location}</p>
              </div>
            </div>
          </div>
        </div>

        {/* Business Information */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-display text-gray-900 mb-4 flex items-center gap-2">
            <Building className="w-5 h-5 text-[#105E53]" />
            Business Information
          </h2>
          <div className="space-y-4">
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Business Name</label>
              <p className="mt-1 text-gray-900 font-ui text-lg">{application.business_name}</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Business Registration</label>
              <p className="mt-1 text-gray-900 font-ui">
                {application.is_business_registered ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-green-100 text-green-800">
                    <Check className="w-4 h-4" />
                    Registered
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm bg-gray-100 text-gray-800">
                    <X className="w-4 h-4" />
                    Not Registered
                  </span>
                )}
              </p>
            </div>
            {application.brand_story && (
              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Brand Story</label>
                <p className="mt-1 text-gray-700 font-ui leading-relaxed whitespace-pre-wrap">{application.brand_story}</p>
              </div>
            )}
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Years in Business</label>
              <p className="mt-1 text-gray-900 font-ui">{application.years_in_business}</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Local Production Level</label>
              <p className="mt-1 text-gray-900 font-ui">{application.local_production_level}</p>
            </div>
            {application.website_link && (
              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Website</label>
                <p className="mt-1">
                  <a
                    href={application.website_link.startsWith('http') ? application.website_link : `https://${application.website_link}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#105E53] hover:underline font-ui"
                  >
                    {application.website_link}
                  </a>
                </p>
              </div>
            )}
            {application.social_media_handles && Object.keys(application.social_media_handles).length > 0 && (
              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Social Media</label>
                <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-3">
                  {application.social_media_handles.instagram && (
                    <div>
                      <span className="text-xs text-gray-500 font-ui">Instagram:</span>
                      <p className="text-gray-900 font-ui mt-0.5">{application.social_media_handles.instagram}</p>
                    </div>
                  )}
                  {application.social_media_handles.facebook && (
                    <div>
                      <span className="text-xs text-gray-500 font-ui">Facebook:</span>
                      <p className="text-gray-900 font-ui mt-0.5">{application.social_media_handles.facebook}</p>
                    </div>
                  )}
                  {application.social_media_handles.twitter && (
                    <div>
                      <span className="text-xs text-gray-500 font-ui">X (Twitter):</span>
                      <p className="text-gray-900 font-ui mt-0.5">{application.social_media_handles.twitter}</p>
                    </div>
                  )}
                  {application.social_media_handles.tiktok && (
                    <div>
                      <span className="text-xs text-gray-500 font-ui">TikTok:</span>
                      <p className="text-gray-900 font-ui mt-0.5">{application.social_media_handles.tiktok}</p>
                    </div>
                  )}
                  {application.social_media_handles.pinterest && (
                    <div>
                      <span className="text-xs text-gray-500 font-ui">Pinterest:</span>
                      <p className="text-gray-900 font-ui mt-0.5">{application.social_media_handles.pinterest}</p>
                    </div>
                  )}
                  {application.social_media_handles.youtube && (
                    <div>
                      <span className="text-xs text-gray-500 font-ui">YouTube:</span>
                      <p className="text-gray-900 font-ui mt-0.5">{application.social_media_handles.youtube}</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Products & Categories */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-display text-gray-900 mb-4 flex items-center gap-2">
            <Package className="w-5 h-5 text-[#105E53]" />
            Products & Categories
          </h2>
          <div>
            <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Product Categories</label>
            <div className="mt-2 flex flex-wrap gap-2">
              {application.product_categories.map((category, idx) => (
                <span
                  key={idx}
                  className="inline-block px-3 py-1.5 rounded-lg text-sm bg-blue-100 text-blue-800 font-ui"
                >
                  {category}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Admin Notes */}
        {application.admin_notes && (
          <div className="bg-amber-50 rounded-2xl border border-amber-200 p-6">
            <h2 className="text-lg font-display text-gray-900 mb-2">Admin Notes</h2>
            <p className="text-gray-700 font-ui">{application.admin_notes}</p>
          </div>
        )}

        {/* Status Information */}
        {(application.status === 'approved' || application.status === 'rejected') && (
          <div className="bg-gray-50 rounded-2xl border border-gray-200 p-6">
            <h2 className="text-lg font-display text-gray-900 mb-4">Status Information</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</label>
                <div className="mt-1">{getStatusBadge(application.status)}</div>
              </div>
              {application.reviewed_at && (
                <div>
                  <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Reviewed Date</label>
                  <p className="mt-1 text-gray-900 font-ui">
                    {new Date(application.reviewed_at).toLocaleDateString('en-US', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
