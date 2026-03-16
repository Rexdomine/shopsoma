import { useEffect, useState, type SVGProps } from 'react';
import { Eye, EyeOff, AlertCircle } from 'lucide-react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Layout from '../../components/layout/Layout';

export default function Login() {
  const [form, setForm] = useState({ email: '', password: '' });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [guestEmail, setGuestEmail] = useState('');
  const [guestError, setGuestError] = useState('');
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

  const isComplete = form.email.trim() && form.password.trim();
  const isValidEmail = (email: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  const handleChange = (key: keyof typeof form, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    if (error) setError(''); // Clear error on input change
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await login({
        email: form.email,
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
      setError(err.message || 'Login failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGuestSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setGuestError('');
    const trimmedEmail = guestEmail.trim();
    if (!trimmedEmail || !isValidEmail(trimmedEmail)) {
      setGuestError('Please enter a valid email address.');
      return;
    }
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
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 flex items-start gap-2 text-left">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <span className="text-sm">{error}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-8 text-left">
                <div className="space-y-6">
                  <div className="space-y-2">
                    <label className="text-base font-serif text-[#105E53]">Email Address</label>
                    <input
                      type="email"
                      value={form.email}
                      onChange={(e) => handleChange('email', e.target.value)}
                      className="w-full border-0 border-b border-[#105E53] bg-transparent px-0 py-3 text-base font-serif text-[#222424] focus:border-[#105E53] focus:outline-none focus:ring-0"
                      required
                      disabled={isLoading}
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-base font-serif text-[#105E53]">Password</label>
                    <div className="relative">
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={form.password}
                        onChange={(e) => handleChange('password', e.target.value)}
                        className="w-full border-0 border-b border-[#105E53] bg-transparent px-0 py-3 pr-10 text-base font-serif text-[#222424] focus:border-[#105E53] focus:outline-none focus:ring-0"
                        required
                        disabled={isLoading}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((prev) => !prev)}
                        className="absolute inset-y-0 right-0 flex items-center text-[#105E53] hover:text-[#0c4c45] transition"
                        aria-label="Toggle password visibility"
                        disabled={isLoading}
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={!isComplete || isLoading}
                  className={`w-full py-4 text-sm font-ui uppercase tracking-[0.24em] transition ${
                    isComplete && !isLoading
                      ? 'bg-[#105E53] text-white hover:bg-[#0c4c45]'
                      : 'bg-[#cbd5d1] text-[#105E53]/70 cursor-not-allowed'
                  }`}
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

                <div className="space-y-4">
                  <div className="flex items-center gap-4 text-xs font-ui uppercase tracking-[0.2em] text-[#105E53]">
                    <span className="flex-1 border-t border-[#105E53]/40" />
                    <span>Or sign in with</span>
                    <span className="flex-1 border-t border-[#105E53]/40" />
                  </div>

                  <div className="space-y-3">
                    <button
                      type="button"
                      className="w-full border border-[#105E53] bg-white text-[#105E53] py-3 text-xs font-ui uppercase tracking-[0.2em] flex items-center justify-center gap-3 hover:bg-[#105E53]/5 transition"
                    >
                      <GoogleIcon className="w-5 h-5" />
                      Sign in with Google
                    </button>
                    <button
                      type="button"
                      className="w-full border border-[#105E53] bg-white text-[#105E53] py-3 text-xs font-ui uppercase tracking-[0.2em] flex items-center justify-center gap-3 hover:bg-[#105E53]/5 transition"
                    >
                      <AppleIcon className="w-5 h-5" />
                      Sign in with Apple
                    </button>
                  </div>
                </div>
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

              <form className="space-y-8 text-left" onSubmit={handleGuestSubmit}>
                <div className="space-y-2">
                  <label className="text-base font-serif text-[#105E53]">Email</label>
                  <input
                    type="email"
                    value={guestEmail}
                    onChange={(e) => setGuestEmail(e.target.value)}
                    className="w-full border-0 border-b border-[#105E53] bg-transparent px-0 py-3 text-base font-serif text-[#222424] focus:border-[#105E53] focus:outline-none focus:ring-0"
                    required
                  />
                  {guestError && (
                    <p className="text-xs font-ui text-red-600">{guestError}</p>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={!guestEmail.trim()}
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

const GoogleIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>
    <path
      d="M21.6 12.227c0-.84-.075-1.64-.214-2.4H12v4.54h5.36c-.232 1.26-.938 2.327-1.996 3.046v2.54h3.228c1.89-1.74 2.988-4.3 2.988-7.326Z"
      fill="#4285F4"
    />
    <path
      d="M12 22c2.7 0 4.968-.894 6.624-2.413l-3.228-2.54c-.896.6-2.04.953-3.396.953-2.612 0-4.824-1.764-5.612-4.136H3.03v2.6C4.674 19.954 8.058 22 12 22Z"
      fill="#34A853"
    />
    <path
      d="M6.388 13.864A5.95 5.95 0 0 1 6.074 12c0-.648.112-1.276.314-1.864V7.536H3.03A9.996 9.996 0 0 0 2 12c0 1.604.386 3.122 1.03 4.464l3.358-2.6Z"
      fill="#FBBC05"
    />
    <path
      d="M12 6.28c1.468 0 2.784.505 3.818 1.496l2.864-2.864C16.964 2.63 14.7 1.6 12 1.6 8.058 1.6 4.674 3.646 3.03 7.536l3.358 2.6C7.176 8.044 9.388 6.28 12 6.28Z"
      fill="#EA4335"
    />
  </svg>
);

const AppleIcon = (props: SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...props}>
    <path
      fill="currentColor"
      d="M19.665 17.195c-.295.68-.64 1.304-1.034 1.873-.545.784-.988 1.325-1.33 1.625-.532.49-1.103.741-1.713.756-.438 0-.968-.125-1.59-.375-.624-.25-1.197-.374-1.72-.374-.545 0-1.133.124-1.762.374-.629.25-1.137.382-1.524.397-.584.025-1.163-.238-1.738-.789-.366-.323-.825-.88-1.378-1.67-.59-.84-1.075-1.812-1.455-2.915-.406-1.184-.61-2.328-.61-3.432 0-1.268.273-2.361.82-3.28a5.07 5.07 0 0 1 1.708-1.775 4.54 4.54 0 0 1 2.32-.68c.455 0 1.05.144 1.787.43.736.287 1.208.431 1.416.431.161 0 .708-.171 1.64-.515.88-.32 1.622-.452 2.225-.397 1.643.132 2.877.779 3.703 1.937-1.472.894-2.205 2.146-2.198 3.758.007 1.253.466 2.292 1.378 3.117.41.387.868.687 1.373.899-.11.316-.226.613-.345.89ZM15.9 3.56c0 .945-.347 1.83-1.04 2.653-.836.984-1.846 1.553-2.942 1.464a2.9 2.9 0 0 1-.022-.36c0-.91.397-1.883 1.102-2.673.352-.404.799-.74 1.342-1.01.542-.26 1.059-.404 1.55-.434.01.12.01.24.01.36Z"
    />
  </svg>
);
