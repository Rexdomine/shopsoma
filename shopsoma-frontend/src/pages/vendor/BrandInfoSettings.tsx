import { useEffect, useMemo, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { Check, Image as ImageIcon, ChevronDown, PauseCircle, Trash2 } from 'lucide-react';
import { vendorService, type BrandInfoData, type PayoutInfoData } from '../../services/vendorService';
import { vendorPaymentMethodsService, type PaymentMethod, type PaymentMethodCreate } from '../../services/vendorPaymentMethodsService';
import { useVendor } from '../../context/VendorContext';
import { useAuth } from '../../context/AuthContext';

type Contact = { phone: string; email: string };
type Address = { country: string; address: string };
type SelectOption = { label: string; value: string };

function CustomSelect({
  value,
  onChange,
  options,
  placeholder,
  disabled = false,
}: {
  value: string;
  onChange: (val: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.value === value);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => !disabled && setOpen((v) => !v)}
        disabled={disabled}
        className={`w-full rounded-xl px-4 py-3 pr-10 border border-gray-200 bg-gray-50 text-gray-700 text-left shadow-[inset_0_1px_2px_rgba(0,0,0,0.04)] whitespace-nowrap overflow-hidden text-ellipsis text-base leading-6 ${
          disabled
            ? 'cursor-not-allowed opacity-60'
            : 'cursor-pointer focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
        }`}
      >
        {selected?.label || placeholder || 'Select'}
        <ChevronDown
          className={`h-4 w-4 text-gray-400 absolute right-3 top-1/2 -translate-y-1/2 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>
      {open && !disabled && (
        <div className="absolute z-40 mt-2 w-full rounded-xl border border-gray-200 bg-white shadow-lg max-h-56 overflow-auto">
          {options.map((opt) => (
            <button
              type="button"
              key={opt.value}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 ${
                opt.value === value ? 'text-[#105E53] font-semibold' : 'text-gray-700'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function BrandInfoSettings() {
  const navigate = useNavigate();
  const { vendorProfile, updateProfile, isOnboarding, brandInfoCompleted } = useVendor();
  const { user } = useAuth();
  const initialized = useRef(false);

  const [phone, setPhone] = useState('');
  const [email, setEmail] = useState('');
  const [secondaryContacts, setSecondaryContacts] = useState<Contact[]>([]);
  const [description, setDescription] = useState('');
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [shipping, setShipping] = useState<Address>({ country: '', address: '' });
  const [returning, setReturning] = useState<Address>({ country: '', address: '' });
  const [sameAsShipping, setSameAsShipping] = useState(false);
  const [openDays, setOpenDays] = useState<Record<string, boolean>>({
    MON: false, TUE: false, WED: false, THU: false, FRI: false, SAT: false, SUN: false,
  });
  const [openHour, setOpenHour] = useState('');
  const [closeHour, setCloseHour] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState('');
  const [toastVisible, setToastVisible] = useState(false);
  const [toastType, setToastType] = useState<'success' | 'error'>('success');
  const [activeTab, setActiveTab] = useState<'brand' | 'payout' | 'security'>('brand');
  const [defaultPayout, setDefaultPayout] = useState('');
  const [tin, setTin] = useState('');
  const [autoTimeline, setAutoTimeline] = useState('');
  const [accountType, setAccountType] = useState('');
  const [bankName, setBankName] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [accountHolder, setAccountHolder] = useState('');
  const [paymentMethodsList, setPaymentMethodsList] = useState<PaymentMethod[]>([]);
  const [loadingPaymentMethods, setLoadingPaymentMethods] = useState(false);
  const countryOptions = useMemo<SelectOption[]>(() => [{ label: 'Nigeria', value: 'Nigeria' }], []);
  const timeOptions = useMemo<SelectOption[]>(
    () =>
      Array.from({ length: 24 }, (_, i) => {
        const hour = i.toString().padStart(2, '0');
        return { label: `${hour}:00`, value: `${hour}:00` };
      }),
    []
  );
  const paymentMethods = useMemo<SelectOption[]>(() => {
    return paymentMethodsList.map(pm => ({
      label: `${pm.bank_name} (${pm.masked_account})`,
      value: pm.id
    }));
  }, [paymentMethodsList]);
  const payoutFrequencies = useMemo<SelectOption[]>(() => [
    { label: 'Monthly', value: 'Monthly' },
    { label: 'Weekly', value: 'Weekly' },
    { label: 'Daily', value: 'Daily' },
  ], []);
  const accountTypes = useMemo<SelectOption[]>(() => [
    { label: 'Checking', value: 'Checking' },
    { label: 'Savings', value: 'Savings' },
  ], []);

  const nigerianBanks = useMemo<SelectOption[]>(() => [
    { label: 'Access Bank', value: 'Access Bank' },
    { label: 'Ecobank', value: 'Ecobank' },
    { label: 'Fidelity Bank', value: 'Fidelity Bank' },
    { label: 'First Bank of Nigeria', value: 'First Bank of Nigeria' },
    { label: 'Guaranty Trust Bank (GTBank)', value: 'Guaranty Trust Bank' },
    { label: 'Keystone Bank', value: 'Keystone Bank' },
    { label: 'Polaris Bank', value: 'Polaris Bank' },
    { label: 'Stanbic IBTC Bank', value: 'Stanbic IBTC Bank' },
    { label: 'Standard Chartered', value: 'Standard Chartered' },
    { label: 'Sterling Bank', value: 'Sterling Bank' },
    { label: 'Union Bank', value: 'Union Bank' },
    { label: 'United Bank for Africa (UBA)', value: 'United Bank for Africa' },
    { label: 'Unity Bank', value: 'Unity Bank' },
    { label: 'Wema Bank', value: 'Wema Bank' },
    { label: 'Zenith Bank', value: 'Zenith Bank' },
  ], []);

  // Fetch payment methods
  const fetchPaymentMethods = async () => {
    try {
      setLoadingPaymentMethods(true);
      const methods = await vendorPaymentMethodsService.list();
      setPaymentMethodsList(methods);

      // Set default payment method
      const defaultMethod = methods.find(m => m.is_default);
      if (defaultMethod) {
        setDefaultPayout(defaultMethod.id);
      }
    } catch (error: any) {
      console.error('Failed to fetch payment methods:', error);
    } finally {
      setLoadingPaymentMethods(false);
    }
  };

  // Fetch payment methods on mount
  useEffect(() => {
    if (vendorProfile) {
      fetchPaymentMethods();
    }
  }, [vendorProfile]);

  // Initialize form with existing vendor data (only once on component mount)
  useEffect(() => {
    if (!vendorProfile || initialized.current) return;

    initialized.current = true;

    // Populate phone and email from user data (available during onboarding)
    if (user) {
      setPhone(user.phone_number || vendorProfile?.business_phone || '');
      setEmail(user.email || '');
    }

    // Populate description from vendor profile (brand story from signup)
    setDescription(vendorProfile.business_description || '');

    // Populate logo
    if (vendorProfile.logo_url) {
      setLogoPreview(vendorProfile.logo_url);
    }

    // Populate shipping address
    setShipping({
      country: vendorProfile.business_address ? 'Nigeria' : '',
      address: vendorProfile.business_address || '',
    });

    // Populate returning address
    if (vendorProfile.returning_address) {
      setReturning({
        country: 'Nigeria',
        address: vendorProfile.returning_address,
      });
    }

    // Populate open days
    if (vendorProfile.open_days && Array.isArray(vendorProfile.open_days)) {
      const days: Record<string, boolean> = {
        MON: false, TUE: false, WED: false, THU: false, FRI: false, SAT: false, SUN: false,
      };
      vendorProfile.open_days.forEach((day: string) => {
        days[day] = true;
      });
      setOpenDays(days);
    }

    // Populate hours
    if (vendorProfile.open_hour) {
      setOpenHour(vendorProfile.open_hour);
    }
    if (vendorProfile.close_hour) {
      setCloseHour(vendorProfile.close_hour);
    }

    // Populate secondary contacts
    if (vendorProfile.secondary_contacts && Array.isArray(vendorProfile.secondary_contacts)) {
      setSecondaryContacts(vendorProfile.secondary_contacts);
    }

    // Note: Bank details are now managed through payment methods API
    // and populated via fetchPaymentMethods()
  }, [vendorProfile, isOnboarding, user]);

  useEffect(() => {
    if (sameAsShipping) {
      setReturning(shipping);
    }
  }, [sameAsShipping, shipping]);

  const requiredMet = useMemo(() => {
    const hasOpenDay = Object.values(openDays).some(Boolean);
    return !!phone && !!shipping.address && hasOpenDay && !!openHour && !!closeHour;
  }, [phone, shipping.address, openDays, openHour, closeHour]);

  const toggleDay = (day: string) => {
    setOpenDays((prev) => ({ ...prev, [day]: !prev[day] }));
  };

  const handleLogoUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setLogoPreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    if (saving || !requiredMet) return;
    setSaving(true);
    setMessage(null);
    try {
      const selectedDays = Object.entries(openDays)
        .filter(([_, selected]) => selected)
        .map(([day]) => day);

      const brandInfoData: BrandInfoData = {
        business_phone: phone,
        email: email || undefined,
        business_description: description || undefined,
        logo_url: logoPreview || undefined,
        shipping_country: shipping.country || undefined,
        shipping_address: shipping.address,
        returning_country: returning.country || undefined,
        returning_address: returning.address || undefined,
        open_days: selectedDays,
        open_hour: openHour,
        close_hour: closeHour,
      };

      const updatedProfile = await vendorService.saveBrandInfo(brandInfoData);
      updateProfile(updatedProfile);
      setMessage('Brand info saved successfully!');

      // Switch to payout tab if brand info is newly completed and payout is not
      if (updatedProfile.brand_info_completed && !updatedProfile.payout_info_completed) {
        setTimeout(() => {
          setActiveTab('payout');
          setMessage('Please complete your payout information to finish onboarding.');
        }, 1000);
      }
    } catch (err: any) {
      setMessage(err?.message || 'Failed to save brand info.');
    } finally {
      setSaving(false);
    }
  };

  const handleSavePayout = async (event: React.FormEvent) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setMessage(null);
    try {
      // Create payment method via new API
      if (bankName && accountNumber && accountHolder) {
        const paymentMethodData: PaymentMethodCreate = {
          account_type: accountType || undefined,
          bank_name: bankName,
          account_number: accountNumber,
          account_holder: accountHolder,
          tin: tin || undefined,
          is_default: false, // Don't auto-set as default
        };

        await vendorPaymentMethodsService.create(paymentMethodData);

        // Refresh payment methods list
        await fetchPaymentMethods();

        // Clear form
        setAccountType('');
        setBankName('');
        setAccountNumber('');
        setAccountHolder('');
        setTin('');
      }

      // Save TIN to vendor profile (legacy support)
      const payoutData: PayoutInfoData = {
        tin: tin || undefined,
        account_type: accountType,
        bank_name: bankName || 'N/A',
        account_number: accountNumber || '0000000000',
        account_holder: accountHolder || 'N/A',
      };

      const updatedProfile = await vendorService.savePayoutInfo(payoutData);
      updateProfile(updatedProfile);

      setMessage('Payment method added successfully!');

      // If onboarding is now complete, show success message
      if (!updatedProfile.is_onboarding) {
        setTimeout(() => {
          setMessage('Onboarding complete! You now have full access to the dashboard.');
        }, 1000);
      }
    } catch (err: any) {
      setMessage(err?.message || 'Failed to save payment info.');
    } finally {
      setSaving(false);
    }
  };

  // Show toast notification
  const showToast = (message: string, type: 'success' | 'error' = 'success') => {
    setToastMessage(message);
    setToastType(type);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 4000);
  };

  // Handle changing default payment method
  const handleDefaultPaymentChange = async (methodId: string) => {
    const previousDefault = defaultPayout; // Store previous value for rollback

    try {
      // Optimistically update UI
      setDefaultPayout(methodId);

      // Call API to persist the change
      const updatedMethod = await vendorPaymentMethodsService.setDefault(methodId);

      // Refresh list to update is_default flags
      await fetchPaymentMethods();

      // Show success toast with bank name
      showToast(
        `Default payment method updated. Your payouts will now be sent to ${updatedMethod.bank_name}.`,
        'success'
      );
    } catch (error: any) {
      // Rollback UI change on error
      setDefaultPayout(previousDefault);

      // Show error toast
      showToast(
        error?.message || 'Unable to update default payment method. Please try again.',
        'error'
      );
    }
  };

  // Handle pausing/activating store
  const handleToggleStoreStatus = async () => {
    try {
      if (vendorProfile?.store_active) {
        // Pause store
        if (!window.confirm('Are you sure you want to pause your store? Customers will not be able to see your products while the store is paused.')) {
          return;
        }
        const updatedProfile = await vendorService.pauseStore();
        updateProfile(updatedProfile);
        showToast('Store paused successfully. Your products are now hidden from customers.', 'success');
      } else {
        // Activate store
        const updatedProfile = await vendorService.activateStore();
        updateProfile(updatedProfile);
        showToast('Store activated successfully. Your products are now visible to customers.', 'success');
      }
    } catch (error: any) {
      showToast(error?.message || 'Failed to update store status', 'error');
    }
  };

  // Handle deleting store
  const handleDeleteStore = async () => {
    if (!window.confirm('Are you sure you want to delete your store? This action cannot be easily undone. All your products will be hidden and you will need to contact support to restore your store.')) {
      return;
    }

    // Double confirmation for deletion
    if (!window.confirm('Final confirmation: Delete your store permanently?')) {
      return;
    }

    try {
      const updatedProfile = await vendorService.deleteStore();
      updateProfile(updatedProfile);
      showToast('Store deleted successfully. Contact support if you need to restore it.', 'success');
    } catch (error: any) {
      showToast(error?.message || 'Failed to delete store', 'error');
    }
  };

  const disabledNav = isOnboarding && !brandInfoCompleted;

  return (
    <div className="min-h-screen bg-[#F9FAFB] flex">
      {/* Toast Notification */}
      {toastVisible && (
        <div className="fixed inset-x-0 top-0 z-50">
          <div
            className={`mx-auto max-w-[1200px] px-8 py-4 border-b flex items-center justify-between ${
              toastType === 'success'
                ? 'bg-[#105E53] text-white border-[#0d4a41]'
                : 'bg-red-600 text-white border-red-700'
            }`}
          >
            <div>
              <p className="text-[10px] uppercase tracking-[0.4em] text-white/70">
                {toastType === 'success' ? 'Payment Settings' : 'Error'}
              </p>
              <p className="text-sm font-semibold tracking-wide">{toastMessage}</p>
            </div>
            <button
              type="button"
              onClick={() => setToastVisible(false)}
              className="text-[10px] uppercase tracking-[0.4em] text-white/70 hover:text-white transition"
            >
              Close
            </button>
          </div>
        </div>
      )}

      <VendorSidebar
        disableMain={disabledNav}
        activePrimary="settings"
        activeSettings="brand-info"
        pendingOrders={0}
        completedOrders={0}
        onViewStore={() => navigate(ROUTES.PRODUCTS)}
      />

      <main className="flex-1 p-8">
        <div>

          {/* Main Content */}
          <section className="space-y-6">
            <div className="flex items-center justify-between">
              <h1 className="text-2xl font-display text-[#105E53]">Settings</h1>
              <div className="flex items-center gap-3">
                <div className="hidden sm:flex items-center gap-2 px-4 py-2 rounded-xl border border-gray-200 bg-white">
                  <span className="text-gray-400 text-sm">🔍</span>
                  <input
                    type="text"
                    placeholder="Search"
                    className="w-48 sm:w-64 border-none outline-none text-sm text-gray-700"
                  />
                </div>
                <button type="button" className="h-10 w-10 rounded-xl border border-gray-200 bg-white text-gray-500">⇅</button>
                <button type="button" className="h-10 w-10 rounded-xl border border-gray-200 bg-white text-gray-500">☰</button>
              </div>
            </div>

            <div className="rounded-3xl overflow-visible relative">
              {/* Banner + logo wrapper */}
              <div className="relative overflow-visible">
                <div className="h-[260px] rounded-3xl overflow-hidden relative">
                  <img
                    src="/images/profilebanner.jpg"
                    alt="Brand banner"
                    className="w-full h-full object-cover"
                  />
                  <button
                    type="button"
                    className="absolute left-4 top-4 h-8 w-8 rounded-full border border-white/60 bg-white/70 flex items-center justify-center text-gray-600"
                  >
                    i
                  </button>
                  <button
                    type="button"
                    className="absolute right-4 bottom-4 px-4 py-2 text-xs font-ui rounded-lg bg-white text-[#105E53] border border-[#105E53] hover:bg-[#105E53] hover:text-white transition"
                  >
                    Edit Banner Image
                  </button>
                </div>

                {/* Logo positioned at bottom center, overlapping banner */}
                <div className="absolute left-1/2 -bottom-10 -translate-x-1/2 w-28 h-28 rounded-2xl bg-white flex items-center justify-center shadow-xl z-30 border-4 border-white">
                  {logoPreview ? (
                    <img src={logoPreview} alt="Logo" className="w-24 h-24 rounded-xl object-cover" />
                  ) : (
                    <span className="text-4xl font-display text-[#105E53]">S</span>
                  )}
                </div>
              </div>

              <div className="p-6 pt-20 space-y-6 bg-transparent overflow-visible">
                <div className="grid grid-cols-[220px_minmax(0,1fr)] gap-12 mt-6">
                  {/* Tabs */}
                  <div className="space-y-3 text-sm font-ui">
                    {[
                      { key: 'brand', label: 'Brand Info' },
                      { key: 'payout', label: 'Payout Information' },
                      { key: 'security', label: 'Security' },
                    ].map((tab) => (
                      <button
                        key={tab.key}
                        type="button"
                        onClick={() => setActiveTab(tab.key as typeof activeTab)}
                        className={`block text-left ${
                          activeTab === tab.key
                            ? 'text-[#222] font-semibold'
                            : 'text-gray-500 font-normal'
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {/* Tab Content */}
                  <div className="space-y-6">
                    {activeTab === 'brand' && (
                      <>
                        <h2 className="text-xl font-display text-[#222]">Brand Info</h2>

                        <form className="space-y-6" onSubmit={handleSave}>
                          {/* Brand name (read-only) */}
                          <div className="space-y-2">
                            <label className="text-sm font-ui text-gray-700">Brand Name</label>
                            <input
                              type="text"
                              value={vendorProfile?.business_name || 'Your Brand Name'}
                              disabled
                              className="w-full border border-gray-200 rounded-xl px-3 py-3 bg-gray-50 text-gray-600"
                            />
                            <p className="text-xs text-gray-500 font-ui">
                              The brand name cannot be changed without contacting the Support team.
                            </p>
                          </div>

                          {/* Contact */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Phone Number</label>
                              <input
                                type="tel"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value)}
                                placeholder="+234 800 000 0000"
                                className="w-full border border-gray-200 rounded-xl px-3 py-3 focus:outline-none focus:border-[#105E53] bg-white"
                              />
                            </div>
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Email Address</label>
                              <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                placeholder="info@yourbrand.com"
                                className="w-full border border-gray-200 rounded-xl px-3 py-3 focus:outline-none focus:border-[#105E53] bg-white"
                              />
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => setSecondaryContacts((prev) => [...prev, { phone: '', email: '' }])}
                            className="inline-flex items-center gap-2 text-sm font-ui text-[#105E53] underline"
                          >
                            + Add Second Contact
                          </button>
                          {secondaryContacts.map((contact, idx) => (
                            <div key={idx} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <input
                                type="tel"
                                placeholder="Secondary phone"
                                value={contact.phone}
                                onChange={(e) => {
                                  const updated = [...secondaryContacts];
                                  updated[idx].phone = e.target.value;
                                  setSecondaryContacts(updated);
                                }}
                                className="w-full border border-gray-200 rounded-xl px-3 py-3 focus:outline-none focus:border-[#105E53] bg-white"
                              />
                              <input
                                type="email"
                                placeholder="Secondary email"
                                value={contact.email}
                                onChange={(e) => {
                                  const updated = [...secondaryContacts];
                                  updated[idx].email = e.target.value;
                                  setSecondaryContacts(updated);
                                }}
                                className="w-full border border-gray-200 rounded-xl px-3 py-3 focus:outline-none focus:border-[#105E53] bg-white"
                              />
                            </div>
                          ))}

                          {/* Logo upload */}
                          <div className="space-y-2">
                            <label className="text-sm font-ui text-gray-700">Logo</label>
                            <label className="border border-gray-200 rounded-2xl px-6 py-10 flex flex-col items-center justify-center gap-3 text-sm text-gray-600 cursor-pointer hover:border-gray-300 transition">
                              {logoPreview ? (
                                <img src={logoPreview} alt="Logo preview" className="h-20 w-20 object-contain" />
                              ) : (
                                <>
                                  <div className="h-12 w-12 rounded-lg border border-gray-300 flex items-center justify-center text-gray-400">
                                    <ImageIcon className="h-6 w-6" />
                                  </div>
                                  <div className="text-center leading-tight">
                                    <div>Upload New Logo or</div>
                                    <div>Drag Image/SVG here</div>
                                  </div>
                                </>
                              )}
                              <input type="file" accept="image/*" className="hidden" onChange={handleLogoUpload} />
                            </label>
                          </div>

                          {/* Brand Description */}
                          <div className="space-y-2">
                            <label className="text-sm font-ui text-gray-700">Brand Description</label>
                            <textarea
                              value={description}
                              onChange={(e) => setDescription(e.target.value)}
                              placeholder="Tell customers about your brand story and what makes it special..."
                              rows={5}
                              className="w-full border border-gray-200 rounded-xl px-4 py-3 focus:outline-none focus:border-[#105E53] bg-white resize-none text-gray-700"
                            />
                            <p className="text-xs text-gray-500 font-ui">
                              This description will be displayed on your storefront.
                            </p>
                          </div>

                          {/* Shipping */}
                          <div className="grid grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)] gap-4">
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Country</label>
                              <CustomSelect
                                value={shipping.country || countryOptions[0].value}
                                onChange={(val) => setShipping((prev) => ({ ...prev, country: val }))}
                                options={countryOptions}
                                placeholder="Select country"
                              />
                            </div>
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Shipping Address</label>
                              <input
                                type="text"
                                value={shipping.address}
                                onChange={(e) => setShipping((prev) => ({ ...prev, address: e.target.value }))}
                                className="w-full border border-gray-200 rounded-xl px-3 py-3 focus:outline-none focus:border-[#105E53] bg-white"
                                placeholder="e.g., 123 Main Street, Lagos"
                              />
                            </div>
                          </div>

                          {/* Open days */}
                          <div className="space-y-2">
                            <label className="text-sm font-ui text-gray-700">Open Days</label>
                            <div className="flex flex-wrap gap-2">
                              {Object.keys(openDays).map((day) => (
                                <button
                                  key={day}
                                  type="button"
                                  onClick={() => toggleDay(day)}
                                  className={`px-4 py-2 rounded-lg text-xs font-semibold uppercase ${
                                    openDays[day]
                                      ? 'bg-[#3b3b3b] text-white'
                                      : 'bg-gray-200 text-gray-700'
                                  }`}
                                >
                                  {day}
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* Hours */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Open Hours</label>
                              <CustomSelect
                                value={openHour}
                                onChange={setOpenHour}
                                options={timeOptions}
                                placeholder="Select opening time"
                              />
                            </div>
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Closing Hours</label>
                              <CustomSelect
                                value={closeHour}
                                onChange={setCloseHour}
                                options={timeOptions}
                                placeholder="Select closing time"
                              />
                            </div>
                          </div>

                          {/* Returning */}
                          <div className="grid grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)] gap-4">
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Country</label>
                              <CustomSelect
                                value={returning.country || countryOptions[0].value}
                                onChange={(val) => setReturning((prev) => ({ ...prev, country: val }))}
                                options={countryOptions}
                                placeholder="Select country"
                                disabled={sameAsShipping}
                              />
                            </div>
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Returning Address</label>
                              <input
                                type="text"
                                value={returning.address}
                                onChange={(e) => setReturning((prev) => ({ ...prev, address: e.target.value }))}
                                className="w-full border border-gray-200 rounded-xl px-3 py-3 focus:outline-none focus:border-[#105E53] bg-white disabled:bg-gray-50 disabled:cursor-not-allowed"
                                placeholder="e.g., 123 Main Street, Lagos"
                                disabled={sameAsShipping}
                              />
                            </div>
                          </div>

                          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
                            <input
                              type="checkbox"
                              checked={sameAsShipping}
                              onChange={(e) => setSameAsShipping(e.target.checked)}
                              className="peer sr-only"
                            />
                            <span className="flex h-5 w-5 items-center justify-center rounded-full border border-gray-400 peer-checked:bg-[#105E53] peer-checked:border-[#105E53] transition">
                              <Check className="h-3 w-3 text-white opacity-0 peer-checked:opacity-100" />
                            </span>
                            Same as Shipping Address
                          </label>

                          {message && (
                            <div className="text-sm text-[#105E53]">{message}</div>
                          )}

                          {!requiredMet && (
                            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg p-3">
                              Please fill all required fields: Phone, Shipping Address, Open Days, and Hours
                            </div>
                          )}

                          <button
                            type="submit"
                            disabled={saving || !requiredMet}
                            className="w-full py-3 rounded-full bg-[#105E53] text-white font-ui text-sm tracking-[0.12em] hover:bg-[#0c4c45] transition disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            {saving ? 'Saving…' : 'Save Changes'}
                          </button>
                        </form>
                      </>
                    )}

                    {activeTab === 'payout' && (
                      <form className="space-y-6" onSubmit={handleSavePayout}>
                        <h2 className="text-xl font-display text-[#222]">Payout Information</h2>

                        <div className="space-y-2">
                          <label className="text-sm font-ui text-gray-700">Default Payment Method</label>
                          <CustomSelect
                            value={defaultPayout}
                            onChange={handleDefaultPaymentChange}
                            options={paymentMethods}
                            placeholder={loadingPaymentMethods ? "Loading..." : paymentMethods.length === 0 ? "No payment methods added" : "Select payment method"}
                            disabled={loadingPaymentMethods || paymentMethods.length === 0}
                          />
                          {paymentMethods.length === 0 && !loadingPaymentMethods && (
                            <p className="text-xs text-gray-500 font-ui">Add a payment method below to choose a default.</p>
                          )}
                        </div>

                        <div className="space-y-2">
                          <label className="text-sm font-ui text-gray-700">Taxpayer Identification Number (TIN)</label>
                          <input
                            type="text"
                            value={tin}
                            onChange={(e) => setTin(e.target.value)}
                            className="w-full border border-gray-200 rounded-xl px-4 py-3 bg-white text-gray-700 focus:outline-none focus:border-[#105E53]"
                            placeholder="e.g. 12-3456789"
                          />
                        </div>

                        <div className="space-y-1">
                          <label className="text-sm font-ui text-gray-700">Auto Payment Timeline</label>
                          <p className="text-xs text-gray-500 font-ui">Next Payment: Not set</p>
                          <CustomSelect
                            value={autoTimeline}
                            onChange={setAutoTimeline}
                            options={payoutFrequencies}
                            placeholder="Select timeline"
                          />
                        </div>

                        <div className="rounded-2xl border border-gray-200 bg-white/70 p-5 space-y-4">
                          <h3 className="text-sm font-semibold text-gray-700">Add Payment Method</h3>
                          <p className="text-xs text-gray-500">Fill in the details below to add a new bank account</p>
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Account Type</label>
                              <CustomSelect
                                value={accountType}
                                onChange={setAccountType}
                                options={accountTypes}
                                placeholder="Select account type"
                              />
                            </div>
                            <div className="space-y-2">
                              <label className="text-sm font-ui text-gray-700">Bank Name</label>
                              <CustomSelect
                                value={bankName}
                                onChange={setBankName}
                                options={nigerianBanks}
                                placeholder="Select bank"
                              />
                            </div>
                          </div>

                          <div className="space-y-2">
                            <label className="text-sm font-ui text-gray-700">Account Number</label>
                            <input
                              type="text"
                              value={accountNumber}
                              onChange={(e) => setAccountNumber(e.target.value)}
                              placeholder="Enter your account number"
                              className="w-full border border-gray-200 rounded-xl px-4 py-3 bg-white text-gray-700 focus:outline-none focus:border-[#105E53]"
                            />
                          </div>

                          <div className="space-y-2">
                            <label className="text-sm font-ui text-gray-700">Account Name</label>
                            <div className="relative">
                              <input
                                type="text"
                                value={accountHolder}
                                onChange={(e) => setAccountHolder(e.target.value)}
                                placeholder="Account holder name"
                                className="w-full border border-gray-200 rounded-xl px-4 py-3 pr-10 bg-white text-gray-700 focus:outline-none focus:border-[#105E53]"
                              />
                              {accountHolder && <Check className="h-4 w-4 text-[#105E53] absolute right-3 top-1/2 -translate-y-1/2" />}
                            </div>
                          </div>

                          <button
                            type="submit"
                            disabled={saving || !bankName || !accountNumber || !accountHolder}
                            className="w-full py-3 rounded-full bg-[#105E53] text-white font-ui text-sm tracking-[0.08em] hover:bg-[#0c4c45] transition disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            {saving ? 'Adding…' : 'Add Payment Method'}
                          </button>
                        </div>

                        {message && (
                          <div className="text-sm text-[#105E53]">{message}</div>
                        )}
                      </form>
                    )}

                    {activeTab === 'security' && (
                      <div className="space-y-6">
                        <h2 className="text-xl font-display text-[#222]">Store Status</h2>

                        <div className="space-y-4">
                          <div>
                            <h3 className="text-sm font-semibold text-gray-800">
                              {vendorProfile?.store_active ? 'Temporarily Pause Store' : 'Activate Store'}
                            </h3>
                            <p className="text-sm text-gray-600 mt-1">
                              {vendorProfile?.store_active
                                ? 'Pausing your store will hide all your products from customers. You can reactivate it anytime.'
                                : 'Activating your store will make all your products visible to customers again.'}
                            </p>
                            <button
                              type="button"
                              onClick={handleToggleStoreStatus}
                              disabled={!!vendorProfile?.store_deleted_at}
                              className={`mt-3 inline-flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed ${
                                vendorProfile?.store_active
                                  ? 'bg-[#F4B000] text-white hover:bg-[#d99b00]'
                                  : 'bg-green-600 text-white hover:bg-green-700'
                              }`}
                            >
                              <PauseCircle className="h-5 w-5" />
                              {vendorProfile?.store_active ? 'Pause Store' : 'Activate Store'}
                            </button>
                            {vendorProfile?.store_paused_at && (
                              <p className="text-xs text-gray-500 mt-2">
                                Store paused on {new Date(vendorProfile.store_paused_at).toLocaleDateString()}
                              </p>
                            )}
                          </div>

                          <div className="pt-2">
                            <h3 className="text-sm font-semibold text-gray-800">Delete Store</h3>
                            <p className="text-sm text-gray-600 mt-1">
                              Permanently delete your store. This will hide all your products and you'll need to contact support to restore it.
                            </p>
                            <button
                              type="button"
                              onClick={handleDeleteStore}
                              disabled={!!vendorProfile?.store_deleted_at}
                              className="mt-3 inline-flex items-center gap-2 rounded-xl bg-[#D92D20] text-white px-4 py-3 text-sm font-semibold hover:bg-[#b8241a] transition disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              <Trash2 className="h-5 w-5" />
                              Delete Store
                            </button>
                            {vendorProfile?.store_deleted_at && (
                              <p className="text-xs text-red-600 mt-2 font-semibold">
                                Store deleted on {new Date(vendorProfile.store_deleted_at).toLocaleDateString()}. Contact support to restore.
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
