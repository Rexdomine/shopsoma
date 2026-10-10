import { useMemo, useState, useEffect, useRef } from 'react';
import { ArrowRight, ArrowLeft, AlertCircle, Loader2 } from 'lucide-react';
import { ROUTES } from '../../config/constants';
import { useNavigate, useLocation } from 'react-router-dom';
import { vendorApplicationService, type VendorApplicationData } from '../../services/vendorApplicationService';

type ChecklistItem = {
  label: string;
  key: string;
};

const SERVICES: ChecklistItem[] = [
  { label: "Women's Fashion", key: 'womens' },
  { label: "Men's Fashion", key: 'mens' },
  { label: 'Jewelry', key: 'jewelry' },
  { label: 'Bags/Accessories', key: 'bags' },
  { label: 'Skincare', key: 'skincare' },
  { label: 'Beauty and Makeup', key: 'beauty' },
  { label: 'Homewares', key: 'homewares' },
];

const LOCALITY = [
  { label: 'We source all our products locally - 100%', key: 'all' },
  { label: 'We source most locally', key: 'most' },
  { label: 'We source some locally', key: 'some' },
  { label: "We don't source locally - 0%", key: 'none' },
];

export default function VendorSignupBusiness() {
  const navigate = useNavigate();
  const location = useLocation();

  // Get personal info from previous step
  const personalInfo = location.state as {
    firstName: string;
    lastName: string;
    email: string;
    phoneCode: string;
    phoneNumber: string;
  } | null;

  const [businessName, setBusinessName] = useState('');
  const [businessLocation, setBusinessLocation] = useState('');
  const [registration, setRegistration] = useState('');
  const [services, setServices] = useState<Record<string, boolean>>({});
  const [locality, setLocality] = useState<string>('');
  const [years, setYears] = useState('');
  const [brandStory, setBrandStory] = useState('');
  const [website, setWebsite] = useState('');

  // Individual social media fields
  const [socialInstagram, setSocialInstagram] = useState('');
  const [socialFacebook, setSocialFacebook] = useState('');
  const [socialTwitter, setSocialTwitter] = useState('');
  const [socialTiktok, setSocialTiktok] = useState('');
  const [socialPinterest, setSocialPinterest] = useState('');
  const [socialYoutube, setSocialYoutube] = useState('');

  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState('');

  const businessNameRef = useRef<HTMLInputElement>(null);
  const businessLocationRef = useRef<HTMLInputElement>(null);
  const categoriesRef = useRef<HTMLDivElement>(null);
  const localityRef = useRef<HTMLDivElement>(null);
  const yearsRef = useRef<HTMLInputElement>(null);

  // Redirect back if no personal info
  useEffect(() => {
    if (!personalInfo) {
      navigate(ROUTES.VENDOR_SIGNUP, { replace: true });
    }
  }, [personalInfo, navigate]);

  const selectedServices = useMemo(
    () => Object.keys(services).filter((key) => services[key]),
    [services]
  );

  // Field validation rules
  const errors = useMemo(() => {
    const errs: Record<string, string> = {};

    if (!businessName.trim()) {
      errs.businessName = 'Business name is required';
    }

    if (!businessLocation.trim()) {
      errs.businessLocation = 'Business location address is required';
    }

    if (selectedServices.length === 0) {
      errs.productCategories = 'Please select at least one product/service category';
    }

    if (!locality.trim()) {
      errs.locality = 'Please select what percentage of your products are made locally';
    }

    if (!years.trim()) {
      errs.years = 'Please specify how many years you have been in business';
    }

    return errs;
  }, [businessName, businessLocation, selectedServices.length, locality, years]);

  const hasErrors = Object.keys(errors).length > 0;

  const handleBlur = (field: string) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  };

  const toggleService = (key: string) => {
    setServices((prev) => ({ ...prev, [key]: !prev[key] }));
    setTouched((prev) => ({ ...prev, productCategories: true }));
  };

  const handleLocalityChange = (key: string) => {
    setLocality(key);
    setTouched((prev) => ({ ...prev, locality: true }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitAttempted(true);
    setTouched({
      businessName: true,
      businessLocation: true,
      productCategories: true,
      locality: true,
      years: true,
    });

    if (hasErrors) {
      // Focus and scroll to first error
      if (errors.businessName) {
        businessNameRef.current?.focus();
        businessNameRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      } else if (errors.businessLocation) {
        businessLocationRef.current?.focus();
        businessLocationRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      } else if (errors.productCategories) {
        categoriesRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      } else if (errors.locality) {
        localityRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      } else if (errors.years) {
        yearsRef.current?.focus();
        yearsRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      }
      return;
    }

    if (submitting || !personalInfo) return;

    setSubmitting(true);
    setServerError('');

    try {
      // Build social media handles object with only non-empty fields
      const socialMediaHandles: Record<string, string> = {};
      if (socialInstagram.trim()) socialMediaHandles.instagram = socialInstagram.trim();
      if (socialFacebook.trim()) socialMediaHandles.facebook = socialFacebook.trim();
      if (socialTwitter.trim()) socialMediaHandles.twitter = socialTwitter.trim();
      if (socialTiktok.trim()) socialMediaHandles.tiktok = socialTiktok.trim();
      if (socialPinterest.trim()) socialMediaHandles.pinterest = socialPinterest.trim();
      if (socialYoutube.trim()) socialMediaHandles.youtube = socialYoutube.trim();

      const applicationData: VendorApplicationData = {
        // Personal info from step 1
        firstName: personalInfo.firstName,
        lastName: personalInfo.lastName,
        email: personalInfo.email,
        phoneCountryCode: personalInfo.phoneCode,
        phoneNumber: personalInfo.phoneNumber,

        // Business info from this step
        businessName: businessName.trim(),
        businessLocation: businessLocation.trim(),
        isBusinessRegistered: registration.trim() || undefined,
        productCategories: selectedServices,
        localProductionLevel: locality,
        yearsInBusiness: years.trim(),
        brandStory: brandStory.trim() || undefined,
        websiteLink: website.trim() || undefined,
        socialMediaHandles: Object.keys(socialMediaHandles).length > 0 ? (socialMediaHandles as any) : undefined,
      };

      await vendorApplicationService.submitApplication(applicationData);

      // Navigate to thank you page
      navigate(ROUTES.VENDOR_SIGNUP_THANK_YOU, { replace: true });
    } catch (err: any) {
      console.error('Failed to submit application:', err);
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: any) => d.msg || d.message).join(', ')
          : 'Failed to submit application. Please check your information and try again.';
      setServerError(msg);
      try {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } catch {
        // Safe fallback in test/unsupported environments
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (!personalInfo) {
    return null; // Will redirect in useEffect
  }

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] px-6 py-12 flex flex-col items-center">
      <div className="flex flex-col items-center gap-6 mt-6 mb-10 text-center">
        <img src="/images/somalogo.svg" alt="Shopsoma" className="h-10 w-auto" />
        <div className="space-y-1">
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-display text-[#105E53]">Wanna join the Shopsoma Family?</h1>
          <h2 className="text-2xl sm:text-3xl md:text-4xl font-display text-[#105E53]">Sign up below!</h2>
        </div>
      </div>

      <form
        onSubmit={handleSubmit}
        noValidate
        className="w-full max-w-5xl bg-white/80 border border-gray-200 rounded-[32px] shadow-sm px-8 sm:px-12 py-10 space-y-6"
      >
        <div className="space-y-1 text-left">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 font-ui font-medium">Business Information</p>
            <span className="text-xs font-semibold px-3 py-1 rounded-full bg-[#105E53]/10 text-[#105E53] font-ui">
              Step 2 of 2
            </span>
          </div>
          <h3 className="text-2xl font-display text-gray-800 leading-tight">
            Now that we're Acquainted,
            <br />
            Tell us about your Brand
          </h3>
          <p className="text-sm text-gray-600 font-ui">Please fill in your business details below</p>
        </div>

        {/* Server Error Alert */}
        {serverError && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 text-red-700 px-5 py-4 rounded-2xl flex items-start gap-3 text-sm font-ui animate-in fade-in duration-150"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-500 mt-0.5" />
            <div>
              <p className="font-semibold text-red-800">Application Error:</p>
              <p className="text-xs text-red-600 mt-0.5">{serverError}</p>
            </div>
          </div>
        )}

        {/* Validation Summary Alert */}
        {submitAttempted && hasErrors && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 text-red-700 px-5 py-3.5 rounded-2xl flex items-start gap-3 text-sm font-ui animate-in fade-in duration-150"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-500 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold text-red-800">Please complete all required fields:</p>
              <ul className="list-disc list-inside text-xs text-red-600 space-y-0.5">
                {Object.values(errors).map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Business Name */}
        <div className="space-y-1.5">
          <label htmlFor="businessName" className="text-sm text-gray-700 font-ui font-medium">
            What's your business name? <span className="text-red-500">*</span>
          </label>
          <input
            id="businessName"
            ref={businessNameRef}
            type="text"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            onBlur={() => handleBlur('businessName')}
            placeholder="Business Name"
            aria-invalid={!!((touched.businessName || submitAttempted) && errors.businessName)}
            aria-describedby={(touched.businessName || submitAttempted) && errors.businessName ? 'businessName-error' : undefined}
            className={`w-full rounded-2xl border bg-white px-4 py-3 text-gray-800 focus:outline-none transition ${
              (touched.businessName || submitAttempted) && errors.businessName
                ? 'border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-200 bg-red-50/20'
                : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
            }`}
          />
          {(touched.businessName || submitAttempted) && errors.businessName && (
            <p id="businessName-error" className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.businessName}</span>
            </p>
          )}
        </div>

        {/* Business Location */}
        <div className="space-y-1.5">
          <div>
            <label htmlFor="businessLocation" className="text-sm text-gray-700 font-ui font-medium">
              Where is your business located? <span className="text-red-500">*</span>
            </label>
            <p className="text-xs text-gray-500 font-ui">
              (Kindly share a detailed address, we need this to assign you a collection agent)
            </p>
          </div>
          <input
            id="businessLocation"
            ref={businessLocationRef}
            type="text"
            value={businessLocation}
            onChange={(e) => setBusinessLocation(e.target.value)}
            onBlur={() => handleBlur('businessLocation')}
            placeholder="e.g. 12 Broad Street, Victoria Island, Lagos"
            aria-invalid={!!((touched.businessLocation || submitAttempted) && errors.businessLocation)}
            aria-describedby={(touched.businessLocation || submitAttempted) && errors.businessLocation ? 'businessLocation-error' : undefined}
            className={`w-full rounded-2xl border bg-white px-4 py-3 text-gray-800 focus:outline-none transition ${
              (touched.businessLocation || submitAttempted) && errors.businessLocation
                ? 'border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-200 bg-red-50/20'
                : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
            }`}
          />
          {(touched.businessLocation || submitAttempted) && errors.businessLocation && (
            <p id="businessLocation-error" className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.businessLocation}</span>
            </p>
          )}
        </div>

        {/* Business Registration (Optional) */}
        <div className="space-y-1.5">
          <div>
            <label htmlFor="registration" className="text-sm text-gray-700 font-ui font-medium">
              Is your business registered?
            </label>
            <p className="text-xs text-gray-500 font-ui">
              If YES, please provide the registration/CAC number. If it isn't registered, just answer "NO".
            </p>
          </div>
          <input
            id="registration"
            type="text"
            value={registration}
            onChange={(e) => setRegistration(e.target.value)}
            placeholder='e.g., RC1234567 or "NO"'
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        {/* Product Categories */}
        <div ref={categoriesRef} className="space-y-2">
          <div>
            <label className="text-sm text-gray-800 font-ui font-medium">
              What products/services does your company offer? <span className="text-red-500">*</span>
            </label>
            <p className="text-xs text-gray-500 font-ui">Select all that apply</p>
          </div>
          <div
            className={`p-4 rounded-2xl border transition ${
              (touched.productCategories || submitAttempted) && errors.productCategories
                ? 'border-red-400 bg-red-50/20'
                : 'border-gray-200 bg-white/50'
            }`}
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {SERVICES.map((item) => (
                <label key={item.key} className="flex items-center gap-2.5 text-sm text-gray-800 font-ui cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={!!services[item.key]}
                    onChange={() => toggleService(item.key)}
                    className="h-4 w-4 rounded border-gray-300 text-[#105E53] focus:ring-[#105E53] cursor-pointer"
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>
          {(touched.productCategories || submitAttempted) && errors.productCategories && (
            <p className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.productCategories}</span>
            </p>
          )}
        </div>

        {/* Locality Percentage */}
        <div ref={localityRef} className="space-y-2">
          <div>
            <label className="text-sm text-gray-800 font-ui font-medium">
              What percentage of your products are made locally? <span className="text-red-500">*</span>
            </label>
            <p className="text-xs text-gray-500 font-ui">Select one</p>
          </div>
          <div
            className={`p-4 rounded-2xl border transition ${
              (touched.locality || submitAttempted) && errors.locality
                ? 'border-red-400 bg-red-50/20'
                : 'border-gray-200 bg-white/50'
            }`}
          >
            <div className="space-y-2.5">
              {LOCALITY.map((item) => (
                <label key={item.key} className="flex items-center gap-2.5 text-sm text-gray-800 font-ui cursor-pointer select-none">
                  <input
                    type="radio"
                    name="locality"
                    checked={locality === item.key}
                    onChange={() => handleLocalityChange(item.key)}
                    className="h-4 w-4 border-gray-300 text-[#105E53] focus:ring-[#105E53] cursor-pointer"
                  />
                  <span>{item.label}</span>
                </label>
              ))}
            </div>
          </div>
          {(touched.locality || submitAttempted) && errors.locality && (
            <p className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.locality}</span>
            </p>
          )}
        </div>

        {/* Years in Business */}
        <div className="space-y-1.5">
          <label htmlFor="years" className="text-sm text-gray-700 font-ui font-medium">
            How many years have you been actively in business? <span className="text-red-500">*</span>
          </label>
          <input
            id="years"
            ref={yearsRef}
            type="text"
            value={years}
            onChange={(e) => setYears(e.target.value)}
            onBlur={() => handleBlur('years')}
            placeholder="e.g., 3 years"
            aria-invalid={!!((touched.years || submitAttempted) && errors.years)}
            aria-describedby={(touched.years || submitAttempted) && errors.years ? 'years-error' : undefined}
            className={`w-full rounded-2xl border bg-white px-4 py-3 text-gray-800 focus:outline-none transition ${
              (touched.years || submitAttempted) && errors.years
                ? 'border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-200 bg-red-50/20'
                : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
            }`}
          />
          {(touched.years || submitAttempted) && errors.years && (
            <p id="years-error" className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.years}</span>
            </p>
          )}
        </div>

        {/* Brand Story (Optional) */}
        <div className="space-y-1.5">
          <div>
            <label htmlFor="brandStory" className="text-sm text-gray-700 font-ui font-medium">
              What makes your brand extra special?
            </label>
            <p className="text-xs text-gray-500 font-ui">
              This will help us highlight the authenticity of your products to our audience and help your products get sold quicker.
            </p>
          </div>
          <textarea
            id="brandStory"
            value={brandStory}
            onChange={(e) => setBrandStory(e.target.value)}
            rows={3}
            placeholder="Tell us your brand story..."
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        {/* Website Link (Optional) */}
        <div className="space-y-1.5">
          <div>
            <label htmlFor="website" className="text-sm text-gray-700 font-ui font-medium">
              Your Website Link
            </label>
            <p className="text-xs text-gray-500 font-ui">If you don't have an existing website at the moment please write "NO".</p>
          </div>
          <input
            id="website"
            type="text"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="https://yourwebsite.com"
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        {/* Social Media (Optional) */}
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-800 font-ui font-medium">Social Media</label>
            <p className="text-xs text-gray-500 font-ui">
              Please add your brand's handles/links for each platform (where applicable). All fields are optional.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label htmlFor="instagram" className="text-xs text-gray-600 font-ui font-medium">Instagram</label>
              <input
                id="instagram"
                type="text"
                value={socialInstagram}
                onChange={(e) => setSocialInstagram(e.target.value)}
                placeholder="@yourbrand or URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="facebook" className="text-xs text-gray-600 font-ui font-medium">Facebook</label>
              <input
                id="facebook"
                type="text"
                value={socialFacebook}
                onChange={(e) => setSocialFacebook(e.target.value)}
                placeholder="Facebook page URL or handle"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="twitter" className="text-xs text-gray-600 font-ui font-medium">X (Twitter)</label>
              <input
                id="twitter"
                type="text"
                value={socialTwitter}
                onChange={(e) => setSocialTwitter(e.target.value)}
                placeholder="@yourbrand or URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="tiktok" className="text-xs text-gray-600 font-ui font-medium">TikTok</label>
              <input
                id="tiktok"
                type="text"
                value={socialTiktok}
                onChange={(e) => setSocialTiktok(e.target.value)}
                placeholder="@yourbrand or URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="pinterest" className="text-xs text-gray-600 font-ui font-medium">Pinterest</label>
              <input
                id="pinterest"
                type="text"
                value={socialPinterest}
                onChange={(e) => setSocialPinterest(e.target.value)}
                placeholder="Pinterest profile URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="youtube" className="text-xs text-gray-600 font-ui font-medium">YouTube</label>
              <input
                id="youtube"
                type="text"
                value={socialYoutube}
                onChange={(e) => setSocialYoutube(e.target.value)}
                placeholder="YouTube channel URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>
          </div>
        </div>

        {/* Buttons / Actions */}
        <div className="pt-6 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-gray-100">
          <button
            type="button"
            onClick={() => navigate(ROUTES.VENDOR_SIGNUP, { state: personalInfo })}
            disabled={submitting}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-full border border-gray-300 bg-white hover:bg-gray-50 active:bg-gray-100 text-gray-700 px-6 py-3 font-ui text-sm font-medium transition cursor-pointer"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Back to Personal Info</span>
          </button>

          <button
            type="submit"
            disabled={submitting}
            className="w-full sm:w-auto min-w-[200px] inline-flex items-center justify-center gap-2 rounded-full bg-[#105E53] hover:bg-[#0c4c45] active:bg-[#093c35] text-white px-8 py-3.5 font-ui text-sm font-medium tracking-wide transition shadow-sm hover:shadow disabled:opacity-60 disabled:cursor-not-allowed cursor-pointer"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Submitting Application...</span>
              </>
            ) : (
              <>
                <span>Submit Application</span>
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </button>
        </div>

        <p className="text-xs text-center text-gray-500 font-ui">
          * Required fields
        </p>
      </form>
    </div>
  );
}
