import { useEffect, useState } from 'react';
import { Eye, EyeOff, AlertCircle } from 'lucide-react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Layout from '../../components/layout/Layout';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

export const isValidEmail = (email: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

export interface LoginFormState {
  email: string;
  password: string;
}

export interface LoginFieldErrors {
  email?: string;
  password?: string;
}

export const validateLoginField = (
  field: keyof LoginFieldErrors,
  form: LoginFormState
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

export const validateLoginForm = (form: LoginFormState): LoginFieldErrors => {
  const errors: LoginFieldErrors = {};
  const fields: (keyof LoginFieldErrors)[] = ['email', 'password'];
  for (const field of fields) {
    const error = validateLoginField(field, form);
    if (error) {
      errors[field] = error;
    }
  }
  return errors;
};

export default function Login() {
  const [form, setForm] = useState<LoginFormState>({ email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState<LoginFieldErrors>({});
  const [touched, setTouched] = useState<Record<keyof LoginFieldErrors, boolean>>({
    email: false,
    password: false,
  });

  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const [guestEmail, setGuestEmail] = useState('');
  const [guestError, setGuestError] = useState('');
  const [guestTouched, setGuestTouched] = useState(false);
  const [newsletterOptIn, setNewsletterOptIn] = useState(false);

  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const stateEmail = (location.state as any)?.prefillEmail;
    if (stateEmail) {
      setForm((prev) => ({ ...prev, email: stateEmail }));
    }
  }, [location.state]);

  const handleFieldChange = (key: keyof LoginFormState, value: string) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (touched[key] || fieldErrors[key]) {
        const err = validateLoginField(key, next);
        setFieldErrors((e) => ({ ...e, [key]: err }));
      }
      return next;
    });
    if (error) setError('');
  };

  const handleBlur = (field: keyof LoginFieldErrors) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    const err = validateLoginField(field, form);
    setFieldErrors((prev) => ({ ...prev, [field]: err }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    const allTouched: Record<keyof LoginFieldErrors, boolean> = {
      email: true,
      password: true,
    };
    setTouched(allTouched);

    const errors = validateLoginForm(form);
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

      // Get the user data to check role
      const userStr = localStorage.getItem('shopsoma_user');
      const userData = userStr ? JSON.parse(userStr) : null;

      // Redirect based on user role
      if (userData?.role === 'admin') {
        navigate('/admin/vendor-applications', { replace: true });
      } else if (userData?.role === 'vendor') {
        navigate('/vendor/analytics', { replace: true });
      } else {
        // Regular users: redirect to the page they were trying to access
        // Check if user came from checkout, otherwise go to home
        const from = (location.state as any)?.from?.pathname;
        if (from && from !== '/login') {
          navigate(from, { replace: true });
        } else {
          navigate('/', { replace: true });
        }
      }
    } catch (err: any) {
      setError(apiErrorMessage(err, err?.message || 'Login failed. Please try again.'));
    } finally {
      setIsLoading(false);
    }
  };

  const handleGuestEmailChange = (val: string) => {
    setGuestEmail(val);
    if (guestTouched) {
      const trimmed = val.trim();
      if (!trimmed) {
        setGuestError('Email address is required');
      } else if (!isValidEmail(trimmed)) {
        setGuestError('Please enter a valid email address');
      } else {
        setGuestError('');
      }
    }
  };

  const handleGuestEmailBlur = () => {
    setGuestTouched(true);
    const trimmed = guestEmail.trim();
    if (!trimmed) {
      setGuestError('Email address is required');
    } else if (!isValidEmail(trimmed)) {
      setGuestError('Please enter a valid email address');
    } else {
      setGuestError('');
    }
  };

  const handleGuestSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setGuestTouched(true);
    const trimmedEmail = guestEmail.trim();
    if (!trimmedEmail) {
      setGuestError('Email address is required');
      return;
    }
    if (!isValidEmail(trimmedEmail)) {
      setGuestError('Please enter a valid email address');
      return;
    }
    setGuestError('');
    sessionStorage.setItem('shopsoma_guest_email', trimmedEmail);
    if (newsletterOptIn) {
      sessionStorage.setItem('shopsoma_guest_newsletter', 'true');
    } else {
      sessionStorage.removeItem('shopsoma_guest_newsletter');
    }
    navigate('/cart', { state: { guestEmail: trimmedEmail, guestNewsletter: newsletterOptIn } });
  };

  return (
    <Layout>
      <section className="relative bg-[var(--color-page-bg)] min-h-screen py-12 lg:py-16">
        <div className="hidden lg:block absolute top-0 bottom-0 left-1/2 w-px bg-[#105E53] -translate-x-1/2 pointer-events-none" aria-hidden="true" />
        <div className="max-w-[1250px] mx-auto px-4 sm:px-6 lg:px-[64px]">
          <div className="bg-transparent grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 px-0 py-[72px]">
            {/* Login Column */}
            <div className="space-y-10 lg:pr-12">
              <div className="space-y-3">
                <h1 className="text-3xl lg:text-[32px] font-display text-[#105E53]">Login to your account</h1>
                <p className="text-xs font-ui uppercase tracking-[0.28em] text-[#105E53]">
                  Speed up your purchase and save the details of the order in your account
                </p>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 flex items-start gap-2 text-left" role="alert">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <span className="text-sm">{error}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} noValidate className="space-y-8 text-left">
                <div className="space-y-6">
                  <div className="space-y-2">
                    <label htmlFor="login-email" className="text-base font-serif text-[#105E53] flex items-center justify-between">
                      <span>
                        Email Address
                        <span className="text-red-500 ml-1" aria-hidden="true">*</span>
                      </span>
                    </label>
                    <input
                      id="login-email"
                      type="email"
                      value={form.email}
                      onChange={(e) => handleFieldChange('email', e.target.value)}
                      onBlur={() => handleBlur('email')}
                      autoComplete="email"
                      aria-invalid={Boolean(fieldErrors.email)}
                      aria-describedby={fieldErrors.email ? 'login-email-error' : undefined}
                      className={`w-full border-0 border-b bg-transparent px-0 py-3 text-base font-serif text-[#222424] focus:outline-none focus:ring-0 transition-colors ${
                        fieldErrors.email
                          ? 'border-red-500 focus:border-red-600'
                          : 'border-[#105E53] focus:border-[#105E53]'
                      }`}
                      disabled={isLoading}
                    />
                    {fieldErrors.email && (
                      <p id="login-email-error" className="text-xs font-ui text-red-600">
                        {fieldErrors.email}
                      </p>
                    )}
                  </div>

                  <div className="space-y-2">
                    <label htmlFor="login-password" className="text-base font-serif text-[#105E53] flex items-center justify-between">
                      <span>
                        Password
                        <span className="text-red-500 ml-1" aria-hidden="true">*</span>
                      </span>
                    </label>
                    <div className="relative">
                      <input
                        id="login-password"
                        type={showPassword ? 'text' : 'password'}
                        value={form.password}
                        onChange={(e) => handleFieldChange('password', e.target.value)}
                        onBlur={() => handleBlur('password')}
                        autoComplete="current-password"
                        aria-invalid={Boolean(fieldErrors.password)}
                        aria-describedby={fieldErrors.password ? 'login-password-error' : undefined}
                        className={`w-full border-0 border-b bg-transparent px-0 py-3 pr-10 text-base font-serif text-[#222424] focus:outline-none focus:ring-0 transition-colors ${
                          fieldErrors.password
                            ? 'border-red-500 focus:border-red-600'
                            : 'border-[#105E53] focus:border-[#105E53]'
                        }`}
                        disabled={isLoading}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((prev) => !prev)}
                        className="absolute inset-y-0 right-0 flex items-center text-[#105E53] hover:text-[#0c4c45] transition p-1"
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                        disabled={isLoading}
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                    {fieldErrors.password && (
                      <p id="login-password-error" className="text-xs font-ui text-red-600">
                        {fieldErrors.password}
                      </p>
                    )}
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-4 text-sm font-ui uppercase tracking-[0.24em] bg-[#105E53] text-white hover:bg-[#0c4c45] transition disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <span className="flex items-center justify-center gap-2">
                      <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      Signing in...
                    </span>
                  ) : (
                    'Login'
                  )}
                </button>

                <div className="flex items-center justify-between text-sm">
                  <Link to="/forgot-password" className="text-[#105E53] hover:text-[#0c4c45] font-ui">
                    Forgot password?
                  </Link>
                  <Link to="/register" className="text-[#105E53] hover:text-[#0c4c45] font-ui">
                    Create account
                  </Link>
                </div>

                {/* Social Login - Hidden */}
              </form>
            </div>

            {/* Guest Checkout Column */}
            <div className="space-y-10 lg:pl-12">
              <div className="space-y-3">
                <h2 className="text-3xl lg:text-[32px] font-display text-[#105E53]">Checkout as guest</h2>
                <p className="text-xs font-ui uppercase tracking-[0.28em] text-[#105E53]">
                  You can complete your order without registering
                </p>
              </div>

              <form className="space-y-8 text-left" onSubmit={handleGuestSubmit} noValidate>
                <div className="space-y-2">
                  <label htmlFor="login-guest-email" className="text-base font-serif text-[#105E53]">
                    Email
                  </label>
                  <input
                    id="login-guest-email"
                    type="email"
                    value={guestEmail}
                    onChange={(e) => handleGuestEmailChange(e.target.value)}
                    onBlur={handleGuestEmailBlur}
                    aria-invalid={Boolean(guestError)}
                    aria-describedby={guestError ? 'login-guest-email-error' : undefined}
                    className={`w-full border-0 border-b bg-transparent px-0 py-3 text-base font-serif text-[#222424] focus:outline-none focus:ring-0 transition-colors ${
                      guestError
                        ? 'border-red-500 focus:border-red-600'
                        : 'border-[#105E53] focus:border-[#105E53]'
                    }`}
                  />
                  {guestError && (
                    <p id="login-guest-email-error" className="text-xs font-ui text-red-600">
                      {guestError}
                    </p>
                  )}
                </div>

                <button
                  type="submit"
                  className="w-full py-4 text-sm font-ui uppercase tracking-[0.24em] bg-[#105E53] text-white hover:bg-[#0c4c45] transition"
                >
                  Continue as guest
                </button>

                <label className="flex items-center gap-3 text-sm font-serif text-[#105E53]">
                  <input
                    type="checkbox"
                    checked={newsletterOptIn}
                    onChange={(e) => setNewsletterOptIn(e.target.checked)}
                    className="h-4 w-4 border border-[#105E53] text-[#105E53] focus:ring-[#105E53]"
                  />
                  <span>Sign me up for the Newsletter</span>
                </label>
              </form>
            </div>
          </div>
        </div>
      </section>
    </Layout>
  );
}
