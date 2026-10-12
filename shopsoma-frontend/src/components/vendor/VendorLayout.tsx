import { VendorProvider } from '../../context/VendorContext';
import VendorOnboardingGuard from './VendorOnboardingGuard';
import ProtectedRoute from '../common/ProtectedRoute';

interface VendorLayoutProps {
  children: React.ReactNode;
}

/**
 * Layout wrapper for vendor routes
 * - Enforces authentication and vendor role via ProtectedRoute
 * - Provides VendorContext to all vendor pages
 * - Enforces onboarding flow via VendorOnboardingGuard
 */
export default function VendorLayout({ children }: VendorLayoutProps) {
  return (
    <ProtectedRoute roles={['vendor']}>
      <VendorProvider>
        <VendorOnboardingGuard>
          {children}
        </VendorOnboardingGuard>
      </VendorProvider>
    </ProtectedRoute>
  );
}
