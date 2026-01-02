import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Store, Mail, Phone, MapPin, Calendar, Package, ShoppingBag, TrendingUp, CheckCircle, AlertCircle, Clock } from 'lucide-react';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { adminService } from '../../services/adminService';

export default function AdminVendorDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [vendor, setVendor] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (id) {
      loadVendorDetails();
    }
  }, [id]);

  const loadVendorDetails = async () => {
    try {
      setLoading(true);
      const data = await adminService.getVendor(id!);
      setVendor(data);
    } catch (error: any) {
      console.error('Failed to load vendor details:', error);
      showMessage('error', 'Failed to load vendor details');
    } finally {
      setLoading(false);
    }
  };

  const showMessage = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getKYCBadge = (status?: string) => {
    switch (status) {
      case 'pending':
        return (
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-700">
            <Clock className="w-4 h-4" />
            Pending
          </span>
        );
      case 'submitted':
        return (
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-700">
            <Clock className="w-4 h-4" />
            Submitted
          </span>
        );
      case 'approved':
        return (
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-700">
            <CheckCircle className="w-4 h-4" />
            Approved
          </span>
        );
      case 'rejected':
        return (
          <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-700">
            <AlertCircle className="w-4 h-4" />
            Rejected
          </span>
        );
      default:
        return <span className="text-sm text-gray-400">N/A</span>;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex gap-8 px-8 py-6">
        <AdminSidebar activeSection="vendors" />
        <main className="flex-1">
          <div className="flex items-center justify-center h-96">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#105E53]"></div>
          </div>
        </main>
      </div>
    );
  }

  if (!vendor) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex gap-8 px-8 py-6">
        <AdminSidebar activeSection="vendors" />
        <main className="flex-1">
          <div className="text-center py-12">
            <Store className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-600">Vendor not found</p>
            <button
              onClick={() => navigate('/admin/vendors')}
              className="mt-4 px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0d4a41] transition"
            >
              Back to Vendors
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex gap-8 px-8 py-6">
      <AdminSidebar activeSection="vendors" />

      <main className="flex-1 space-y-6 max-w-[1400px]">
        {/* Header */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/admin/vendors')}
            className="p-2 hover:bg-white rounded-lg transition"
          >
            <ArrowLeft className="w-5 h-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-3xl font-display text-gray-900">{vendor.business_name}</h1>
            <p className="text-gray-600 font-ui">Vendor Details</p>
          </div>
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
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Products</p>
                <p className="text-2xl font-display text-gray-900 mt-1">{vendor.total_products}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-blue-100 flex items-center justify-center">
                <Package className="w-6 h-6 text-blue-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Orders</p>
                <p className="text-2xl font-display text-gray-900 mt-1">{vendor.total_orders}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-purple-100 flex items-center justify-center">
                <ShoppingBag className="w-6 h-6 text-purple-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Revenue</p>
                <p className="text-2xl font-display text-gray-900 mt-1">{formatCurrency(vendor.total_revenue)}</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-green-100 flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-green-600" />
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Commission</p>
                <p className="text-2xl font-display text-gray-900 mt-1">{vendor.commission_rate}%</p>
              </div>
              <div className="h-12 w-12 rounded-xl bg-[#105E53]/10 flex items-center justify-center">
                <Store className="w-6 h-6 text-[#105E53]" />
              </div>
            </div>
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Business Information */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-xl font-display text-gray-900 mb-4">Business Information</h2>
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <Store className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Business Name</p>
                  <p className="text-sm font-medium text-gray-900">{vendor.business_name}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <MapPin className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Address</p>
                  <p className="text-sm font-medium text-gray-900">{vendor.business_address || 'N/A'}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Phone className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Phone</p>
                  <p className="text-sm font-medium text-gray-900">{vendor.business_phone || 'N/A'}</p>
                </div>
              </div>
              {vendor.business_description && (
                <div className="flex items-start gap-3">
                  <div className="w-5 h-5 mt-0.5" />
                  <div>
                    <p className="text-xs text-gray-500 uppercase tracking-wide">Description</p>
                    <p className="text-sm font-medium text-gray-900">{vendor.business_description}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* User Information */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-xl font-display text-gray-900 mb-4">Owner Information</h2>
            <div className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-full bg-[#105E53] flex items-center justify-center text-white font-semibold">
                  {vendor.user?.full_name?.charAt(0).toUpperCase() || 'V'}
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Full Name</p>
                  <p className="text-sm font-medium text-gray-900">{vendor.user?.full_name || 'N/A'}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Mail className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Email</p>
                  <p className="text-sm font-medium text-gray-900">{vendor.user?.email || 'N/A'}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Phone className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Phone</p>
                  <p className="text-sm font-medium text-gray-900">{vendor.user?.phone_number || 'N/A'}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Calendar className="w-5 h-5 text-gray-400 mt-0.5" />
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wide">Joined</p>
                  <p className="text-sm font-medium text-gray-900">{formatDate(vendor.user?.created_at)}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Account Status */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-xl font-display text-gray-900 mb-4">Account Status</h2>
            <div className="space-y-4">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Approval Status</p>
                {vendor.approved ? (
                  <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-700">
                    <CheckCircle className="w-4 h-4" />
                    Approved
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-amber-100 text-amber-700">
                    <Clock className="w-4 h-4" />
                    Pending
                  </span>
                )}
                {vendor.approved_at && (
                  <p className="text-xs text-gray-500 mt-1">on {formatDate(vendor.approved_at)}</p>
                )}
              </div>

              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">KYC Status</p>
                {getKYCBadge(vendor.kyc_status)}
                {vendor.kyc_submitted_at && (
                  <p className="text-xs text-gray-500 mt-1">Submitted on {formatDate(vendor.kyc_submitted_at)}</p>
                )}
              </div>

              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Account Active</p>
                {vendor.user?.is_active ? (
                  <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-700">
                    <CheckCircle className="w-4 h-4" />
                    Active
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-700">
                    <AlertCircle className="w-4 h-4" />
                    Inactive
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Onboarding Status */}
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-xl font-display text-gray-900 mb-4">Onboarding Status</h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">Brand Info</span>
                {vendor.brand_info_completed ? (
                  <CheckCircle className="w-5 h-5 text-green-600" />
                ) : (
                  <AlertCircle className="w-5 h-5 text-red-400" />
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-sm text-gray-700">Payout Info</span>
                {vendor.payout_info_completed ? (
                  <CheckCircle className="w-5 h-5 text-green-600" />
                ) : (
                  <AlertCircle className="w-5 h-5 text-red-400" />
                )}
              </div>
              {vendor.onboarding_completed_at && (
                <p className="text-xs text-gray-500 mt-2">
                  Completed on {formatDate(vendor.onboarding_completed_at)}
                </p>
              )}
              {vendor.is_onboarding && (
                <span className="inline-block px-3 py-1 rounded-full text-sm bg-amber-50 text-amber-700 border border-amber-200">
                  In Progress
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Bank Information */}
        {(vendor.bank_name || vendor.bank_account_number) && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <h2 className="text-xl font-display text-gray-900 mb-4">Bank Information</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Bank Name</p>
                <p className="text-sm font-medium text-gray-900">{vendor.bank_name || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Account Number</p>
                <p className="text-sm font-medium text-gray-900">{vendor.bank_account_number || 'N/A'}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Account Name</p>
                <p className="text-sm font-medium text-gray-900">{vendor.bank_account_name || 'N/A'}</p>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
