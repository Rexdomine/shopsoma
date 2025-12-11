import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { vendorService, type VendorProfile } from '../services/vendorService';

interface VendorContextType {
  vendorProfile: VendorProfile | null;
  isOnboarding: boolean;
  brandInfoCompleted: boolean;
  payoutInfoCompleted: boolean;
  refreshProfile: () => Promise<void>;
  updateProfile: (profile: VendorProfile) => void;
  isLoading: boolean;
}

const VendorContext = createContext<VendorContextType | undefined>(undefined);

export function VendorProvider({ children }: { children: React.ReactNode }) {
  const [vendorProfile, setVendorProfile] = useState<VendorProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshProfile = useCallback(async () => {
    try {
      setIsLoading(true);
      const profile = await vendorService.getProfile();
      setVendorProfile(profile);
    } catch (error) {
      console.error('Failed to fetch vendor profile:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const updateProfile = useCallback((profile: VendorProfile) => {
    setVendorProfile(profile);
  }, []);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  const value = {
    vendorProfile,
    isOnboarding: vendorProfile?.is_onboarding ?? true,
    brandInfoCompleted: vendorProfile?.brand_info_completed ?? false,
    payoutInfoCompleted: vendorProfile?.payout_info_completed ?? false,
    refreshProfile,
    updateProfile,
    isLoading,
  };

  return <VendorContext.Provider value={value}>{children}</VendorContext.Provider>;
}

export function useVendor() {
  const context = useContext(VendorContext);
  if (context === undefined) {
    throw new Error('useVendor must be used within a VendorProvider');
  }
  return context;
}
