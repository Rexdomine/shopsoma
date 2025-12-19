import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import api from '../../services/api';

export default function Profile() {
  const navigate = useNavigate();
  const { user, logout, isAuthenticated } = useAuth();
  const [isResending, setIsResending] = useState(false);
  const [resendMessage, setResendMessage] = useState('');

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      navigate(ROUTES.LOGIN, { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleResendVerification = async () => {
    setIsResending(true);
    setResendMessage('');
    try {
      await api.post('/auth/resend-verification');
      setResendMessage('Verification email sent! Please check your inbox.');
    } catch (error: any) {
      setResendMessage(error.response?.data?.detail || 'Failed to send verification email. Please try again.');
    } finally {
      setIsResending(false);
    }
  };

  const handleSignOut = async () => {
    await logout();
    // Navigate to login page - logout has already cleared all state
    navigate(ROUTES.LOGIN, { replace: true });
  };

  const menuItems = [
    { label: 'Account Details', route: ROUTES.PROFILE, active: true },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
    { label: 'Return', route: ROUTES.PROFILE_RETURNS },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
    { label: 'Sign Out', onClick: handleSignOut },
  ];

  if (!user) {
    return null;
  }

  // Split full name into first and last name
  const nameParts = user.full_name.split(' ');
  const firstName = nameParts[0] || '';
  const lastName = nameParts.slice(1).join(' ') || '';
  return (
    <Layout>
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />

          <section className="flex-1">
            <header className="mb-8">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Account details</p>
            </header>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-16 gap-y-4 text-sm text-gray-700">
              <ProfileField label="First Name" value={firstName} />
              <ProfileField label="Last Name" value={lastName} />
              <ProfileField label="Email Address" value={user.email} />
              <ProfileField label="Phone Number" value={user.phone_number || 'Not provided'} />
              <ProfileField
                label="Date of Birth"
                value={formatDateOfBirth(user.date_of_birth)}
              />
              <ProfileField label="Gender" value={user.gender || 'Not provided'} />
              <ProfileField label="Account Type" value={user.role.charAt(0).toUpperCase() + user.role.slice(1)} />
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Email Verified</p>
                <div className="flex items-center gap-3">
                  <p className="text-sm text-gray-800">{user.email_verified ? 'Yes' : 'No'}</p>
                  {!user.email_verified && (
                    <button
                      onClick={handleResendVerification}
                      disabled={isResending}
                      className="text-xs text-primary hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isResending ? 'Sending...' : 'Resend'}
                    </button>
                  )}
                </div>
                {resendMessage && (
                  <p className={`text-xs mt-1 ${resendMessage.includes('sent') ? 'text-green-600' : 'text-red-600'}`}>
                    {resendMessage}
                  </p>
                )}
              </div>
              <ProfileField label="Password" value="********" />
            </div>

            <div className="mt-10">
              <button
                type="button"
                onClick={() => navigate(ROUTES.PROFILE_EDIT)}
                className="px-8 py-3 border border-primary text-primary font-semibold rounded-sm hover:bg-primary hover:text-white transition"
              >
                Edit Profile
              </button>
            </div>
          </section>
        </div>
      </div>
    </Layout>
  );
}

interface ProfileFieldProps {
  label: string;
  value: string;
}

function ProfileField({ label, value }: ProfileFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <p className="text-sm text-gray-800">{value}</p>
    </div>
  );
}

function formatDateOfBirth(dateOfBirth?: string | null) {
  if (!dateOfBirth) return 'Not provided';
  const date = new Date(`${dateOfBirth}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return 'Not provided';
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });
}
