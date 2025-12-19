import { VendorProvider } from '../../context/VendorContext';
import VendorOnboardingGuard from './VendorOnboardingGuard';

interface VendorLayoutProps {
  children: React.ReactNode;
}

/**
 * Layout wrapper for vendor routes
 * - Provides VendorContext to all vendor pages
 * - Enforces onboarding flow via VendorOnboardingGuard
 */
export default function VendorLayout({ children }: VendorLayoutProps) {
  return (
    <VendorProvider>
      <VendorOnboardingGuard>
        {children}
      </VendorOnboardingGuard>
    </VendorProvider>
  );
}
