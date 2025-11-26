import { useMemo, useState, useEffect, useRef } from 'react';
import { ChevronDown } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { useAuth } from '../../context/AuthContext';
import { userService } from '../../services/userService';

const MENU_ITEMS = [
  { label: 'Account Details', route: ROUTES.PROFILE, active: false },
  { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
  { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
  { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
  { label: 'Return', route: ROUTES.PROFILE_RETURNS },
  { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
  { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
  { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
  { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
  { label: 'Sign Out' },
];

export default function ProfileEdit() {
  const navigate = useNavigate();
  const { user, logout, isAuthenticated, refreshUser } = useAuth();
  const [showToast, setShowToast] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
    gender: '',
    day: '',
    month: '',
    year: '',
  });

  // Redirect if not authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      navigate(ROUTES.LOGIN, { replace: true });
      return;
    }

    if (user) {
      // Parse user data
      const nameParts = user.full_name.split(' ');
      const firstName = nameParts[0] || '';
      const lastName = nameParts.slice(1).join(' ') || '';

      // Parse date of birth if it exists
      let day = '';
      let month = '';
      let year = '';
      if (user.date_of_birth) {
        const date = new Date(`${user.date_of_birth}T00:00:00Z`);
        day = String(date.getUTCDate()).padStart(2, '0');
        month = date.toLocaleDateString('en-US', { month: 'long', timeZone: 'UTC' });
        year = String(date.getUTCFullYear());
      }

      setFormData({
        firstName,
        lastName,
        email: user.email,
        phone: user.phone_number || '',
        gender: user.gender || '',
        day,
        month,
        year,
      });
    }
  }, [user, isAuthenticated, navigate]);

  const dayOptions = useMemo(() => Array.from({ length: 31 }, (_, i) => String(i + 1).padStart(2, '0')), []);
  const yearOptions = useMemo(() => Array.from({ length: 50 }, (_, i) => String(1975 + i)), []);

  const handleCancel = () => navigate(ROUTES.PROFILE);

  const handleSignOut = async () => {
    await logout();
    navigate(ROUTES.LOGIN, { replace: true });
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSaving(true);

    try {
      const formElement = event.currentTarget;
      const formDataObj = new FormData(formElement);

      const firstName = formDataObj.get('firstName') as string;
      const lastName = formDataObj.get('lastName') as string;
      const phone = formDataObj.get('phone') as string;
      const gender = formDataObj.get('gender') as string;
      const day = formDataObj.get('day') as string;
      const month = formDataObj.get('month') as string;
      const year = formDataObj.get('year') as string;

      // Prepare update data
      const updateData: any = {
        full_name: `${firstName} ${lastName}`.trim(),
        phone_number: phone || null,
        gender: gender || null,
      };

      // Convert date of birth to ISO format if all parts are provided
      if (day && month && year) {
        const monthIndex = [
          'January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December'
        ].indexOf(month);

        if (monthIndex !== -1) {
          const date = new Date(Date.UTC(parseInt(year, 10), monthIndex, parseInt(day, 10)));
          updateData.date_of_birth = date.toISOString().split('T')[0];
        }
      }

      // Call API to update profile
      const updatedUser = await userService.updateProfile(updateData);

      // Update user context with new data
      if (updatedUser) {
        // Refresh user data from context
        await refreshUser();
      }

      setShowToast(true);
      setTimeout(() => {
        setShowToast(false);
        navigate(ROUTES.PROFILE);
      }, 2000);
    } catch (error: any) {
      console.error('Error updating profile:', error);
      alert(error.message || 'Failed to update profile. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  if (!user) {
    return null;
  }

  return (
    <Layout>
      {showToast && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            <p className="font-semibold">Profile updated</p>
            <p className="text-white/90">Your account details were saved successfully.</p>
          </div>
        </div>
      )}
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu
            items={MENU_ITEMS.map((item) => ({
              ...item,
              active: item.label === 'Account Details',
              onClick: item.label === 'Sign Out' ? handleSignOut : undefined,
            }))}
            onNavigate={(route) => navigate(route)}
          />

          <section className="flex-1">
            <header className="mb-8 flex items-center gap-4">
              <button
                type="button"
                onClick={handleCancel}
                className="text-primary text-xl"
                aria-label="Go back to profile"
              >
                ←
              </button>
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Account details</p>
            </header>

            <form className="space-y-6" onSubmit={handleSubmit}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <InputField
                  label="First Name"
                  name="firstName"
                  defaultValue={formData.firstName}
                  required
                />
                <InputField
                  label="Last Name"
                  name="lastName"
                  defaultValue={formData.lastName}
                  required
                />
              </div>
              <InputField
                label="Email Address"
                name="email"
                defaultValue={formData.email}
                type="email"
                disabled
              />

              <div className="space-y-3">
                <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Date of Birth</p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <BrandedSelect
                    label="Day"
                    name="day"
                    options={dayOptions}
                    defaultValue={formData.day}
                  />
                  <BrandedSelect
                    label="Month"
                    name="month"
                    options={[
                      'January',
                      'February',
                      'March',
                      'April',
                      'May',
                      'June',
                      'July',
                      'August',
                      'September',
                      'October',
                      'November',
                      'December',
                    ]}
                    defaultValue={formData.month}
                  />
                  <BrandedSelect
                    label="Year"
                    name="year"
                    options={yearOptions}
                    defaultValue={formData.year}
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                <InputField
                  label="Phone Number"
                  name="phone"
                  defaultValue={formData.phone}
                />
                <BrandedSelect
                  label="Gender"
                  name="gender"
                  options={['Male', 'Female', 'Rather not say']}
                  defaultValue={formData.gender}
                />
              </div>

              <div className="flex flex-col sm:flex-row gap-4 pt-4">
                <button
                  type="button"
                  onClick={handleCancel}
                  className="flex-1 border border-primary text-primary font-semibold py-3 rounded-sm hover:bg-primary hover:text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className={`flex-1 py-3 rounded-sm font-semibold transition ${
                    isSaving
                      ? 'bg-primary/60 text-white cursor-wait'
                      : 'bg-primary text-white hover:bg-primary-dark'
                  }`}
                >
                  {isSaving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </Layout>
  );
}

interface InputFieldProps {
  label: string;
  name: string;
  defaultValue?: string;
  type?: string;
  disabled?: boolean;
  required?: boolean;
}

function InputField({ label, name, defaultValue, type = 'text', disabled = false, required = false }: InputFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <input
        type={type}
        name={name}
        defaultValue={defaultValue}
        disabled={disabled}
        required={required}
        className={`w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary ${
          disabled ? 'bg-gray-100 text-gray-500 cursor-not-allowed' : ''
        }`}
      />
    </div>
  );
}

interface BrandedSelectProps {
  label: string;
  name: string;
  options: string[];
  defaultValue?: string;
}

function BrandedSelect({ label, name, options, defaultValue = '' }: BrandedSelectProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(defaultValue);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setValue(defaultValue || '');
  }, [defaultValue]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const displayValue = value || 'Select...';

  return (
    <div className="space-y-1" ref={containerRef}>
      <p className="text-[11px] uppercase tracking-[0.3em] text-gray-500">{label}</p>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          className={`w-full rounded-sm border px-3 py-2.5 text-sm flex items-center justify-between transition focus:outline-none focus:ring-1 focus:ring-primary/10 ${
            open ? 'border-primary' : 'border-gray-200 hover:border-primary/60'
          }`}
        >
          <span className={value ? 'text-gray-900' : 'text-gray-400'}>{displayValue}</span>
          <ChevronDown className={`h-4 w-4 text-primary transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        <input type="hidden" name={name} value={value} />
        {open && (
          <div className="absolute z-20 mt-1 w-full rounded-sm border border-gray-200 bg-white shadow-xl">
            <button
              type="button"
              onClick={() => {
                setValue('');
                setOpen(false);
              }}
              className="w-full text-left px-4 py-2 text-sm text-gray-500 hover:bg-gray-50"
            >
              Select...
            </button>
            <div className="max-h-56 overflow-y-auto">
              {options.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => {
                    setValue(option);
                    setOpen(false);
                  }}
                  className={`w-full text-left px-4 py-2 text-sm transition ${
                    option === value ? 'bg-primary/10 text-primary font-semibold' : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
