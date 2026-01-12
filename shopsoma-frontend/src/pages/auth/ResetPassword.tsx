import { useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import Newsletter from '../../components/home/Newsletter';
import { ROUTES } from '../../config/constants';
import { authService } from '../../services/authService';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [toast, setToast] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const passwordMatch = newPassword.length > 0 && newPassword === confirmPassword;
  const isComplete = token.trim().length > 0 && newPassword.length >= 8 && passwordMatch;
  const submitLabel = useMemo(() => {
    if (isSubmitting) {
      return 'Saving...';
    }
    return 'Update password';
  }, [isSubmitting]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!isComplete || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    try {
      await authService.resetPassword(token.trim(), newPassword);
      setToastMessage('Your password has been updated. Please sign in.');
      setToast(true);
      setTimeout(() => {
        navigate(ROUTES.LOGIN);
      }, 1200);
    } catch (error: any) {
      setToastMessage(error?.message || 'Unable to reset password. Please try again.');
      setToast(true);
    } finally {
      setIsSubmitting(false);
      setTimeout(() => setToast(false), 4000);
    }
  };

  return (
    <Layout>
      {toast && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-center text-center">
            <div className="text-sm">
              <p className="font-semibold">Reset password</p>
              <p className="text-white/90">{toastMessage}</p>
            </div>
          </div>
        </div>
      )}
      <section className="bg-white py-10 lg:py-16">
        <div className="max-w-xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <h1 className="text-2xl font-display text-dark">Reset Password</h1>
          <p className="text-sm text-gray-600">
            Enter a new password for your account. Passwords must be at least 8 characters.
          </p>
          {!token && (
            <div className="rounded-sm border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
              This link is missing or invalid. Request a new reset link to continue.
            </div>
          )}
          <form onSubmit={handleSubmit} className="space-y-4 text-left">
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="Enter new password"
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700">Confirm Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="Re-enter new password"
                required
              />
            </div>
            {confirmPassword.length > 0 && !passwordMatch && (
              <p className="text-xs text-red-600">Passwords do not match.</p>
            )}
            <button
              type="submit"
              disabled={!isComplete || isSubmitting}
              className={`w-full py-3 rounded-sm text-sm font-semibold transition ${
                isComplete && !isSubmitting
                  ? 'bg-primary text-white hover:bg-primary-dark'
                  : 'bg-gray-200 text-gray-500 cursor-not-allowed'
              }`}
            >
              {submitLabel}
            </button>
            <div className="text-center text-sm text-gray-600">
              <button
                type="button"
                onClick={() => navigate(ROUTES.FORGOT_PASSWORD)}
                className="text-primary hover:text-primary-dark"
              >
                Request a new reset link
              </button>
            </div>
          </form>
        </div>
      </section>
      <Newsletter />
    </Layout>
  );
}
