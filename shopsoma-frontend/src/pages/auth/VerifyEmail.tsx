import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import api from '../../services/api';
import { useAuth } from '../../context/AuthContext';

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');

    if (!token) {
      setStatus('error');
      setMessage('Invalid verification link');
      return;
    }

    verifyEmail(token);
  }, [searchParams]);

  const verifyEmail = async (token: string) => {
    try {
      const response = await api.post('/auth/verify-email', null, {
        params: { token }
      });

      setStatus('success');
      setMessage(response.data.message || 'Email verified successfully!');

      // Refresh user data to update email_verified status
      await refreshUser();

      // Redirect to profile after 3 seconds
      setTimeout(() => {
        navigate(ROUTES.PROFILE);
      }, 3000);
    } catch (error: any) {
      setStatus('error');
      setMessage(error.response?.data?.detail || 'Failed to verify email. The link may have expired.');
    }
  };

  return (
    <Layout>
      <section className="bg-white py-16">
        <div className="max-w-xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-6">
          {status === 'loading' && (
            <>
              <div className="mx-auto w-16 h-16 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
              <h1 className="text-2xl font-display text-dark">Verifying your email...</h1>
              <p className="text-gray-600">Please wait while we verify your email address.</p>
            </>
          )}

          {status === 'success' && (
            <>
              <div className="mx-auto w-16 h-16 flex items-center justify-center rounded-full bg-green-100 text-green-600 text-3xl">
                ✓
              </div>
              <h1 className="text-2xl font-display text-dark">Email Verified!</h1>
              <p className="text-gray-600">{message}</p>
              <p className="text-sm text-gray-500">Redirecting to your profile...</p>
            </>
          )}

          {status === 'error' && (
            <>
              <div className="mx-auto w-16 h-16 flex items-center justify-center rounded-full bg-red-100 text-red-600 text-3xl">
                ✕
              </div>
              <h1 className="text-2xl font-display text-dark">Verification Failed</h1>
              <p className="text-gray-600">{message}</p>
              <button
                onClick={() => navigate(ROUTES.PROFILE)}
                className="mt-4 px-8 py-3 bg-primary text-white rounded-sm hover:bg-primary-dark transition"
              >
                Go to Profile
              </button>
            </>
          )}
        </div>
      </section>
    </Layout>
  );
}
