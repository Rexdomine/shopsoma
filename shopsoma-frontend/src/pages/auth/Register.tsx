import { useEffect, useMemo, useRef, useState, type SVGProps } from 'react';
import { Eye, EyeOff, AlertCircle } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Layout from '../../components/layout/Layout';
import { subscribeToNewsletter } from '../../services/newsletterService';
import { ROUTES } from '../../config/constants';

// Password validation rules
const validatePassword = (password: string) => {
  const rules = {
    minLength: password.length >= 8,
    hasUppercase: /[A-Z]/.test(password),
    hasNumber: /[0-9]/.test(password),
  };
  const isValid = rules.minLength && rules.hasUppercase && rules.hasNumber;
  return { ...rules, isValid };
};

type RegisterLocationState = {
  from?: { pathname?: string };
  prefillEmail?: string;
};

export default function Register() {
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    password: '',
    dob: '',
    newsletter: false,
  });
  const [confirmPassword, setConfirmPassword] = useState('');
  const [guestEmail, setGuestEmail] = useState('');
  const [guestNewsletter, setGuestNewsletter] = useState(false);
  const [guestError, setGuestError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const locationState = location.state as RegisterLocationState | null;

  useEffect(() => {
    if (locationState?.prefillEmail) {
      setForm((prev) => ({ ...prev, email: locationState.prefillEmail ?? prev.email }));
    }
  }, [locationState?.prefillEmail]);

  const passwordValidation = validatePassword(form.password);
  const isComplete = form.fullName.trim() && form.email.trim() && form.password.trim() && passwordValidation.isValid;

  const handleChange = (key: keyof typeof form, value: string | boolean) => {
    setForm((prev) => ({ ...prev, [key]: value as never }));
    if (error) setError(''); // Clear error on input change
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    // Validate password
    if (!passwordValidation.isValid) {
      setError('Password does not meet security requirements');
      return;
    }

    setIsLoading(true);

    try {
      await register({
        full_name: form.fullName,
        email: form.email,
        password: form.password,
        date_of_birth: form.dob || undefined,
        role: 'customer',
      });

      if (form.newsletter) {
        const [firstName, ...rest] = form.fullName.trim().split(' ');
        try {
          await subscribeToNewsletter({
            email: form.email.trim(),
            firstName: firstName || undefined,
            lastName: rest.join(' ') || undefined,
            consent: true,
          });
        } catch (newsletterError) {
          console.error('Failed to subscribe to newsletter during registration', newsletterError);
        }
      }

      const from = locationState?.from?.pathname;
      navigate(from && from !== ROUTES.REGISTER ? from : '/', { replace: true });
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const isValidEmail = (email: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  const handleGuestSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setGuestError('');
    const trimmedEmail = guestEmail.trim();
    if (!trimmedEmail || !isValidEmail(trimmedEmail)) {
      setGuestError('Please enter a valid email address.');
      return;
    }
    sessionStorage.setItem('shopsoma_guest_email', trimmedEmail);
    if (guestNewsletter) {
      sessionStorage.setItem('shopsoma_guest_newsletter', 'true');
    } else {
      sessionStorage.removeItem('shopsoma_guest_newsletter');
    }
    navigate('/cart', { state: { guestEmail: trimmedEmail, guestNewsletter } });
  };

  return (
    <Layout>
      <section className="relative bg-[var(--color-page-bg)] min-h-screen py-12 lg:py-16">
        <div className="hidden lg:block absolute top-0 bottom-0 left-1/2 w-px bg-[#105E53] -translate-x-1/2 pointer-events-none" aria-hidden="true" />
        <div className="max-w-[1250px] mx-auto px-4 sm:px-6 lg:px-[64px]">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-20 px-0 py-[72px]">
            {/* Sign Up Column */}
            <div className="space-y-10 lg:pr-12">
              <div className="space-y-3">
                <h1 className="text-3xl lg:text-[32px] font-display text-[#105E53]">Sign Up</h1>
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
                  <Field
                    label="Full Name"
                    value={form.fullName}
                    onChange={(val) => handleChange('fullName', val)}
                    type="text"
                    disabled={isLoading}
                  />
                  <Field
                    label="Email Address"
                    value={form.email}
                    onChange={(val) => handleChange('email', val)}
                    type="email"
                    disabled={isLoading}
                  />
                  <PasswordField
                    label="Password"
                    value={form.password}
                    onChange={(val) => handleChange('password', val)}
                    showPassword={showPassword}
                    setShowPassword={setShowPassword}
                    disabled={isLoading}
                  />
                  <PasswordField
                    label="Confirm Password"
                    value={confirmPassword}
                    onChange={setConfirmPassword}
                    showPassword={showPassword}
                    setShowPassword={setShowPassword}
                    disabled={isLoading}
                  />
                  <div className="space-y-2">
                    <label className="text-base font-serif text-[#105E53]">Date of Birth</label>
                    <DatePicker
                      value={form.dob}
                      onChange={(val) => handleChange('dob', val)}
                    />
                  </div>
                  <label className="inline-flex items-center gap-3 text-sm font-serif text-[#105E53]">
                    <input
                      type="checkbox"
                      checked={form.newsletter}
                      onChange={(e) => handleChange('newsletter', e.target.checked)}
                      className="h-4 w-4 border border-[#105E53] text-[#105E53] focus:ring-[#105E53]"
                    />
                    Register to get style news and exclusive offers.
                  </label>
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
                      Creating account...
                    </span>
                  ) : (
                    'Sign Up'
                  )}
                </button>

                <div className="space-y-4">
                  <div className="flex items-center gap-4 text-xs font-ui uppercase tracking-[0.2em] text-[#105E53]">
                    <span className="flex-1 border-t border-[#105E53]/40" />
                    <span>Or continue with</span>
                    <span className="flex-1 border-t border-[#105E53]/40" />
                  </div>

                  <div className="space-y-3">
                    <button
                      type="button"
                      className="w-full border border-[#105E53] bg-white text-[#105E53] py-3 text-xs font-ui uppercase tracking-[0.2em] flex items-center justify-center gap-3 hover:bg-[#105E53]/5 transition"
                    >
                      <GoogleIcon className="w-5 h-5" />
                      Sign up with Google
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

                <div className="flex items-center justify-between text-sm font-ui text-[#105E53]">
                  <Link to="/login" className="hover:text-[#0c4c45]">Already have an account? Login</Link>
                  <Link to="/forgot-password" className="hover:text-[#0c4c45]">Forgot password?</Link>
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
                    checked={guestNewsletter}
                    onChange={(e) => setGuestNewsletter(e.target.checked)}
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

type FieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  disabled?: boolean;
};

function Field({ label, value, onChange, type = 'text', disabled }: FieldProps) {
  return (
    <div className="space-y-2">
      <label className="text-base font-serif text-[#105E53]">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border-0 border-b border-[#105E53] bg-transparent px-0 py-3 text-base font-serif text-[#222424] focus:border-[#105E53] focus:outline-none focus:ring-0"
        required
        disabled={disabled}
      />
    </div>
  );
}

type PasswordFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  showPassword: boolean;
  setShowPassword: (value: boolean) => void;
  disabled?: boolean;
};

function PasswordField({
  label,
  value,
  onChange,
  showPassword,
  setShowPassword,
  disabled,
}: PasswordFieldProps) {
  return (
    <div className="space-y-2">
      <label className="text-base font-serif text-[#105E53]">{label}</label>
      <div className="relative">
        <input
          type={showPassword ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border-0 border-b border-[#105E53] bg-transparent px-0 py-3 pr-10 text-base font-serif text-[#222424] focus:border-[#105E53] focus:outline-none focus:ring-0"
          required
          disabled={disabled}
        />
        <button
          type="button"
          onClick={() => setShowPassword(!showPassword)}
          className="absolute inset-y-0 right-0 flex items-center text-[#105E53] hover:text-[#0c4c45] transition"
          aria-label="Toggle password visibility"
          disabled={disabled}
        >
          {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
    </div>
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

type DatePickerProps = {
  value: string;
  onChange: (value: string) => void;
};

function DatePicker({ value, onChange }: DatePickerProps) {
  const [open, setOpen] = useState(false);
  const selectedParts = useMemo(() => {
    if (!value) return null;
    const [y, m, d] = value.split('-').map(Number);
    if (!y || !m || !d) return null;
    return { year: y, month: m - 1, day: d };
  }, [value]);
  const selectedDate = selectedParts
    ? new Date(Date.UTC(selectedParts.year, selectedParts.month, selectedParts.day))
    : null;
  const [currentMonth, setCurrentMonth] = useState<Date>(selectedDate ?? new Date());

  const daysInMonth = (date: Date) => new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  const startDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), 1).getDay();

  const days = useMemo(() => {
    const total = daysInMonth(currentMonth);
    const offset = startDay(currentMonth);
    return Array.from({ length: offset + total }, (_, idx) => (idx < offset ? null : idx - offset + 1));
  }, [currentMonth]);

  const displayValue =
    selectedParts && selectedDate && !Number.isNaN(selectedDate.getTime())
      ? new Date(Date.UTC(selectedParts.year, selectedParts.month, selectedParts.day)).toLocaleDateString('en-GB', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
        })
      : 'Select date of birth';

  const handleSelectDay = (day: number) => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth() + 1;
    const padded = (n: number) => (n < 10 ? `0${n}` : `${n}`);
    const iso = `${year}-${padded(month)}-${padded(day)}`;
    onChange(iso);
    setOpen(false);
    setCurrentMonth(new Date(year, month - 1, day));
  };

  const prevMonth = () => {
    const next = new Date(currentMonth);
    next.setMonth(currentMonth.getMonth() - 1);
    setCurrentMonth(next);
  };

  const nextMonth = () => {
    const next = new Date(currentMonth);
    next.setMonth(currentMonth.getMonth() + 1);
    setCurrentMonth(next);
  };

  const years = useMemo(() => {
    const currentYear = new Date().getFullYear();
    return Array.from({ length: 100 }, (_, i) => currentYear - i);
  }, []);

  const pickerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div className="relative" ref={pickerRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={`w-full px-0 py-3 text-base font-serif text-left flex items-center justify-between border-0 border-b border-[#105E53] bg-transparent transition focus:outline-none focus:ring-0 ${
          open ? 'border-[#105E53]' : 'hover:border-[#105E53]'
        }`}
      >
        <span className={selectedDate ? 'text-[#222424]' : 'text-[#105E53]/60'}>{displayValue}</span>
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`text-primary transition-transform ${open ? 'rotate-180' : ''}`}
        >
          <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div className="absolute z-20 mt-2 w-full bg-white rounded-2xl shadow-2xl border border-[#105E53]/30 p-4">
          <div className="flex items-center justify-between mb-3 text-sm font-semibold text-[#105E53]">
            <div className="flex items-center gap-2">
              <button onClick={prevMonth} className="p-2 hover:text-[#0c4c45]" type="button" aria-label="Previous month">
                ‹
              </button>
              <select
                value={currentMonth.getMonth()}
                onChange={(e) => {
                  const next = new Date(currentMonth);
                  next.setMonth(Number(e.target.value));
                  setCurrentMonth(next);
                }}
                className="border border-[#105E53]/30 rounded px-2 py-1 text-sm focus:outline-none focus:border-[#105E53]"
              >
                {Array.from({ length: 12 }, (_, i) => (
                  <option key={i} value={i}>
                    {new Date(2000, i, 1).toLocaleDateString('en-US', { month: 'long' })}
                  </option>
                ))}
              </select>
              <select
                value={currentMonth.getFullYear()}
                onChange={(e) => {
                  const next = new Date(currentMonth);
                  next.setFullYear(Number(e.target.value));
                  setCurrentMonth(next);
                }}
                className="border border-[#105E53]/30 rounded px-2 py-1 text-sm focus:outline-none focus:border-[#105E53]"
              >
                {years.map((yr) => (
                  <option key={yr} value={yr}>
                    {yr}
                  </option>
                ))}
              </select>
              <button onClick={nextMonth} className="p-2 hover:text-[#0c4c45]" type="button" aria-label="Next month">
                ›
              </button>
            </div>
          </div>
          <div className="grid grid-cols-7 text-[11px] font-semibold text-[#105E53] mb-2 gap-y-1">
            {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map((d) => (
              <span key={d} className="text-center">
                {d}
              </span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1 text-sm">
            {days.map((day, idx) => {
              if (!day) return <span key={idx} />;
              const isSelected =
                selectedDate &&
                day === selectedDate.getDate() &&
                currentMonth.getMonth() === selectedDate.getMonth() &&
                currentMonth.getFullYear() === selectedDate.getFullYear();
              return (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleSelectDay(day)}
                  className={`h-9 w-9 rounded-full flex items-center justify-center transition ${
                    isSelected ? 'bg-[#105E53] text-white' : 'hover:bg-[#105E53]/10 text-[#105E53]'
                  }`}
                >
                  {day}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
