import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { userService } from '../../services/userService';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';

const MENU_ITEMS = [
  { label: 'Account Details', route: ROUTES.PROFILE },
  { label: 'Password', route: ROUTES.PROFILE_PASSWORD, active: true },
  { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
  { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
  { label: 'Return', route: ROUTES.PROFILE_RETURNS },
  { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
  { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
  { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
  { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
  { label: 'Sign Out' },
];

export default function ProfilePassword() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [showToast, setShowToast] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState('');
  const [formData, setFormData] = useState({
    current_password: '',
    new_password: '',
    confirm_password: '',
  });

  const handleSignOut = async () => {
    await logout();
    navigate(ROUTES.HOME);
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setIsSaving(true);

    try {
      await userService.changePassword(formData);
      setShowToast(true);
      setTimeout(() => setShowToast(false), 3500);
      setShowForm(false);
      setFormData({ current_password: '', new_password: '', confirm_password: '' });
    } catch (err: any) {
      setError(err.message || 'Failed to change password');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Layout>
      {showToast && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            <p className="font-semibold">Password updated</p>
            <p className="text-white/90">Your password has been changed successfully.</p>
          </div>
        </div>
      )}
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu
            items={MENU_ITEMS.map((item) => ({
              ...item,
              active: item.label === 'Password',
              onClick: item.label === 'Sign Out' ? handleSignOut : undefined,
            }))}
            onNavigate={(route) => navigate(route)}
          />

          <section className="flex-1">
            {showForm ? (
              <>
                <header className="mb-8 flex items-center gap-4">
                  <button
                    type="button"
                    onClick={() => {
                      setShowForm(false);
                      setError('');
                    }}
                    className="text-primary text-xl"
                    aria-label="Go back"
                  >
                    ←
                  </button>
                  <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Change password</p>
                </header>
                {error && (
                  <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 rounded-sm text-sm">
                    {error}
                  </div>
                )}
                <form onSubmit={handleSubmit} className="space-y-6 max-w-lg">
                  <PasswordField
                    label="Old password"
                    value={formData.current_password}
                    onChange={(v) => setFormData({ ...formData, current_password: v })}
                  />
                  <PasswordField
                    label="New password"
                    value={formData.new_password}
                    onChange={(v) => setFormData({ ...formData, new_password: v })}
                  />
                  <PasswordField
                    label="Confirm new password"
                    value={formData.confirm_password}
                    onChange={(v) => setFormData({ ...formData, confirm_password: v })}
                  />

                  <button
                    type="submit"
                    disabled={isSaving}
                    className={`w-full py-3 rounded-sm font-semibold tracking-wide ${
                      isSaving ? 'bg-primary/70 text-white cursor-wait' : 'bg-primary text-white hover:bg-primary-dark'
                    }`}
                  >
                    {isSaving ? 'Updating...' : 'Change Password'}
                  </button>
                </form>
              </>
            ) : (
              <>
                <header className="mb-8">
                  <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Password</p>
                </header>
                <div className="space-y-4 max-w-md">
                  <p className="text-sm text-gray-600">
                    Keep your account secure by using a strong password. You’ll be prompted to verify your identity
                    before the change is completed.
                  </p>
                  <button
                    type="button"
                    onClick={() => setShowForm(true)}
                    className="px-8 py-3 border border-primary text-primary font-semibold rounded-sm hover:bg-primary hover:text-white transition"
                  >
                    Change Password
                  </button>
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </Layout>
  );
}

interface PasswordFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
}

function PasswordField({ label, value, onChange }: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <div className="relative">
        <input
          type={visible ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary pr-10"
          required
        />
        <button
          type="button"
          onClick={() => setVisible((prev) => !prev)}
          className="absolute inset-y-0 right-2 flex items-center text-gray-400"
          aria-label={visible ? 'Hide password' : 'Show password'}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            className="w-5 h-5"
          >
            {visible ? (
              <>
                <path d="M3 3l18 18" strokeLinecap="round" strokeLinejoin="round" />
                <path
                  d="M9.9 9.9a3 3 0 104.2 4.2M6.1 6.1C4.1 7.8 2.7 10 2.1 12c1.3 3.5 4.8 6 9.9 6 1.4 0 2.7-.2 3.9-.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M17.8 17.8c2.1-1.7 3.5-3.9 4.1-5.9-1.3-3.5-4.8-6-9.9-6-.9 0-1.8.1-2.7.3"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </>
            ) : (
              <>
                <path
                  d="M2.1 12C3.4 8.5 6.9 6 12 6s8.6 2.5 9.9 6c-1.3 3.5-4.8 6-9.9 6s-8.6-2.5-9.9-6z"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <circle cx="12" cy="12" r="3" strokeLinecap="round" strokeLinejoin="round" />
              </>
            )}
          </svg>
        </button>
      </div>
    </div>
  );
}
