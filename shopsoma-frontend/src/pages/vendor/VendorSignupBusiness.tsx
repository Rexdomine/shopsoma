import { useMemo, useState, useEffect } from 'react';
import { ArrowRight, AlertCircle } from 'lucide-react';
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

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Redirect back if no personal info
  useEffect(() => {
    if (!personalInfo) {
      navigate(ROUTES.VENDOR_SIGNUP, { replace: true });
    }
  }, [personalInfo, navigate]);

  const selectedServices = Object.keys(services).filter((key) => services[key]);

  const isValid = useMemo(
    () =>
      businessName.trim() !== '' &&
      businessLocation.trim() !== '' &&
      selectedServices.length > 0 &&
      locality.trim() !== '' &&
      years.trim() !== '',
    [businessName, businessLocation, selectedServices.length, locality, years]
  );

  const toggleService = (key: string) => {
    setServices((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid || submitting || !personalInfo) return;

    setSubmitting(true);
    setError('');

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
        businessName,
        businessLocation,
        isBusinessRegistered: registration.trim() || undefined,
        productCategories: selectedServices,
        localProductionLevel: locality,
        yearsInBusiness: years,
        brandStory: brandStory.trim() || undefined,
        websiteLink: website.trim() || undefined,
        socialMediaHandles: Object.keys(socialMediaHandles).length > 0 ? socialMediaHandles as any : undefined,
      };

      await vendorApplicationService.submitApplication(applicationData);

      // Navigate to thank you page
      navigate(ROUTES.VENDOR_SIGNUP_THANK_YOU, { replace: true });
    } catch (err: any) {
      console.error('Failed to submit application:', err);
      setError(err?.response?.data?.detail || 'Failed to submit application. Please try again.');
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
        className="w-full max-w-5xl bg-white/80 border border-gray-200 rounded-[32px] shadow-sm px-8 sm:px-12 py-10 space-y-6"
      >
        <div className="space-y-1 text-left">
          <p className="text-sm text-gray-500 font-ui">Business Information</p>
          <h3 className="text-2xl font-display text-gray-800 leading-tight">
            Now that we're Acquainted,
            <br />
            Tell us about your Brand
          </h3>
          <p className="text-sm text-gray-600 font-ui">Please fill the information below</p>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl flex items-start gap-2">
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <span className="text-sm">{error}</span>
          </div>
        )}

        <div className="space-y-2">
          <label className="text-sm text-gray-700 font-ui">What's your business name? *</label>
          <input
            type="text"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            required
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        <div className="space-y-2">
          <div>
            <label className="text-sm text-gray-700 font-ui">Where is your business located? *</label>
            <p className="text-xs text-gray-500 font-ui">
              (Kindly share a detailed address, we need this to assign you a collection agent)
            </p>
          </div>
          <input
            type="text"
            value={businessLocation}
            onChange={(e) => setBusinessLocation(e.target.value)}
            required
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        <div className="space-y-2">
          <div>
            <label className="text-sm text-gray-700 font-ui">Is your business registered?</label>
            <p className="text-xs text-gray-500 font-ui">
              If YES, please provide the registration/CAC number. If it isn't registered, just answer "NO".
            </p>
          </div>
          <input
            type="text"
            value={registration}
            onChange={(e) => setRegistration(e.target.value)}
            placeholder='e.g., RC1234567 or "NO"'
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-800 font-ui">What products/services does your company offer? *</label>
            <p className="text-xs text-gray-500 font-ui">Select all that apply</p>
          </div>
          <div className="space-y-2">
            {SERVICES.map((item) => (
              <label key={item.key} className="flex items-center gap-2 text-sm text-gray-800 font-ui cursor-pointer">
                <input
                  type="checkbox"
                  checked={!!services[item.key]}
                  onChange={() => toggleService(item.key)}
                  className="h-4 w-4 rounded border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                />
                {item.label}
              </label>
            ))}
          </div>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-sm text-gray-800 font-ui">What percentage of your products are made locally? *</label>
            <p className="text-xs text-gray-500 font-ui">Select one</p>
          </div>
          <div className="space-y-2">
            {LOCALITY.map((item) => (
              <label key={item.key} className="flex items-center gap-2 text-sm text-gray-800 font-ui cursor-pointer">
                <input
                  type="radio"
                  name="locality"
                  checked={locality === item.key}
                  onChange={() => setLocality(item.key)}
                  className="h-4 w-4 border-gray-300 text-[#105E53] focus:ring-[#105E53]"
                />
                {item.label}
              </label>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm text-gray-700 font-ui">How many years have you been actively in business? *</label>
          <input
            type="text"
            value={years}
            onChange={(e) => setYears(e.target.value)}
            required
            placeholder="e.g., 3 years"
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        <div className="space-y-2">
          <div>
            <label className="text-sm text-gray-700 font-ui">What makes your brand extra special?</label>
            <p className="text-xs text-gray-500 font-ui">
              This will help us highlight the authenticity of your products to our audience and help your products get sold quicker.
            </p>
          </div>
          <textarea
            value={brandStory}
            onChange={(e) => setBrandStory(e.target.value)}
            rows={3}
            placeholder="Tell us your brand story..."
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        <div className="space-y-2">
          <div>
            <label className="text-sm text-gray-700 font-ui">Your Website Link</label>
            <p className="text-xs text-gray-500 font-ui">If you don't have an existing website at the moment please write "NO".</p>
          </div>
          <input
            type="text"
            value={website}
            onChange={(e) => setWebsite(e.target.value)}
            placeholder="https://yourwebsite.com"
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
          />
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-800 font-ui">Social Media</label>
            <p className="text-xs text-gray-500 font-ui">
              Please add your brand's handles/links for each platform (where applicable). All fields are optional.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs text-gray-600 font-ui">Instagram</label>
              <input
                type="text"
                value={socialInstagram}
                onChange={(e) => setSocialInstagram(e.target.value)}
                placeholder="@yourbrand or URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-gray-600 font-ui">Facebook</label>
              <input
                type="text"
                value={socialFacebook}
                onChange={(e) => setSocialFacebook(e.target.value)}
                placeholder="Facebook page URL or handle"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-gray-600 font-ui">X (Twitter)</label>
              <input
                type="text"
                value={socialTwitter}
                onChange={(e) => setSocialTwitter(e.target.value)}
                placeholder="@yourbrand or URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-gray-600 font-ui">TikTok</label>
              <input
                type="text"
                value={socialTiktok}
                onChange={(e) => setSocialTiktok(e.target.value)}
                placeholder="@yourbrand or URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-gray-600 font-ui">Pinterest</label>
              <input
                type="text"
                value={socialPinterest}
                onChange={(e) => setSocialPinterest(e.target.value)}
                placeholder="Pinterest profile URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs text-gray-600 font-ui">YouTube</label>
              <input
                type="text"
                value={socialYoutube}
                onChange={(e) => setSocialYoutube(e.target.value)}
                placeholder="YouTube channel URL"
                className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-2.5 text-sm text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              />
            </div>
          </div>
        </div>

        <div className="pt-4 flex justify-center">
          <button
            type="submit"
            disabled={!isValid || submitting}
            className="min-w-[180px] inline-flex items-center justify-center gap-2 rounded-full bg-[#105E53] text-white px-8 py-3 font-ui text-sm tracking-wide disabled:opacity-60 disabled:cursor-not-allowed hover:bg-[#0c4c45] transition"
          >
            {submitting ? 'Submitting...' : 'Submit Application'}
            {!submitting && <ArrowRight className="h-4 w-4" />}
          </button>
        </div>

        <p className="text-xs text-center text-gray-500 font-ui">
          * Required fields
        </p>
      </form>
    </div>
  );
}
