import { useState, useEffect } from 'react';
import { CreditCard, ExternalLink, Loader2, CheckCircle, Shield, Lock, RefreshCw, X } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { useAuth } from '../../context/AuthContext';
import { paymentService } from '../../services/paymentService';

export default function ProfilePayments() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [paystackLoading, setPaystackLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Check for success/error messages in URL params
  useEffect(() => {
    const paystackSuccess = searchParams.get('paystack');
    const stripeSuccess = searchParams.get('stripe');

    if (paystackSuccess === 'success') {
      setSuccessMessage('Payment method successfully added to Paystack!');
      // Clean up URL
      searchParams.delete('paystack');
      setSearchParams(searchParams, { replace: true });
    } else if (stripeSuccess === 'success') {
      setSuccessMessage('Payment method successfully updated in Stripe!');
      // Clean up URL
      searchParams.delete('stripe');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const handleSignOut = async () => {
    await logout();
    navigate(ROUTES.LOGIN);
  };

  const menuItems = [
    { label: 'My Details', route: ROUTES.PROFILE_EDIT },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
    { label: 'My Orders', route: ROUTES.PROFILE_ORDERS },
    { label: 'Returns', route: ROUTES.PROFILE_RETURNS },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS, active: true },
    { label: 'Sign Out', onClick: handleSignOut },
  ];

  const handleManagePaystack = async () => {
    try {
      setPaystackLoading(true);
      setError(null);
      setSuccessMessage(null);
      const { url } = await paymentService.getPaystackCustomerPortalUrl();
      window.location.href = url; // Redirect to Paystack portal
    } catch (err: any) {
      console.error('Error opening Paystack portal:', err);
      setError(err?.response?.data?.detail || 'Failed to open Paystack portal. Please try again.');
    } finally {
      setPaystackLoading(false);
    }
  };

  return (
    <Layout>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="flex flex-col lg:flex-row gap-8 lg:gap-12">
          {/* Sidebar Menu */}
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />

          {/* Main Content */}
          <div className="flex-1">
            <div className="mb-8">
              <div className="rounded-md border border-gray-200 bg-white/95 p-6 shadow-sm">
                <p className="text-xs uppercase tracking-[0.4em] text-gray-400 mb-2">Manage Payments</p>
                <h1 className="text-3xl font-display font-bold text-dark mb-3">Payment Methods</h1>
                <p className="text-sm text-gray-600 max-w-2xl">
                  Save trusted cards with our payment partners for seamless future checkouts. We never store your full card details—everything is handled through secure provider vaults.
                </p>
              </div>
            </div>

            {/* Success Message */}
            {successMessage && (
              <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-sm flex items-start gap-3">
                <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm text-green-700">{successMessage}</p>
                </div>
                <button
                  onClick={() => setSuccessMessage(null)}
                  className="text-green-600 hover:text-green-700"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-sm flex items-start gap-3">
                <div className="flex-1">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
                <button
                  onClick={() => setError(null)}
                  className="text-red-600 hover:text-red-700"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}

            {/* Payment Providers */}
            <div className="space-y-5">
              {/* Paystack Card */}
              <div className="rounded-md border border-gray-200 bg-white shadow-sm transition hover:border-primary/30">
                <div className="rounded-t-md bg-gradient-to-r from-primary/5 via-white to-white px-6 py-4">
                  <p className="text-[11px] uppercase tracking-[0.4em] text-gray-400">Preferred for NG & GH Payments</p>
                  <h3 className="text-xl font-semibold text-dark">Paystack</h3>
                </div>
                <div className="px-6 py-5 flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-md bg-white flex items-center justify-center shadow-inner">
                      <CreditCard className="w-6 h-6 text-primary" />
                    </div>
                    <p className="text-sm text-gray-600 max-w-xl">
                      Save and manage your cards with Paystack for faster checkout across West Africa.
                    </p>
                  </div>
                  <button
                    onClick={handleManagePaystack}
                    disabled={paystackLoading}
                    className="inline-flex items-center gap-2 rounded-sm px-5 py-2.5 text-sm font-semibold text-white transition disabled:opacity-50 disabled:cursor-not-allowed bg-primary hover:bg-primary-dark"
                  >
                    {paystackLoading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Opening...
                      </>
                    ) : (
                      <>
                        Manage Paystack Cards
                        <ExternalLink className="w-4 h-4" />
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Stripe Link Info */}
              <div className="rounded-md border border-gray-200 bg-white shadow-sm">
                <div className="rounded-t-md bg-gradient-to-r from-blue-50 via-white to-white px-6 py-4">
                  <p className="text-[11px] uppercase tracking-[0.4em] text-gray-400">International Coverage</p>
                  <h3 className="text-xl font-semibold text-dark">Stripe Link</h3>
                </div>
                <div className="px-6 py-5 space-y-3">
                  <div className="flex items-start gap-4">
                    <div className="w-12 h-12 rounded-md bg-white flex items-center justify-center shadow-inner">
                      <CreditCard className="w-6 h-6 text-primary" />
                    </div>
                    <div className="text-sm text-gray-600 space-y-2">
                      <p>
                        Use Link at checkout to securely save your card once and reuse it everywhere Stripe is enabled across Shopsoma. It’s the fastest way to reuse cards without leaving the checkout flow.
                      </p>
                      <ul className="list-disc pl-5 text-gray-500 space-y-1">
                        <li>Add items to your Shopping Bag and proceed to checkout.</li>
                        <li>Select <strong>“Secure, fast checkout with Link”</strong> under Card Details.</li>
                        <li>Link remembers your card for future purchases automatically.</li>
                      </ul>
                      <p className="text-xs text-gray-500">
                        Tip: You can manage Link-saved cards directly within the Link flow during checkout.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Info Section */}
            <div className="mt-10 rounded-lg border border-gray-200 bg-white/70 p-6 shadow-sm">
              <div className="flex items-center gap-3 mb-4">
                <div className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Shield className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.4em] text-gray-400">Security & Privacy</p>
                  <h4 className="text-lg font-semibold text-dark">About Payment Management</h4>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                {[
                  { icon: Lock, text: 'Card numbers are never stored on Shopsoma; our processors vault and tokenise every detail.' },
                  { icon: CreditCard, text: 'Add or remove cards anytime and your preferred payment follows you through checkout.' },
                  { icon: RefreshCw, text: 'Update expiry dates instantly without re-entering your full card when banks issue replacements.' },
                ].map((item) => (
                  <div key={item.text} className="flex items-start gap-3 text-sm text-gray-600">
                    <item.icon className="w-4 h-4 text-primary mt-1" />
                    <p>{item.text}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
