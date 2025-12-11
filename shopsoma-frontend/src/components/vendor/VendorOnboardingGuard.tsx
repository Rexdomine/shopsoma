import { useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import { useVendor } from '../../context/VendorContext';
import Loading from '../common/Loading';

interface VendorOnboardingGuardProps {
  children: React.ReactNode;
}

/**
 * Guard component that enforces onboarding flow for vendors
 * - Redirects to brand-info if onboarding is not complete
 * - Prevents access to other vendor routes during onboarding
 */
export default function VendorOnboardingGuard({ children }: VendorOnboardingGuardProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { vendorProfile, isOnboarding, brandInfoCompleted, payoutInfoCompleted, isLoading } = useVendor();

  // Routes that are allowed during onboarding
  const allowedOnboardingRoutes = [
    ROUTES.VENDOR_SETTINGS,
    ROUTES.VENDOR_BRAND_INFO,
    ROUTES.VENDOR_PAYOUT_INFO,
    ROUTES.VENDOR_SECURITY,
  ];

  useEffect(() => {
    if (isLoading || !vendorProfile) return;

    // If vendor is in onboarding mode
    if (isOnboarding) {
      // Check if current route is allowed during onboarding
      const isAllowedRoute = allowedOnboardingRoutes.some(route =>
        location.pathname.startsWith(route)
      );

      if (!isAllowedRoute) {
        // Redirect to appropriate settings page based on completion status
        if (!brandInfoCompleted) {
          navigate(ROUTES.VENDOR_BRAND_INFO, { replace: true });
        } else if (!payoutInfoCompleted) {
          navigate(ROUTES.VENDOR_PAYOUT_INFO, { replace: true });
        } else {
          // Both are complete but onboarding flag not updated, redirect to brand info
          navigate(ROUTES.VENDOR_BRAND_INFO, { replace: true });
        }
        return;
      }

      // If on base /vendor/settings, redirect to brand-info
      if (location.pathname === ROUTES.VENDOR_SETTINGS) {
        navigate(ROUTES.VENDOR_BRAND_INFO, { replace: true });
        return;
      }
    } else {
      // Onboarding complete - if on /vendor/settings, redirect to brand-info
      if (location.pathname === ROUTES.VENDOR_SETTINGS) {
        navigate(ROUTES.VENDOR_BRAND_INFO, { replace: true });
        return;
      }
    }
  }, [location.pathname, navigate, isLoading, vendorProfile, isOnboarding, brandInfoCompleted, payoutInfoCompleted, allowedOnboardingRoutes]);

  if (isLoading) {
    return <Loading fullScreen message="Loading..." />;
  }

  return <>{children}</>;
}
