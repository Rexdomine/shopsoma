import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { subscribeToNewsletter } from '../../services/newsletterService';
import { useAuth } from '../../context/AuthContext';

export default function ProfileNewsletter() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [form, setForm] = useState({
    firstName: '',
    lastName: '',
    email: '',
    consent: true,
  });
  const [toast, setToast] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (user) {
      const nameParts = user.full_name?.split(' ') || [];
      setForm((prev) => ({
        ...prev,
        firstName: nameParts[0] || '',
        lastName: nameParts.slice(1).join(' ') || '',
        email: user.email || '',
      }));
    }
  }, [user]);

  const menuItems = [
    { label: 'Account Details', route: ROUTES.PROFILE },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
    { label: 'Return', route: ROUTES.PROFILE_RETURNS },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER, active: true },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
    { label: 'Sign Out' },
  ];

  const handleChange = (field: keyof typeof form, value: string | boolean) => {
    setForm((prev) => ({ ...prev, [field]: value as never }));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');

    if (!form.email.trim()) {
      setError('Email address is required');
      return;
    }

    setSubmitting(true);
    try {
      await subscribeToNewsletter({
        email: form.email.trim(),
        firstName: form.firstName.trim() || undefined,
        lastName: form.lastName.trim() || undefined,
        consent: form.consent,
      });

      setToast(true);
      setTimeout(() => setToast(false), 3500);
    } catch (err: any) {
      const message = err?.response?.data?.detail || 'Failed to update subscription. Please try again.';
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Layout>
      {toast && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            <p className="font-semibold uppercase tracking-[0.3em]">Newsletter</p>
            <p className="text-white/90">Subscription updated successfully</p>
          </div>
        </div>
      )}
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />
          <section className="flex-1 max-w-3xl">
            <header className="mb-8">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Newsletter</p>
              <p className="text-sm text-gray-600 mt-3">
                Sign up for our newsletter and stay up-to-date with the latest trends, new arrivals, exclusive offers, special
                events, promotions, and sale notifications delivered directly to your inbox.
              </p>
            </header>
            <form onSubmit={handleSubmit} className="space-y-5">
              <InputField
                label="First Name"
                value={form.firstName}
                onChange={(value) => handleChange('firstName', value)}
              />
              <InputField
                label="Last Name"
                value={form.lastName}
                onChange={(value) => handleChange('lastName', value)}
              />
              <InputField label="Email Address" value={form.email} onChange={(value) => handleChange('email', value)} type="email" />
              <label className="flex items-start gap-3 text-xs text-gray-600">
                <input
                  type="checkbox"
                  checked={form.consent}
                  onChange={(event) => handleChange('consent', event.target.checked)}
                  className="mt-1 h-4 w-4 border-gray-400"
                />
                <span>
                  I have reviewed and accepted the <button type="button" className="text-primary underline">Privacy Policy</button>, and I
                  consent to the processing of my personal data for the purpose of receiving commercial communications and promotions via
                  newsletter from SHOPSOMA.
                </span>
              </label>
              <button
                type="submit"
                disabled={submitting}
                className="w-full sm:w-auto px-8 py-3 bg-primary text-white rounded-sm text-xs font-semibold uppercase tracking-[0.3em] hover:bg-primary-dark transition disabled:opacity-60"
              >
                {submitting ? 'Saving...' : 'Subscribe Now'}
              </button>
              {error && <p className="text-sm text-red-600">{error}</p>}
            </form>
          </section>
        </div>
      </div>
    </Layout>
  );
}

interface InputFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}

function InputField({ label, value, onChange, type = 'text' }: InputFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary"
      />
    </div>
  );
}
