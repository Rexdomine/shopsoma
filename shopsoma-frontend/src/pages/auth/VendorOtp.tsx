import { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { vendorActivationService } from '../../services/vendorActivationService';
import { ROUTES } from '../../config/constants';

const DEFAULT_LENGTH = 6;

type LocationState = {
  maskedEmail?: string;
  token?: string;
  length?: number;
};

export default function VendorOtp() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  // Get email from URL query parameter for activation link flow
  const emailFromUrl = searchParams.get('email');

  const { maskedEmail, token: tokenFromState, length } = (location.state as LocationState) || {};

  const otpLength = length && length > 0 ? length : DEFAULT_LENGTH;
  const [displayEmail, setDisplayEmail] = useState(maskedEmail || 'your email');
  const [activationToken, setActivationToken] = useState(tokenFromState || '');

  const [values, setValues] = useState<string[]>(Array(otpLength).fill(''));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [initializing, setInitializing] = useState(!!emailFromUrl);
  const [accountAlreadySetup, setAccountAlreadySetup] = useState(false);
  const [alreadySetupMessage, setAlreadySetupMessage] = useState('');
  const [resetPasswordUrl, setResetPasswordUrl] = useState<string>(ROUTES.FORGOT_PASSWORD);
  const [supportEmail, setSupportEmail] = useState('admin@shopsoma.com');
  const inputsRef = useRef<Array<HTMLInputElement | null>>([]);

  const code = useMemo(() => values.join(''), [values]);

  // Initialize activation if email is provided in URL (activation link flow)
  useEffect(() => {
    const initializeActivation = async () => {
      if (!emailFromUrl || activationToken) {
        setInitializing(false);
        return;
      }

      try {
        const response = await vendorActivationService.initiateActivation(emailFromUrl);
        if (response.account_already_setup) {
          setAccountAlreadySetup(true);
          setAlreadySetupMessage(
            response.message ||
              'This vendor account is already set up. Please reset your password or contact admin for help.'
          );
          setResetPasswordUrl(response.reset_password_url || ROUTES.FORGOT_PASSWORD);
          setSupportEmail(response.support_email || 'admin@shopsoma.com');
          setInitializing(false);
          return;
        }

        if (response.token) {
          setActivationToken(response.token);
        }
        if (response.masked_email) {
          setDisplayEmail(response.masked_email);
        }
        setInitializing(false);
      } catch (err: any) {
        setError(err?.message || 'Failed to initialize activation. Please try again.');
        setInitializing(false);
      }
    };

    initializeActivation();
  }, [emailFromUrl, activationToken]);

  useEffect(() => {
    if (!initializing) {
      inputsRef.current[0]?.focus();
    }
  }, [otpLength, initializing]);

  const handleChange = (index: number, value: string) => {
    if (!value) {
      setValues((prev) => {
        const updated = [...prev];
        updated[index] = '';
        return updated;
      });
      setError('');
      return;
    }

    const char = value.slice(-1);
    setValues((prev) => {
      const updated = [...prev];
      updated[index] = char;
      return updated;
    });
    setError('');

    if (index < otpLength - 1) {
      inputsRef.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index: number, event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Backspace' && !values[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (code.length !== otpLength || loading || !activationToken) return;

    setLoading(true);
    setError('');

    try {
      const response = await vendorActivationService.verifyOTP(activationToken, code);

      setSuccess(true);

      // Redirect to password creation page
      setTimeout(() => {
        navigate(ROUTES.VENDOR_SET_PASSWORD, {
          replace: true,
          state: {
            token: response.activation_token,
            email: response.email
          }
        });
      }, 500);
    } catch (err: any) {
      setError(err?.message || 'Invalid code. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    if (resendLoading || !activationToken) return;

    setResendLoading(true);
    setError('');
    setValues(Array(otpLength).fill(''));

    try {
      const response = await vendorActivationService.resendOTP(activationToken);
      setDisplayEmail(response.masked_email);
      // Show success message briefly
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setError(err?.message || 'Could not resend code. Try again shortly.');
    } finally {
      setResendLoading(false);
    }
  };

  // Show loading state while initializing
  if (initializing) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-[#105E53] mx-auto"></div>
          <p className="mt-4 text-gray-600">Preparing activation...</p>
        </div>
      </div>
    );
  }

  // Show error if no activation token available
  if (accountAlreadySetup && !initializing) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex items-center justify-center px-4">
        <div className="max-w-md text-center">
          <div className="bg-white rounded-lg shadow-md p-8">
            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-amber-100 flex items-center justify-center">
              <span className="text-amber-700 text-2xl">!</span>
            </div>
            <h2 className="text-xl font-display text-[#105E53] mb-2">Account Already Set Up</h2>
            <p className="text-gray-600 mb-6">{alreadySetupMessage}</p>
            <div className="space-y-3">
              <a
                href={resetPasswordUrl}
                className="inline-block w-full px-6 py-3 bg-[#105E53] text-white rounded-xl hover:bg-[#0c4c45] transition"
              >
                Reset Password
              </a>
              <p className="text-sm text-gray-600">
                Need help? Contact admin at{' '}
                <a href={`mailto:${supportEmail}`} className="text-[#105E53] underline">
                  {supportEmail}
                </a>
                .
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!activationToken && !initializing) {
    return (
      <div className="min-h-screen bg-[var(--color-page-bg)] flex items-center justify-center px-4">
        <div className="max-w-md text-center">
          <div className="bg-white rounded-lg shadow-md p-8">
            <div className="w-12 h-12 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
              <span className="text-red-600 text-2xl">✕</span>
            </div>
            <h2 className="text-xl font-display text-[#105E53] mb-2">Invalid Activation Link</h2>
            <p className="text-gray-600 mb-6">
              This activation link is invalid or has expired. Please contact support or check your email for a new activation link.
            </p>
            <button
              onClick={() => navigate(ROUTES.VENDOR_LOGIN)}
              className="px-6 py-3 bg-[#105E53] text-white rounded-xl hover:bg-[#0c4c45] transition"
            >
              Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] flex items-center justify-center px-4 sm:px-6 lg:px-12 py-12">
      <style>{`
        @keyframes glowIn {
          0% { opacity: 0; transform: scale(0.6); text-shadow: 0 0 0 rgba(255,255,255,0); }
          60% { opacity: 1; transform: scale(1.05); text-shadow: 0 0 16px rgba(255,255,255,0.9); }
          100% { opacity: 1; transform: scale(1); text-shadow: 0 0 8px rgba(255,255,255,0.7); }
        }
      `}</style>

      <div className="w-full max-w-6xl grid grid-cols-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] gap-10 lg:gap-14 items-stretch py-8">
        {/* Left Column */}
        <div className="flex flex-col items-center justify-center space-y-8">
          <img src="/images/somalogo.svg" alt="Shopsoma" className="h-8 w-auto" />

          <div className="w-full max-w-[440px]">
            <div className="bg-white border border-gray-100 shadow-md rounded-3xl px-8 py-10 text-center">
              <div className="w-10 h-10 mx-auto mb-6 rounded-xl border border-gray-200 flex items-center justify-center text-gray-500">
                <span className="text-lg">•••</span>
              </div>
              <h2 className="text-xl font-display text-[#105E53] mb-2">We sent you a code</h2>
              <p className="text-sm text-gray-500 font-ui mb-6">
                Please input the code sent to the email {displayEmail}
              </p>

              <form className="space-y-6" onSubmit={handleSubmit}>
                <div className="flex justify-center gap-3">
                  {values.map((val, idx) => (
                    <input
                      key={idx}
                      ref={(el) => {
                        inputsRef.current[idx] = el;
                      }}
                      type="text"
                      inputMode="numeric"
                      maxLength={1}
                      value={val}
                      onChange={(e) => handleChange(idx, e.target.value.replace(/\s/g, ''))}
                      onKeyDown={(e) => handleKeyDown(idx, e)}
                      className="w-12 h-14 rounded-xl border border-gray-200 text-center text-lg font-ui text-[#105E53] focus:border-[#105E53] focus:outline-none focus:ring-1 focus:ring-[#105E53]/30"
                    />
                  ))}
                </div>

                {error && (
                  <div className="text-sm text-red-600">{error}</div>
                )}
                {success && !error && !resendLoading && (
                  <div className="text-sm text-green-600">
                    {loading ? 'Code verified! Redirecting to password creation…' : 'New code sent successfully!'}
                  </div>
                )}

                <div className="text-xs text-gray-600 font-ui">
                  Didn't get the code?{' '}
                  <button
                    type="button"
                    onClick={handleResend}
                    disabled={resendLoading}
                    className="text-[#105E53] hover:text-[#0c4c45] underline disabled:opacity-60"
                  >
                    {resendLoading ? 'Sending...' : 'Resend'}
                  </button>
                </div>

                <button
                  type="submit"
                  disabled={code.length !== otpLength || loading}
                  className={`w-full py-3 rounded-xl text-sm font-ui tracking-[0.12em] text-white transition ${
                    code.length === otpLength && !loading
                      ? 'bg-[#105E53] hover:bg-[#0c4c45]'
                      : 'bg-[#cbd5d1] text-[#105E53]/80 cursor-not-allowed'
                  }`}
                >
                  {loading ? 'Verifying…' : 'Get Started'}
                </button>
              </form>
            </div>

            <div className="mt-6 text-center text-xs font-ui text-[#105E53]">
              Wrong place?{' '}
              <a href="https://shopsoma.com" className="underline hover:text-[#0c4c45]">
                Back to Shopsoma.com
              </a>
            </div>
          </div>
        </div>

        {/* Right Column */}
        <div className="w-full flex items-stretch">
          <div className="w-full rounded-[32px] bg-[#105E53] flex items-center justify-center relative overflow-hidden min-h-[75vh] lg:min-h-[80vh]">
            <div className="flex items-center justify-center">
              {Array.from({ length: code.length }).map((_, idx) => (
                <span
                  key={`${code}-${idx}`}
                  className="otp-star"
                  style={{
                    animation: 'glowIn 350ms ease-out',
                    fontSize: '64px',
                    color: '#fff',
                    margin: '0 6px',
                    textShadow: '0 0 8px rgba(255,255,255,0.7)',
                  }}
                >
                  *
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
