import { useEffect, useMemo, useRef, useState } from 'react';
import { Eye, EyeOff, AlertCircle, CheckCircle } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Layout from '../../components/layout/Layout';
import Newsletter from '../../components/home/Newsletter';
import { subscribeToNewsletter } from '../../services/newsletterService';

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

export default function Register() {
  const [form, setForm] = useState({
    fullName: '',
    email: '',
    password: '',
    dob: '',
    newsletter: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { register } = useAuth();
  const navigate = useNavigate();

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

      // Redirect to home after successful registration
      navigate('/', { replace: true });
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Layout>
      <section className="bg-white py-10 lg:py-16">
        <div className="max-w-xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-8">
          <h1 className="text-2xl font-display text-dark">Register</h1>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-sm flex items-start gap-2 text-left">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
              <span className="text-sm">{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5 text-left">
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700">Full Name</label>
              <input
                type="text"
                value={form.fullName}
                onChange={(e) => handleChange('fullName', e.target.value)}
                className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="Enter full name"
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700">Email Address</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => handleChange('email', e.target.value)}
                className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:border-primary focus:outline-none"
                placeholder="Enter email address"
                required
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={form.password}
                  onChange={(e) => handleChange('password', e.target.value)}
                  className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:border-primary focus:outline-none pr-10"
                  placeholder="Enter a secured P@ssw0rd"
                  required
                  disabled={isLoading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  className="absolute inset-y-0 right-2 flex items-center text-gray-500 hover:text-gray-700"
                  aria-label="Toggle password visibility"
                  disabled={isLoading}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {form.password && (
                <div className="space-y-1 text-xs">
                  <div className={`flex items-center gap-1 ${passwordValidation.minLength ? 'text-green-600' : 'text-gray-500'}`}>
                    {passwordValidation.minLength ? <CheckCircle className="w-3 h-3" /> : <span className="w-3 h-3 rounded-full border border-current" />}
                    <span>At least 8 characters</span>
                  </div>
                  <div className={`flex items-center gap-1 ${passwordValidation.hasUppercase ? 'text-green-600' : 'text-gray-500'}`}>
                    {passwordValidation.hasUppercase ? <CheckCircle className="w-3 h-3" /> : <span className="w-3 h-3 rounded-full border border-current" />}
                    <span>One uppercase letter</span>
                  </div>
                  <div className={`flex items-center gap-1 ${passwordValidation.hasNumber ? 'text-green-600' : 'text-gray-500'}`}>
                    {passwordValidation.hasNumber ? <CheckCircle className="w-3 h-3" /> : <span className="w-3 h-3 rounded-full border border-current" />}
                    <span>One number</span>
                  </div>
                </div>
              )}
            </div>
            <div className="space-y-2">
              <label className="text-sm font-semibold text-gray-700">Date of birth</label>
              <DatePicker
                value={form.dob}
                onChange={(val) => handleChange('dob', val)}
              />
            </div>
            <label className="inline-flex items-center gap-2 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={form.newsletter}
                onChange={(e) => handleChange('newsletter', e.target.checked)}
                className="h-4 w-4 border-gray-400"
              />
              Register to get style news and exclusive offers.
            </label>
            <p className="text-xs text-gray-600">
              By signing up you agree to the <a href="#" className="text-primary">Terms of Service</a>.
            </p>
            <button
              type="submit"
              disabled={!isComplete || isLoading}
              className={`w-full py-3 rounded-sm text-sm font-semibold transition ${
                isComplete && !isLoading
                  ? 'bg-primary text-white hover:bg-primary-dark'
                  : 'bg-gray-200 text-gray-500 cursor-not-allowed'
              }`}
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                  Creating account...
                </span>
              ) : (
                'Create Account'
              )}
            </button>
            <div className="text-center text-sm text-gray-600 space-y-2">
              <p>Account already exists?</p>
              <Link
                to="/login"
                className="inline-block w-full py-2.5 rounded-sm border border-primary text-primary font-semibold hover:bg-primary hover:text-white transition"
              >
                Sign In
              </Link>
            </div>
          </form>
        </div>
      </section>
      <Newsletter />
    </Layout>
  );
}

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
        className={`w-full rounded-md px-4 py-3 text-sm text-left flex items-center justify-between border-2 transition focus:outline-none focus:ring-2 focus:ring-primary/10 ${
          open ? 'border-primary' : 'border-gray-200 hover:border-primary/70'
        }`}
      >
        <span className={selectedDate ? 'text-gray-900' : 'text-gray-400'}>{displayValue}</span>
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
        <div className="absolute z-20 mt-2 w-full bg-white rounded-2xl shadow-2xl border border-gray-200 p-4">
          <div className="flex items-center justify-between mb-3 text-sm font-semibold text-gray-800">
            <div className="flex items-center gap-2">
              <button onClick={prevMonth} className="p-2 hover:text-primary" type="button" aria-label="Previous month">
                ‹
              </button>
              <select
                value={currentMonth.getMonth()}
                onChange={(e) => {
                  const next = new Date(currentMonth);
                  next.setMonth(Number(e.target.value));
                  setCurrentMonth(next);
                }}
                className="border border-gray-200 rounded px-2 py-1 text-sm focus:outline-none focus:border-primary"
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
                className="border border-gray-200 rounded px-2 py-1 text-sm focus:outline-none focus:border-primary"
              >
                {years.map((yr) => (
                  <option key={yr} value={yr}>
                    {yr}
                  </option>
                ))}
              </select>
              <button onClick={nextMonth} className="p-2 hover:text-primary" type="button" aria-label="Next month">
                ›
              </button>
            </div>
          </div>
          <div className="grid grid-cols-7 text-[11px] font-semibold text-gray-500 mb-2 gap-y-1">
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
                    isSelected ? 'bg-primary text-white' : 'hover:bg-gray-100'
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
