import { useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { ROUTES, STORAGE_KEYS } from '../../config/constants';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { useVendor } from '../../context/VendorContext';
import VendorWelcomePopup from '../../components/vendor/VendorWelcomePopup';

export default function VendorDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { vendorProfile, isOnboarding, brandInfoCompleted, payoutInfoCompleted, isLoading } = useVendor();
  const [showWelcomePopup, setShowWelcomePopup] = useState(false);

  const onboardingRoute = useMemo(() => {
    if (!brandInfoCompleted) {
      return ROUTES.VENDOR_BRAND_INFO;
    }

    if (!payoutInfoCompleted) {
      return ROUTES.VENDOR_PAYOUT_INFO;
    }

    return ROUTES.VENDOR_BRAND_INFO;
  }, [brandInfoCompleted, payoutInfoCompleted]);

  const onboardingStorageKey = useMemo(() => {
    if (!vendorProfile?.id) return null;
    return `${STORAGE_KEYS.VENDOR_ONBOARDING_WELCOME_SEEN}:${vendorProfile.id}`;
  }, [vendorProfile?.id]);

  useEffect(() => {
    // Redirect if not a vendor
    if (user && user.role !== 'vendor') {
      navigate(ROUTES.HOME, { replace: true });
      return;
    }
  }, [user, navigate]);

  useEffect(() => {
    if (isLoading || !vendorProfile || !isOnboarding || !onboardingStorageKey) {
      return;
    }

    const hasSeenWelcome = window.localStorage.getItem(onboardingStorageKey) === 'true';
    setShowWelcomePopup(!hasSeenWelcome);
  }, [isLoading, vendorProfile, isOnboarding, onboardingStorageKey]);

  const handleDismissWelcome = () => {
    if (onboardingStorageKey) {
      window.localStorage.setItem(onboardingStorageKey, 'true');
    }
    setShowWelcomePopup(false);
  };

  const handleCompleteProfile = () => {
    handleDismissWelcome();
    navigate(onboardingRoute);
  };

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
      <VendorWelcomePopup
        isOpen={showWelcomePopup}
        onClose={handleDismissWelcome}
        onCompleteProfile={handleCompleteProfile}
      />

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

          {vendorProfile && isOnboarding && (
            <div className="mb-6 overflow-hidden rounded-[24px] border border-[#dbe8e3] bg-[linear-gradient(135deg,#f5fbf8_0%,#ffffff_58%,#edf7f4_100%)] shadow-sm">
              <div className="flex flex-col gap-4 px-6 py-6 md:flex-row md:items-center md:justify-between">
                <div className="max-w-2xl">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-[0.25em] text-[#105E53]/70">
                    Vendor onboarding
                  </p>
                  <h2 className="text-2xl font-display text-[#12332c]">
                    Complete your profile before you start uploading products.
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-gray-600 font-ui">
                    Finish your brand and payout setup to unlock products, collections, earnings, and the rest of your
                    dashboard tools.
                  </p>
                </div>

                <div className="flex shrink-0 flex-col gap-3 sm:flex-row">
                  <button
                    type="button"
                    onClick={handleCompleteProfile}
                    className="rounded-full bg-[#105E53] px-6 py-3 text-sm font-semibold tracking-[0.08em] text-white transition hover:bg-[#0c4c45]"
                  >
                    Complete Profile
                  </button>
                </div>
              </div>
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
