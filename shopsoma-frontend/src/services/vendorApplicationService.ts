/**
 * Vendor Application Service
 * Handles vendor signup application submissions
 */
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface SocialMediaHandles {
  instagram?: string;
  facebook?: string;
  twitter?: string;
  tiktok?: string;
  pinterest?: string;
  youtube?: string;
}

export interface VendorApplicationData {
  // Personal Information (Step 1)
  firstName: string;
  lastName: string;
  email: string;
  phoneCountryCode: string;
  phoneNumber: string;

  // Business Information (Step 2)
  businessName: string;
  businessLocation: string;
  isBusinessRegistered?: string;
  productCategories: string[];
  localProductionLevel: string;
  yearsInBusiness: string;
  brandStory?: string;
  websiteLink?: string;
  socialMediaHandles?: SocialMediaHandles;
}

export interface VendorApplicationResponse {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  business_name: string;
  status: string;
  created_at: string;
}

export const vendorApplicationService = {
  /**
   * Submit vendor application
   */
  async submitApplication(data: VendorApplicationData): Promise<VendorApplicationResponse> {
    const payload = {
      first_name: data.firstName,
      last_name: data.lastName,
      email: data.email,
      phone_country_code: data.phoneCountryCode,
      phone_number: data.phoneNumber,
      business_name: data.businessName,
      business_location: data.businessLocation,
      is_business_registered: data.isBusinessRegistered,
      product_categories: data.productCategories,
      local_production_level: data.localProductionLevel,
      years_in_business: data.yearsInBusiness,
      brand_story: data.brandStory,
      website_link: data.websiteLink,
      social_media_handles: data.socialMediaHandles,
    };

    const response = await axios.post(`${API_URL}/api/v1/vendor-applications/`, payload);
    return response.data;
  },
};
