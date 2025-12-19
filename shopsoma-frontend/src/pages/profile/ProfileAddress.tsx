import { useMemo, useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { checkoutService, type Address, type CreateAddressData } from '../../services/checkoutService';
import { useAuth } from '../../context/AuthContext';

type Mode = 'view' | 'edit' | 'add';

interface AddressFormData {
  firstName: string;
  lastName: string;
  phone: string;
  country: string;
  state: string;
  city: string;
  addressLine1: string;
  addressLine2: string;
  postalCode: string;
  addressType: 'shipping' | 'billing';
  isDefault: boolean;
}

const emptyFormData: AddressFormData = {
  firstName: '',
  lastName: '',
  phone: '',
  country: 'Nigeria',
  state: '',
  city: '',
  addressLine1: '',
  addressLine2: '',
  postalCode: '',
  addressType: 'shipping',
  isDefault: false,
};

export default function ProfileAddress() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [mode, setMode] = useState<Mode>('view');
  const [addresses, setAddresses] = useState<Address[]>([]);
  const [selectedAddress, setSelectedAddress] = useState<Address | null>(null);
  const [formData, setFormData] = useState<AddressFormData>(emptyFormData);
  const [showToast, setShowToast] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Address | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const countries = useMemo(
    () => [
      { name: 'Nigeria', code: 'NG', flag: '🇳🇬' },
      { name: 'Ghana', code: 'GH', flag: '🇬🇭' },
      { name: 'Kenya', code: 'KE', flag: '🇰🇪' },
      { name: 'South Africa', code: 'ZA', flag: '🇿🇦' },
    ],
    []
  );

  const menuItems = [
    { label: 'Account Details', route: ROUTES.PROFILE },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS, active: true },
    { label: 'Return', route: ROUTES.PROFILE_RETURNS },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
    { label: 'Sign Out', onClick: async () => {
      await logout();
      navigate(ROUTES.LOGIN, { replace: true });
    }},
  ];

  // Load addresses on mount
  useEffect(() => {
    loadAddresses();
  }, []);

  const loadAddresses = async () => {
    setIsLoading(true);
    try {
      const data = await checkoutService.getAddresses();
      setAddresses(data.addresses);
    } catch (error) {
      console.error('Error loading addresses:', error);
      showToastMessage('Failed to load addresses');
    } finally {
      setIsLoading(false);
    }
  };

  const showToastMessage = (message: string) => {
    setToastMessage(message);
    setShowToast(true);
    setTimeout(() => setShowToast(false), 3500);
  };

  const handleAddNew = () => {
    setFormData(emptyFormData);
    setSelectedAddress(null);
    setMode('add');
  };

  const handleEdit = (address: Address) => {
    const nameParts = address.full_name.split(' ');
    setFormData({
      firstName: nameParts[0] || '',
      lastName: nameParts.slice(1).join(' ') || '',
      phone: address.phone_number,
      country: address.country,
      state: address.state,
      city: address.city,
      addressLine1: address.address_line1,
      addressLine2: address.address_line2 || '',
      postalCode: address.postal_code || '',
      addressType: address.address_type,
      isDefault: address.is_default,
    });
    setSelectedAddress(address);
    setMode('edit');
  };

  const confirmDeleteAddress = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await checkoutService.deleteAddress(deleteTarget.id);
      showToastMessage('Address deleted successfully');
      await loadAddresses();
      setDeleteTarget(null);
    } catch (error: any) {
      console.error('Error deleting address:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to delete address';
      showToastMessage(errorMessage);
      setDeleteTarget(null); // Close modal even on error
    } finally {
      setIsDeleting(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);

    try {
      const addressData: CreateAddressData = {
        full_name: `${formData.firstName} ${formData.lastName}`.trim(),
        phone_number: formData.phone,
        address_line1: formData.addressLine1,
        address_line2: formData.addressLine2 || undefined,
        city: formData.city,
        state: formData.state,
        postal_code: formData.postalCode || undefined,
        country: formData.country,
        address_type: formData.addressType,
        is_default: formData.isDefault,
      };

      if (mode === 'edit' && selectedAddress) {
        await checkoutService.updateAddress(selectedAddress.id, addressData);
        showToastMessage('Address updated successfully');
      } else {
        await checkoutService.createAddress(addressData);
        showToastMessage('Address added successfully');
      }

      await loadAddresses();
      setMode('view');
    } catch (error: any) {
      console.error('Error saving address:', error);
      showToastMessage(error.response?.data?.detail || 'Failed to save address');
    } finally {
      setIsSaving(false);
    }
  };

  const handleChange = (field: keyof AddressFormData, value: string | boolean) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const renderView = () => (
    <>
      <header className="mb-8">
        <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Addresses</p>
      </header>

      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="text-sm text-gray-500">Loading addresses...</div>
        </div>
      ) : addresses.length > 0 ? (
        <div className="space-y-6">
          {addresses.map((address) => (
            <div key={address.id} className="border border-gray-200 rounded-sm p-6">
              <div className="flex items-start justify-between mb-4">
                <div className="flex-1">
                  <p className="font-semibold text-sm text-gray-900">{address.full_name}</p>
                  <p className="text-sm text-gray-600 mt-1">{address.phone_number}</p>
                </div>
                <div className="flex gap-6 text-xs uppercase tracking-[0.3em] text-gray-500">
                  <button
                    type="button"
                    onClick={() => handleEdit(address)}
                    className="flex items-center gap-1 hover:text-primary"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(address)}
                    className="flex items-center gap-1 hover:text-red-500"
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="text-sm text-gray-700 space-y-1">
                <p>{address.address_line1}</p>
                {address.address_line2 && <p>{address.address_line2}</p>}
                <p>{address.city}, {address.state}</p>
                <p>{address.country}</p>
                {address.postal_code && <p>{address.postal_code}</p>}
              </div>

              <div className="mt-4 text-sm text-gray-500 space-y-1">
                <p className="capitalize">{address.address_type} Address</p>
                {address.is_default && (
                  <p className="text-primary font-semibold">Default Address</p>
                )}
              </div>
            </div>
          ))}

          <div className="mt-6">
            <button
              type="button"
              onClick={handleAddNew}
              className="px-8 py-3 border border-primary text-primary font-semibold rounded-sm hover:bg-primary hover:text-white transition"
            >
              Add New Address
            </button>
          </div>
        </div>
      ) : (
        <div className="max-w-md mx-auto py-12 px-6 text-center space-y-4">
          <div className="mx-auto w-12 h-12 flex items-center justify-center rounded-full bg-primary/10 text-primary text-xl">
            !
          </div>
          <div>
            <p className="text-sm font-semibold text-gray-800">No addresses yet</p>
            <p className="text-xs text-gray-500 mt-1">
              Add your first address to make checkout faster
            </p>
          </div>
          <button
            type="button"
            onClick={handleAddNew}
            className="px-6 py-3 rounded-sm bg-primary text-white text-sm font-semibold hover:bg-primary-dark transition"
          >
            Add Address
          </button>
        </div>
      )}
    </>
  );

  const renderForm = (title: string) => (
    <>
      <header className="mb-8 flex items-center gap-4">
        <button
          type="button"
          onClick={() => setMode('view')}
          className="text-primary text-xl"
          aria-label="Go back to addresses"
        >
          ←
        </button>
        <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{title}</p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-6 max-w-3xl">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <InputField
            label="First Name"
            value={formData.firstName}
            onChange={(value) => handleChange('firstName', value)}
            required
          />
          <InputField
            label="Last Name"
            value={formData.lastName}
            onChange={(value) => handleChange('lastName', value)}
            required
          />
        </div>
        <InputField
          label="Phone Number"
          value={formData.phone}
          onChange={(value) => handleChange('phone', value)}
          required
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <CountrySelect
            label="Country"
            value={formData.country}
            countries={countries}
            onChange={(value) => handleChange('country', value)}
          />
          <InputField
            label="State"
            value={formData.state}
            onChange={(value) => handleChange('state', value)}
            required
          />
        </div>
        <InputField
          label="City"
          value={formData.city}
          onChange={(value) => handleChange('city', value)}
          required
        />
        <InputField
          label="Address Line 1"
          value={formData.addressLine1}
          onChange={(value) => handleChange('addressLine1', value)}
          required
        />
        <InputField
          label="Address Line 2 (Optional)"
          value={formData.addressLine2}
          onChange={(value) => handleChange('addressLine2', value)}
        />
        <InputField
          label="Postal Code (Optional)"
          value={formData.postalCode}
          onChange={(value) => handleChange('postalCode', value)}
        />

        <div className="space-y-2">
          <div className="space-y-1">
            <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Address Type</p>
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="radio"
                  checked={formData.addressType === 'shipping'}
                  onChange={() => handleChange('addressType', 'shipping')}
                  className="w-4 h-4 text-primary focus:ring-primary"
                />
                Shipping
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                <input
                  type="radio"
                  checked={formData.addressType === 'billing'}
                  onChange={() => handleChange('addressType', 'billing')}
                  className="w-4 h-4 text-primary focus:ring-primary"
                />
                Billing
              </label>
            </div>
          </div>

          <CheckboxField
            label="Set as default address"
            checked={formData.isDefault}
            onChange={(checked) => handleChange('isDefault', checked)}
          />
        </div>

        <button
          type="submit"
          disabled={isSaving}
          className="inline-flex justify-center px-8 py-3 bg-primary text-white rounded-sm font-semibold hover:bg-primary-dark transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSaving ? 'Saving...' : 'Save Address'}
        </button>
      </form>
    </>
  );

  return (
    <Layout>
      {showToast && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            {toastMessage}
          </div>
        </div>
      )}
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />
          <section className="flex-1">
            {mode === 'view' ? renderView() : renderForm(mode === 'add' ? 'Add new address' : 'Edit address')}
          </section>
        </div>
      </div>

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center p-4 z-50" onClick={() => (!isDeleting ? setDeleteTarget(null) : null)}>
          <div className="bg-white rounded-sm max-w-md w-full shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <p className="text-sm font-semibold tracking-[0.2em] text-gray-500 uppercase">Delete Address</p>
              <button type="button" className="text-gray-400 hover:text-gray-600 text-xl" onClick={() => (!isDeleting ? setDeleteTarget(null) : null)}>
                ×
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <p className="text-sm text-gray-700">
                Are you sure you want to remove <span className="font-semibold text-gray-900">{deleteTarget.full_name}&apos;s</span> address?
                This action cannot be undone.
              </p>
              <div className="text-sm text-gray-500">
                <p>{deleteTarget.address_line1}</p>
                {deleteTarget.address_line2 && <p>{deleteTarget.address_line2}</p>}
                <p>{deleteTarget.city}, {deleteTarget.state}</p>
                <p>{deleteTarget.country}</p>
              </div>
              <div className="flex flex-col sm:flex-row gap-3 pt-2">
                <button
                  type="button"
                  className="flex-1 rounded-sm border border-gray-300 py-2.5 text-sm font-semibold text-gray-700 hover:bg-gray-50"
                  onClick={() => (!isDeleting ? setDeleteTarget(null) : null)}
                  disabled={isDeleting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="flex-1 rounded-sm bg-red-600 text-white py-2.5 text-sm font-semibold hover:bg-red-700 disabled:opacity-60"
                  onClick={confirmDeleteAddress}
                  disabled={isDeleting}
                >
                  {isDeleting ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Layout>
  );
}


interface InputFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}

function InputField({ label, value, onChange, required = false }: InputFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">
        {label}
        {required && <span className="text-red-500 ml-1">*</span>}
      </p>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary"
      />
    </div>
  );
}

interface CheckboxFieldProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}

function CheckboxField({ label, checked, onChange }: CheckboxFieldProps) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 rounded border-gray-400 text-primary focus:ring-primary"
      />
      {label}
    </label>
  );
}

interface CountrySelectProps {
  label: string;
  value: string;
  countries: Array<{ name: string; code: string; flag: string }>;
  onChange: (value: string) => void;
}

function CountrySelect({ label, value, countries, onChange }: CountrySelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const selected = countries.find((country) => country.name === value) || countries[0];

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener('click', handler);
    return () => window.removeEventListener('click', handler);
  }, []);

  const handleSelect = (country: (typeof countries)[number]) => {
    onChange(country.name);
    setOpen(false);
  };

  return (
    <div className="space-y-1 relative" ref={containerRef}>
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm flex items-center justify-between focus:outline-none focus:border-primary"
      >
        <span className="flex items-center gap-2 text-gray-800">
          <span>{selected.flag}</span>
          {selected.name}
        </span>
        <span className="text-gray-400 text-xs">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="absolute z-20 mt-2 bg-white border border-gray-200 rounded-sm shadow-lg max-h-56 overflow-auto min-w-[220px] w-[90%]">
          {countries.map((country) => (
            <button
              type="button"
              key={country.code}
              onClick={() => handleSelect(country)}
              className={`w-full text-left px-3 py-2 text-sm flex items-center gap-2 hover:bg-primary/10 ${
                country.name === selected.name ? 'text-primary font-semibold' : 'text-gray-700'
              }`}
            >
              <span>{country.flag}</span>
              {country.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
