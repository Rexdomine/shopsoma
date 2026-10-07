import { useState } from 'react';
import { Mail, Lock, Eye, EyeOff, LogIn } from 'lucide-react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ROUTES, VENDOR_LOGIN_IMAGE_URL } from '../../config/constants';
import { vendorService } from '../../services/vendorService';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

export const isValidEmail = (email: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

export interface VendorLoginFormState {
  email: string;
  password: string;
}

export interface VendorLoginFieldErrors {
  email?: string;
  password?: string;
}

export const validateVendorLoginField = (
  field: keyof VendorLoginFieldErrors,
  form: VendorLoginFormState
): string | undefined => {
  switch (field) {
    case 'email': {
      const trimmed = form.email.trim();
      if (!trimmed) return 'Email address is required';
      if (!isValidEmail(trimmed)) return 'Please enter a valid email address';
      return undefined;
    }
    case 'password': {
      if (!form.password) return 'Password is required';
      return undefined;
    }
    default:
      return undefined;
  }
};

export const validateVendorLoginForm = (form: VendorLoginFormState): VendorLoginFieldErrors => {
  const errors: VendorLoginFieldErrors = {};
  const fields: (keyof VendorLoginFieldErrors)[] = ['email', 'password'];
  for (const field of fields) {
    const error = validateVendorLoginField(field, form);
    if (error) {
      errors[field] = error;
    }
  }
  return errors;
};

export default function VendorLogin() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [form, setForm] = useState<VendorLoginFormState>({ email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState<VendorLoginFieldErrors>({});
  const [touched, setTouched] = useState<Record<keyof VendorLoginFieldErrors, boolean>>({
    email: false,
    password: false,
  });

  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [attemptsLeft, setAttemptsLeft] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleFieldChange = (key: keyof VendorLoginFormState, value: string) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (touched[key] || fieldErrors[key]) {
        const err = validateVendorLoginField(key, next);
        setFieldErrors((e) => ({ ...e, [key]: err }));
      }
      return next;
    });
    if (error) {
      setError('');
      setAttemptsLeft(null);
    }
  };

  const handleBlur = (field: keyof VendorLoginFieldErrors) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    const err = validateVendorLoginField(field, form);
    setFieldErrors((prev) => ({ ...prev, [field]: err }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setAttemptsLeft(null);

    const allTouched: Record<keyof VendorLoginFieldErrors, boolean> = {
      email: true,
      password: true,
    };
    setTouched(allTouched);

    const errors = validateVendorLoginForm(form);
    setFieldErrors(errors);

    if (Object.keys(errors).length > 0) {
      setError('Please fix the errors below to continue');
      return;
    }

    setIsLoading(true);

    try {
      await login({
        email: form.email.trim(),
        password: form.password,
      });

      const userStr = localStorage.getItem('shopsoma_user');
      const userData = userStr ? JSON.parse(userStr) : null;

      if (userData?.role === 'admin') {
        navigate('/admin/users', { replace: true });
      } else if (userData?.role === 'vendor') {
        try {
          const vendorProfile = await vendorService.getProfile();
          navigate(
            vendorProfile.is_onboarding ? ROUTES.VENDOR_DASHBOARD : ROUTES.VENDOR_ANALYTICS,
            { replace: true }
          );
        } catch {
          navigate(ROUTES.VENDOR_DASHBOARD, { replace: true });
        }
      } else {
        const from = (location.state as any)?.from?.pathname;
        if (from && from !== ROUTES.LOGIN) {
          navigate(from, { replace: true });
        } else {
          navigate('/', { replace: true });
        }
      }
    } catch (err: any) {
      const message = apiErrorMessage(err, err?.message || 'Login failed. Please try again.');
      setError(message);
      const match = /\b(\d+)\s*attempt/i.exec(message);
      if (match) {
        setAttemptsLeft(Number(match[1]));
      } else if (message.toLowerCase().includes('too many')) {
        setAttemptsLeft(0);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const bannerText =
    attemptsLeft !== null
      ? `Wrong password code. ${attemptsLeft} Attempts left`
      : error
        ? error
        : '';

  return (
    <div className="min-h-screen bg-white flex flex-col">
      <main className="flex-1 w-full px-4 sm:px-6 lg:px-12 py-12 flex items-stretch">
        <div className="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] gap-10 lg:gap-12 items-stretch h-full min-h-[80vh] lg:min-h-[90vh]">
          {/* Left - Logo + Card + Link */}
          <div className="w-full flex flex-col items-center justify-center h-full">
            <img
              src="/images/somalogo.svg"
              alt="Shopsoma"
              className="h-8 w-auto mb-8"
            />
            <div className="w-full max-w-[460px]">
              {bannerText && (
                <div className="rounded-t-3xl bg-[#d62c2c] text-white text-xs font-semibold px-4 py-2 text-center" role="alert">
                  {bannerText}
                </div>
              )}
              <div className={`bg-white shadow-xl rounded-3xl border border-gray-100 px-8 py-10 ${bannerText ? 'rounded-t-none' : ''}`}>
                <div className="flex flex-col items-center gap-4 mb-6">
                  <div className="h-12 w-12 rounded-xl bg-[#105E53]/10 border border-[#105E53]/20 flex items-center justify-center text-[#105E53]">
                    <LogIn className="w-5 h-5" />
                  </div>
                  <div className="text-center space-y-2">
                    <h1 className="text-2xl font-display text-[#105E53]">Welcome back to Shopsoma!</h1>
                    <p className="text-sm text-gray-500 font-[var(--font-ui)]">
                      You can only log in using the details provided by the support team
                    </p>
                  </div>
                </div>

                <form className="space-y-6 text-left" onSubmit={handleSubmit} noValidate>
                  <div className="space-y-2">
                    <div className="relative">
                      <Mail className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 transition-colors ${fieldErrors.email ? 'text-red-500' : 'text-gray-400'}`} />
                      <input
                        id="vendor-login-email"
                        type="email"
                        value={form.email}
                        onChange={(e) => handleFieldChange('email', e.target.value)}
                        onBlur={() => handleBlur('email')}
                        placeholder="example@mail.com"
                        autoComplete="email"
                        aria-label="Email Address"
                        aria-invalid={Boolean(fieldErrors.email)}
                        aria-describedby={fieldErrors.email ? 'vendor-email-error' : undefined}
                        className={`w-full pl-10 pr-3 py-3 rounded-xl border text-sm font-ui text-[#222424] focus:outline-none transition-colors ${
                          fieldErrors.email
                            ? 'border-red-500 focus:border-red-600 focus:ring-1 focus:ring-red-500/30'
                            : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
                        }`}
                        disabled={isLoading}
                      />
                    </div>
                    {fieldErrors.email && (
                      <p id="vendor-email-error" className="text-xs font-ui text-red-600 pl-1">
                        {fieldErrors.email}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <div className="relative">
                      <Lock className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 transition-colors ${fieldErrors.password ? 'text-red-500' : 'text-gray-400'}`} />
                      <input
                        id="vendor-login-password"
                        type={showPassword ? 'text' : 'password'}
                        value={form.password}
                        onChange={(e) => handleFieldChange('password', e.target.value)}
                        onBlur={() => handleBlur('password')}
                        placeholder="Password"
                        autoComplete="current-password"
                        aria-label="Password"
                        aria-invalid={Boolean(fieldErrors.password)}
                        aria-describedby={fieldErrors.password ? 'vendor-password-error' : undefined}
                        className={`w-full pl-10 pr-10 py-3 rounded-xl border text-sm font-ui text-[#222424] focus:outline-none transition-colors ${
                          fieldErrors.password
                            ? 'border-red-500 focus:border-red-600 focus:ring-1 focus:ring-red-500/30'
                            : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
                        }`}
                        disabled={isLoading}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((prev) => !prev)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-[#105E53] transition"
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                        disabled={isLoading}
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    {fieldErrors.password && (
                      <p id="vendor-password-error" className="text-xs font-ui text-red-600 pl-1">
                        {fieldErrors.password}
                      </p>
                    )}
                  </div>

                  <div className="flex items-center justify-between text-xs font-[var(--font-ui)] text-[#105E53]">
                    <Link to={`${ROUTES.FORGOT_PASSWORD}?role=vendor`} className="hover:text-[#0c4c45] font-[var(--font-ui)]">
                      Forgot Password?
                    </Link>
                    <a href="mailto:support@shopsoma.com" className="hover:text-[#0c4c45] font-[var(--font-ui)]">
                      Contact Support
                    </a>
                  </div>

                  <button
                    type="submit"
                    disabled={isLoading}
                    className="w-full py-3.5 text-sm font-[var(--font-ui)] tracking-[0.08em] rounded-xl transition bg-[#105E53] text-white hover:bg-[#0c4c45] disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
                      <span className="flex items-center justify-center gap-2">
                        <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                        Logging in...
                      </span>
                    ) : (
                      'Log in'
                    )}
                  </button>
                </form>
              </div>
              <div className="mt-6 text-center text-xs font-[var(--font-ui)] text-[#105E53]">
                Wrong place?{' '}
                <a href="https://shopsoma.com" className="underline hover:text-[#0c4c45] font-[var(--font-ui)]">
                  Back to Shopsoma.com
                </a>
              </div>
            </div>
          </div>

          {/* Right - Image */}
          <div className="w-full flex items-stretch h-full">
            <div className="h-full w-full rounded-[32px] overflow-hidden shadow-lg">
              <img
                src={VENDOR_LOGIN_IMAGE_URL}
                alt="Shopsoma vendor feature"
                className="w-full h-full object-cover"
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
