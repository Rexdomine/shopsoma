import { useEffect } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { useVendor } from '../../context/VendorContext';

export default function VendorDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { vendorProfile, isOnboarding, brandInfoCompleted, isLoading } = useVendor();

  useEffect(() => {
    // Redirect if not a vendor
    if (user && user.role !== 'vendor') {
      navigate(ROUTES.HOME, { replace: true });
      return;
    }
  }, [user, navigate]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#105E53] mx-auto"></div>
          <p className="mt-4 text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  // Calculate disableNav based on VendorContext
  const disableNav = isOnboarding && !brandInfoCompleted;

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex">
      <VendorSidebar
        disableMain={disableNav}
        pendingOrders={vendorProfile?.total_orders || 0}
        completedOrders={vendorProfile?.total_orders || 0}
      />

      <main className="flex-1 p-8">
        <div>
          <div className="bg-white border-b border-gray-200 mb-6">
            <div className="py-4">
              <h1 className="text-3xl font-display text-[#105E53]">Vendor Dashboard</h1>
              <p className="mt-2 text-sm text-gray-600">Welcome back, {user?.full_name}!</p>
            </div>
          </div>

          {vendorProfile && !vendorProfile.approved && (
            <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <h3 className="text-yellow-800 font-semibold">Pending Approval</h3>
              <p className="text-yellow-700 text-sm mt-1">
                Your vendor account is pending approval. You'll be notified once it's activated.
              </p>
            </div>
          )}

          {vendorProfile && (
            <>
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
                <h2 className="text-xl font-display text-[#105E53] mb-4">Business Information</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-gray-500">Business Name</p>
                    <p className="text-base font-medium text-gray-900">{vendorProfile.business_name}</p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-500">KYC Status</p>
                    <p className="text-base font-medium text-gray-900 capitalize">{vendorProfile.kyc_status}</p>
                  </div>
                  {vendorProfile.business_description && (
                    <div className="md:col-span-2">
                      <p className="text-sm text-gray-500">Description</p>
                      <p className="text-base text-gray-900">{vendorProfile.business_description}</p>
                    </div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <p className="text-sm text-gray-500 mb-2">Total Products</p>
                  <p className="text-3xl font-display text-[#105E53]">{vendorProfile.total_products}</p>
                </div>
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <p className="text-sm text-gray-500 mb-2">Total Orders</p>
                  <p className="text-3xl font-display text-[#105E53]">{vendorProfile.total_orders}</p>
                </div>
                <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                  <p className="text-sm text-gray-500 mb-2">Total Revenue</p>
                  <p className="text-3xl font-display text-[#105E53]">₦{parseFloat(vendorProfile.total_revenue).toLocaleString()}</p>
                </div>
              </div>
            </>
          )}

          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8 text-center">
            <h3 className="text-xl font-display text-[#105E53] mb-2">Dashboard Coming Soon</h3>
            <p className="text-gray-600">
              Full vendor dashboard with product management, order tracking, and analytics is under development.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
