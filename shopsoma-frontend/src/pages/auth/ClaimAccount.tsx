import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, CheckCircle2, Mail, Eye, EyeOff } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import Newsletter from '../../components/home/Newsletter';
import { authService } from '../../services/authService';
import { ROUTES } from '../../config/constants';
import { useAuth } from '../../context/AuthContext';

export default function ClaimAccount() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();

  const token = searchParams.get('token') ?? '';
  const initialEmail = searchParams.get('email') ?? '';

  const [form, setForm] = useState({
    email: initialEmail,
    password: '',
    confirmPassword: '',
    full_name: '',
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRequestingLink, setIsRequestingLink] = useState(false);
  const [tokenInvalid, setTokenInvalid] = useState(false);
  const [isEditingEmailField, setIsEditingEmailField] = useState(!initialEmail);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  useEffect(() => {
    if (initialEmail) {
      setForm((prev) => ({ ...prev, email: initialEmail }));
      setIsEditingEmailField(false);
    }
  }, [initialEmail]);

  const tokenMissing = !token;

  const isReady = useMemo(() => {
    const hasPassword = form.password.trim().length >= 8;
    const matches = form.password && form.password === form.confirmPassword;
    const hasFullName = form.full_name.trim().length >= 2;
    return Boolean(form.email && token && hasPassword && matches && hasFullName);
  }, [form, token]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setSuccess('');

    if (!token) {
      setError('This claim link is missing a token. Request a fresh link below.');
      return;
    }

    const trimmedName = form.full_name.trim();
    if (trimmedName.length < 2) {
      setError('Full name is required to secure your account.');
      return;
    }

    if (form.password !== form.confirmPassword) {
      setError('Passwords must match.');
      return;
    }

    setIsSubmitting(true);
    try {
      await authService.claimAccount({
        email: form.email.trim(),
        password: form.password,
        token,
        full_name: trimmedName,
      });
      await refreshUser();
      setSuccess('Password set. Redirecting you to your account details…');
      setTokenInvalid(false);
      setTimeout(() => {
        navigate(ROUTES.PROFILE);
      }, 1500);
    } catch (err: any) {
      const message = err?.message || 'Unable to claim account right now.';
      if (message.toLowerCase().includes('token')) {
        setTokenInvalid(true);
      }
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResendLink = async () => {
    if (!form.email) {
      setError('Provide your email to request a new link.');
      return;
    }
    setError('');
    setSuccess('');
    setIsRequestingLink(true);
    try {
      await authService.requestAccountClaimEmail(form.email.trim());
      setSuccess('A fresh link is on its way to your inbox.');
      setTokenInvalid(false);
    } catch (err: any) {
      setError(err?.message || 'Unable to send a new link right now.');
    } finally {
      setIsRequestingLink(false);
    }
  };

  const handleEmailSave = () => {
    if (!form.email.trim()) {
      setError('Email address is required.');
      return;
    }
    setForm((prev) => ({ ...prev, email: form.email.trim() }));
    setIsEditingEmailField(false);
  };

  const claimDisabled = tokenMissing;

  return (
    <Layout>
      <section className="bg-white py-12 lg:py-16">
        <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 space-y-8">
          <div className="text-center space-y-3">
            <p className="text-[11px] uppercase tracking-[0.5em] text-gray-400">Account Security</p>
            <h1 className="text-2xl font-display text-dark">Set Your Shopsoma Password</h1>
            <p className="text-sm text-gray-600">
              Connect your guest checkout history to a secure account for faster orders, saved addresses, and real-time updates.
            </p>
          </div>

          {(tokenMissing || tokenInvalid) && (
            <div className="rounded-sm border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              {tokenMissing
                ? 'This claim link is incomplete. Use the button below to request a fresh email.'
                : 'This claim link appears invalid or expired. Request a new link to secure your account.'}
            </div>
          )}

          {(error || success) && (
            <div
              className={`px-4 py-3 rounded-sm flex items-start gap-2 text-left ${
                error ? 'bg-red-50 border border-red-200 text-red-700' : 'bg-emerald-50 border border-emerald-200 text-emerald-700'
              }`}
            >
              {error ? <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" /> : <CheckCircle2 className="w-5 h-5 flex-shrink-0 mt-0.5" />}
              <span className="text-sm">{error || success}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6 text-left">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-[0.3em]">Email Address</label>
                {!isEditingEmailField && (
                  <button
                    type="button"
                    onClick={() => setIsEditingEmailField(true)}
                    className="text-xs font-semibold text-primary hover:text-primary-dark"
                  >
                    Change
                  </button>
                )}
              </div>
              <div className="flex items-center gap-3">
                <div
                  className={`flex-1 flex items-center border border-gray-300 rounded-sm px-3 py-2 ${
                    isEditingEmailField ? 'bg-white' : 'bg-gray-50'
                  }`}
                >
                  <Mail className="text-gray-400 w-4 h-4 mr-2" />
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                    className={`flex-1 text-sm focus:outline-none ${!isEditingEmailField ? 'bg-gray-50 cursor-not-allowed' : 'bg-transparent'}`}
                    placeholder="guest@example.com"
                    readOnly={!isEditingEmailField}
                  />
                </div>
                {isEditingEmailField && (
                  <button
                    type="button"
                    onClick={handleEmailSave}
                    className="px-4 py-2 text-xs font-semibold text-white bg-primary rounded-sm hover:bg-primary-dark disabled:opacity-50"
                    disabled={!form.email.trim()}
                  >
                    Save
                  </button>
                )}
              </div>
              <p className="text-xs text-gray-500">
                {isEditingEmailField ? 'Use the email you entered during guest checkout.' : 'Guest account created for this email.'}
              </p>
            </div>

            <div className="space-y-2">
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-[0.3em]">Full Name</label>
              <input
                type="text"
                value={form.full_name}
                onChange={(e) => setForm((prev) => ({ ...prev, full_name: e.target.value }))}
                className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="Enter your full name"
                disabled={isSubmitting || claimDisabled}
              />
            </div>

            <div className="space-y-2">
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-[0.3em]">Create Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => setForm((prev) => ({ ...prev, password: e.target.value }))}
                  className="w-full border border-gray-300 rounded-sm px-3 py-2 pr-10 text-sm focus:border-primary focus:outline-none"
                  placeholder="Create a secure password"
                  minLength={8}
                  disabled={isSubmitting || claimDisabled}
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-2 flex items-center text-gray-500 hover:text-gray-700"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label="Toggle password visibility"
                  disabled={isSubmitting || claimDisabled}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-[11px] font-semibold text-gray-500 uppercase tracking-[0.3em]">Confirm Password</label>
              <div className="relative">
                <input
                  type={showConfirmPassword ? 'text' : 'password'}
                  value={form.confirmPassword}
                  onChange={(e) => setForm((prev) => ({ ...prev, confirmPassword: e.target.value }))}
                  className="w-full border border-gray-300 rounded-sm px-3 py-2 pr-10 text-sm focus:border-primary focus:outline-none"
                  placeholder="Re-enter password"
                  minLength={8}
                  disabled={isSubmitting || claimDisabled}
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-2 flex items-center text-gray-500 hover:text-gray-700"
                  onClick={() => setShowConfirmPassword((prev) => !prev)}
                  aria-label="Toggle confirm password visibility"
                  disabled={isSubmitting || claimDisabled}
                >
                  {showConfirmPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={!isReady || isSubmitting || claimDisabled}
              className={`w-full py-3 rounded-sm text-sm font-semibold transition ${
                isReady && !isSubmitting && !claimDisabled ? 'bg-primary text-white hover:bg-primary-dark' : 'bg-gray-200 text-gray-500 cursor-not-allowed'
              }`}
            >
              {isSubmitting ? 'Securing account...' : 'Activate Account'}
            </button>

            <div className="text-center">
              <button
                type="button"
                onClick={handleResendLink}
                disabled={!form.email || isRequestingLink}
                className="text-sm font-semibold text-primary hover:underline disabled:opacity-50"
              >
                {isRequestingLink ? 'Sending link...' : 'Need a fresh link?'}
              </button>
            </div>
          </form>
        </div>
      </section>
      <Newsletter />
    </Layout>
  );
}
