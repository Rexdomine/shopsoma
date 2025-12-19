import React, { createContext, useContext, useState, useCallback } from 'react';
import { vendorApplicationService, type VendorApplicationData } from '../services/vendorApplicationService';

interface VendorSignupContextType {
  // Step 1 data
  firstName: string;
  lastName: string;
  email: string;
  phoneCountryCode: string;
  phoneNumber: string;

  // Step 2 data
  businessName: string;
  businessLocation: string;
  isBusinessRegistered: string;
  productCategories: string[];
  localProductionLevel: string;
  yearsInBusiness: string;
  brandStory: string;
  websiteLink: string;
  socialMediaHandles: {
    instagram?: string;
    facebook?: string;
    twitter?: string;
    tiktok?: string;
  };

  // State management
  isSubmitting: boolean;
  error: string | null;

  // Actions
  setStep1Data: (data: Step1Data) => void;
  setStep2Data: (data: Step2Data) => void;
  submitApplication: () => Promise<boolean>;
  clearError: () => void;
}

export interface Step1Data {
  firstName: string;
  lastName: string;
  email: string;
  phoneCountryCode: string;
  phoneNumber: string;
}

export interface Step2Data {
  businessName: string;
  businessLocation: string;
  isBusinessRegistered: string;
  productCategories: string[];
  localProductionLevel: string;
  yearsInBusiness: string;
  brandStory: string;
  websiteLink: string;
  socialMediaHandles: {
    instagram?: string;
    facebook?: string;
    twitter?: string;
    tiktok?: string;
  };
}

const VendorSignupContext = createContext<VendorSignupContextType | undefined>(undefined);

export function VendorSignupProvider({ children }: { children: React.ReactNode }) {
  // Step 1 state
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phoneCountryCode, setPhoneCountryCode] = useState('+234');
  const [phoneNumber, setPhoneNumber] = useState('');

  // Step 2 state
  const [businessName, setBusinessName] = useState('');
  const [businessLocation, setBusinessLocation] = useState('');
  const [isBusinessRegistered, setIsBusinessRegistered] = useState('');
  const [productCategories, setProductCategories] = useState<string[]>([]);
  const [localProductionLevel, setLocalProductionLevel] = useState('');
  const [yearsInBusiness, setYearsInBusiness] = useState('');
  const [brandStory, setBrandStory] = useState('');
  const [websiteLink, setWebsiteLink] = useState('');
  const [socialMediaHandles, setSocialMediaHandles] = useState<{
    instagram?: string;
    facebook?: string;
    twitter?: string;
    tiktok?: string;
  }>({});

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setStep1Data = useCallback((data: Step1Data) => {
    setFirstName(data.firstName);
    setLastName(data.lastName);
    setEmail(data.email);
    setPhoneCountryCode(data.phoneCountryCode);
    setPhoneNumber(data.phoneNumber);
  }, []);

  const setStep2Data = useCallback((data: Step2Data) => {
    setBusinessName(data.businessName);
    setBusinessLocation(data.businessLocation);
    setIsBusinessRegistered(data.isBusinessRegistered);
    setProductCategories(data.productCategories);
    setLocalProductionLevel(data.localProductionLevel);
    setYearsInBusiness(data.yearsInBusiness);
    setBrandStory(data.brandStory);
    setWebsiteLink(data.websiteLink);
    setSocialMediaHandles(data.socialMediaHandles);
  }, []);

  const submitApplication = useCallback(async (): Promise<boolean> => {
    setIsSubmitting(true);
    setError(null);

    try {
      const applicationData: VendorApplicationData = {
        firstName,
        lastName,
        email,
        phoneCountryCode,
        phoneNumber,
        businessName,
        businessLocation,
        isBusinessRegistered: isBusinessRegistered || undefined,
        productCategories,
        localProductionLevel,
        yearsInBusiness,
        brandStory: brandStory || undefined,
        websiteLink: websiteLink || undefined,
        socialMediaHandles: Object.keys(socialMediaHandles).length > 0 ? socialMediaHandles : undefined,
      };

      await vendorApplicationService.submitApplication(applicationData);

      // Clear all data after successful submission
      setFirstName('');
      setLastName('');
      setEmail('');
      setPhoneCountryCode('+234');
      setPhoneNumber('');
      setBusinessName('');
      setBusinessLocation('');
      setIsBusinessRegistered('');
      setProductCategories([]);
      setLocalProductionLevel('');
      setYearsInBusiness('');
      setBrandStory('');
      setWebsiteLink('');
      setSocialMediaHandles({});

      return true;
    } catch (err: any) {
      const errorMessage = err?.response?.data?.detail || err?.message || 'Failed to submit application';
      setError(errorMessage);
      return false;
    } finally {
      setIsSubmitting(false);
    }
  }, [
    firstName,
    lastName,
    email,
    phoneCountryCode,
    phoneNumber,
    businessName,
    businessLocation,
    isBusinessRegistered,
    productCategories,
    localProductionLevel,
    yearsInBusiness,
    brandStory,
    websiteLink,
    socialMediaHandles,
  ]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const value = {
    firstName,
    lastName,
    email,
    phoneCountryCode,
    phoneNumber,
    businessName,
    businessLocation,
    isBusinessRegistered,
    productCategories,
    localProductionLevel,
    yearsInBusiness,
    brandStory,
    websiteLink,
    socialMediaHandles,
    isSubmitting,
    error,
    setStep1Data,
    setStep2Data,
    submitApplication,
    clearError,
  };

  return <VendorSignupContext.Provider value={value}>{children}</VendorSignupContext.Provider>;
}

export function useVendorSignup() {
  const context = useContext(VendorSignupContext);
  if (context === undefined) {
    throw new Error('useVendorSignup must be used within a VendorSignupProvider');
  }
  return context;
}
