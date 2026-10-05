import { useEffect, useState } from 'react';
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
