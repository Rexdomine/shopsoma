import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import Newsletter from '../../components/home/Newsletter';
import { ROUTES } from '../../config/constants';
import { authService } from '../../services/authService';

export default function ForgotPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const isComplete = email.trim().length > 0;
  const [toast, setToast] = useState(false);
  const [toastMessage, setToastMessage] = useState('Reset password link sent successfully');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    const token = searchParams.get('token');
    if (token) {
      navigate(`${ROUTES.RESET_PASSWORD}?token=${token}`, { replace: true });
    }
  }, [navigate, searchParams]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!isComplete || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    try {
      await authService.requestPasswordReset(email.trim());
      setToastMessage('If the email exists, a reset link has been sent.');
      setToast(true);
    } catch (error: any) {
      setToastMessage(error?.message || 'Unable to send reset email. Please try again.');
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
              <p className="font-semibold">Forgot password</p>
              <p className="text-white/90">{toastMessage}</p>
            </div>
          </div>
        </div>
      )}
      <section className="bg-white py-10 lg:py-16">
        <div className="max-w-xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <h1 className="text-2xl font-display text-dark">Forgot Password</h1>
          <p className="text-sm text-gray-600">
            Enter your email address used in signing up on Shopsoma. We&apos;ll send you an email with a link in order to choose a new password.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4 text-left">
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700">Email Address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="Enter email address"
                required
              />
            </div>
            <button
              type="submit"
              disabled={!isComplete || isSubmitting}
              className={`w-full py-3 rounded-sm text-sm font-semibold transition ${
                isComplete && !isSubmitting
                  ? 'bg-primary text-white hover:bg-primary-dark'
                  : 'bg-gray-200 text-gray-500 cursor-not-allowed'
              }`}
            >
              {isSubmitting ? 'Sending...' : 'Send instructions'}
            </button>
          </form>
        </div>
      </section>
      <Newsletter />
    </Layout>
  );
}
