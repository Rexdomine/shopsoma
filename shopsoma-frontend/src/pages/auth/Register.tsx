import { useEffect, useMemo, useRef, useState } from 'react';
import { Eye, EyeOff, AlertCircle } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import Layout from '../../components/layout/Layout';
import { subscribeToNewsletter } from '../../services/newsletterService';
import { ROUTES } from '../../config/constants';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

export const isValidEmail = (email: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

// Password validation rules
export const validatePassword = (password: string) => {
  const rules = {
    minLength: password.length >= 8,
    hasUppercase: /[A-Z]/.test(password),
    hasNumber: /[0-9]/.test(password),
  };
  const isValid = rules.minLength && rules.hasUppercase && rules.hasNumber;
  return { ...rules, isValid };
};

export interface RegisterFormState {
  fullName: string;
  email: string;
  password: string;
  dob: string;
  newsletter: boolean;
}

export interface RegisterFieldErrors {
  fullName?: string;
  email?: string;
  password?: string;
  confirmPassword?: string;
  dob?: string;
}

export const validateRegisterField = (
  field: keyof RegisterFieldErrors,
  form: RegisterFormState,
  confirmPasswordValue: string
): string | undefined => {
  switch (field) {
    case 'fullName': {
      const trimmed = form.fullName.trim();
      if (!trimmed) return 'Full name is required';
      if (trimmed.length < 2) return 'Full name must be at least 2 characters';
      return undefined;
    }
    case 'email': {
      const trimmed = form.email.trim();
      if (!trimmed) return 'Email address is required';
      if (!isValidEmail(trimmed)) return 'Please enter a valid email address';
      return undefined;
    }
    case 'password': {
      if (!form.password) return 'Password is required';
      const validation = validatePassword(form.password);
      if (!validation.isValid) {
        if (!validation.minLength) return 'Password must be at least 8 characters';
        if (!validation.hasUppercase) return 'Password must include at least one uppercase letter';
        if (!validation.hasNumber) return 'Password must include at least one number';
        return 'Password does not meet security requirements';
      }
      return undefined;
    }
    case 'confirmPassword': {
      if (!confirmPasswordValue) return 'Please confirm your password';
      if (confirmPasswordValue !== form.password) return 'Passwords do not match';
      return undefined;
    }
    case 'dob': {
      if (form.dob) {
        const selected = new Date(form.dob);
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        if (selected > today) return 'Date of birth cannot be in the future';
      }
      return undefined;
    }
    default:
      return undefined;
  }
};

export const validateRegisterForm = (
  form: RegisterFormState,
  confirmPasswordValue: string
): RegisterFieldErrors => {
  const errors: RegisterFieldErrors = {};
  const fields: (keyof RegisterFieldErrors)[] = ['fullName', 'email', 'password', 'confirmPassword', 'dob'];
  for (const field of fields) {
    const error = validateRegisterField(field, form, confirmPasswordValue);
    if (error) {
      errors[field] = error;
    }
  }
  return errors;
};

type RegisterLocationState = {
  from?: { pathname?: string };
  prefillEmail?: string;
};

export default function Register() {
  const [form, setForm] = useState<RegisterFormState>({
    fullName: '',
    email: '',
    password: '',
    dob: '',
    newsletter: false,
  });
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<RegisterFieldErrors>({});
  const [touched, setTouched] = useState<Record<keyof RegisterFieldErrors, boolean>>({
    fullName: false,
    email: false,
    password: false,
    confirmPassword: false,
    dob: false,
  });

  const [guestEmail, setGuestEmail] = useState('');
  const [guestNewsletter, setGuestNewsletter] = useState(false);
  const [guestError, setGuestError] = useState('');
  const [guestTouched, setGuestTouched] = useState(false);

  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
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

  const handleFieldChange = (key: keyof RegisterFormState, value: string | boolean) => {
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (touched[key as keyof RegisterFieldErrors] || fieldErrors[key as keyof RegisterFieldErrors]) {
        const err = validateRegisterField(key as keyof RegisterFieldErrors, next, confirmPassword);
        setFieldErrors((e) => ({ ...e, [key]: err }));
      }
      if (key === 'password' && (touched.confirmPassword || fieldErrors.confirmPassword)) {
        const confirmErr = validateRegisterField('confirmPassword', next, confirmPassword);
        setFieldErrors((e) => ({ ...e, confirmPassword: confirmErr }));
      }
      return next;
    });
    if (error) setError('');
  };

  const handleConfirmPasswordChange = (value: string) => {
    setConfirmPassword(value);
    if (touched.confirmPassword || fieldErrors.confirmPassword) {
      const err = validateRegisterField('confirmPassword', form, value);
      setFieldErrors((e) => ({ ...e, confirmPassword: err }));
    }
    if (error) setError('');
  };

  const handleBlur = (field: keyof RegisterFieldErrors) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
    const err = validateRegisterField(field, form, confirmPassword);
    setFieldErrors((prev) => ({ ...prev, [field]: err }));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');

    const allTouched: Record<keyof RegisterFieldErrors, boolean> = {
      fullName: true,
      email: true,
      password: true,
      confirmPassword: true,
      dob: true,
    };
    setTouched(allTouched);

    const errors = validateRegisterForm(form, confirmPassword);
    setFieldErrors(errors);

    if (Object.keys(errors).length > 0) {
      setError('Please fix the errors below to continue');
      return;
    }

    setIsLoading(true);

    try {
      await register({
        full_name: form.fullName.trim(),
        email: form.email.trim(),
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
      setError(apiErrorMessage(err, err?.message || 'Registration failed. Please try again.'));
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
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 flex items-start gap-2 text-left" role="alert">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <span className="text-sm">{error}</span>
                </div>
              )}

              <form onSubmit={handleSubmit} noValidate className="space-y-8 text-left">
                <div className="space-y-6">
                  <Field
                    label="Full Name"
                    value={form.fullName}
                    onChange={(val) => handleFieldChange('fullName', val)}
                    onBlur={() => handleBlur('fullName')}
                    error={fieldErrors.fullName}
                    type="text"
                    disabled={isLoading}
                    required
                    autoComplete="name"
                  />
                  <Field
                    label="Email Address"
                    value={form.email}
                    onChange={(val) => handleFieldChange('email', val)}
                    onBlur={() => handleBlur('email')}
                    error={fieldErrors.email}
                    type="email"
                    disabled={isLoading}
                    required
                    autoComplete="email"
                  />
                  <PasswordField
                    label="Password"
                    value={form.password}
                    onChange={(val) => handleFieldChange('password', val)}
                    onBlur={() => handleBlur('password')}
                    showPassword={showPassword}
                    setShowPassword={setShowPassword}
                    error={fieldErrors.password}
                    disabled={isLoading}
                    required
                    autoComplete="new-password"
                  >
                    <div className="pt-2 space-y-1.5 text-xs font-ui" aria-live="polite">
                      <div
                        className={`flex items-center gap-2 transition-colors ${
                          passwordValidation.minLength ? 'text-emerald-700 font-medium' : 'text-gray-500'
                        }`}
                      >
                        <span className="w-3.5 h-3.5 flex items-center justify-center text-xs">
                          {passwordValidation.minLength ? '✓' : '○'}
                        </span>
                        <span>At least 8 characters</span>
                      </div>
                      <div
                        className={`flex items-center gap-2 transition-colors ${
                          passwordValidation.hasUppercase ? 'text-emerald-700 font-medium' : 'text-gray-500'
                        }`}
                      >
                        <span className="w-3.5 h-3.5 flex items-center justify-center text-xs">
                          {passwordValidation.hasUppercase ? '✓' : '○'}
                        </span>
                        <span>At least one uppercase letter (A-Z)</span>
                      </div>
                      <div
                        className={`flex items-center gap-2 transition-colors ${
                          passwordValidation.hasNumber ? 'text-emerald-700 font-medium' : 'text-gray-500'
                        }`}
                      >
                        <span className="w-3.5 h-3.5 flex items-center justify-center text-xs">
                          {passwordValidation.hasNumber ? '✓' : '○'}
                        </span>
                        <span>At least one number (0-9)</span>
                      </div>
                    </div>
                  </PasswordField>
                  <PasswordField
                    label="Confirm Password"
                    value={confirmPassword}
                    onChange={handleConfirmPasswordChange}
                    onBlur={() => handleBlur('confirmPassword')}
                    showPassword={showConfirmPassword}
                    setShowPassword={setShowConfirmPassword}
                    error={fieldErrors.confirmPassword}
                    disabled={isLoading}
                    required
                    autoComplete="new-password"
                  />
                  <div className="space-y-2">
                    <label className="text-base font-serif text-[#105E53]">Date of Birth</label>
                    <DatePicker
                      value={form.dob}
                      onChange={(val) => handleFieldChange('dob', val)}
                      onBlur={() => handleBlur('dob')}
                      error={fieldErrors.dob}
                      disabled={isLoading}
                    />
                  </div>
                  <label className="inline-flex items-center gap-3 text-sm font-serif text-[#105E53]">
                    <input
                      type="checkbox"
                      checked={form.newsletter}
                      onChange={(e) => handleFieldChange('newsletter', e.target.checked)}
                      disabled={isLoading}
                      className="h-4 w-4 border border-[#105E53] text-[#105E53] focus:ring-[#105E53]"
                    />
                    Register to get style news and exclusive offers.
                  </label>
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full py-4 text-sm font-ui uppercase tracking-[0.24em] bg-[#105E53] text-white hover:bg-[#0c4c45] transition disabled:opacity-60 disabled:cursor-not-allowed"
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

                {/* Social Login - Hidden */}

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

              <form className="space-y-8 text-left" onSubmit={handleGuestSubmit} noValidate>
                <div className="space-y-2">
                  <label htmlFor="guest-email" className="text-base font-serif text-[#105E53]">
                    Email
                  </label>
                  <input
                    id="guest-email"
                    type="email"
                    value={guestEmail}
                    onChange={(e) => handleGuestEmailChange(e.target.value)}
                    onBlur={handleGuestEmailBlur}
                    aria-invalid={Boolean(guestError)}
                    aria-describedby={guestError ? 'guest-email-error' : undefined}
                    className={`w-full border-0 border-b bg-transparent px-0 py-3 text-base font-serif text-[#222424] focus:outline-none focus:ring-0 transition-colors ${
                      guestError
                        ? 'border-red-500 focus:border-red-600'
                        : 'border-[#105E53] focus:border-[#105E53]'
                    }`}
                  />
                  {guestError && (
                    <p id="guest-email-error" className="text-xs font-ui text-red-600">
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
  onBlur?: () => void;
  type?: string;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  autoComplete?: string;
};

function Field({
  label,
  value,
  onChange,
  onBlur,
  type = 'text',
  error,
  disabled,
  required,
  id,
  autoComplete,
}: FieldProps) {
  const inputId = id || `field-${label.toLowerCase().replace(/\s+/g, '-')}`;
  const errorId = `${inputId}-error`;

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="text-base font-serif text-[#105E53] flex items-center justify-between">
        <span>
          {label}
          {required && <span className="text-red-500 ml-1" aria-hidden="true">*</span>}
        </span>
      </label>
      <input
        id={inputId}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        autoComplete={autoComplete}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? errorId : undefined}
        className={`w-full border-0 border-b bg-transparent px-0 py-3 text-base font-serif text-[#222424] focus:outline-none focus:ring-0 transition-colors ${
          error
            ? 'border-red-500 focus:border-red-600'
            : 'border-[#105E53] focus:border-[#105E53]'
        }`}
        disabled={disabled}
      />
      {error && (
        <p id={errorId} className="text-xs font-ui text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}

type PasswordFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  showPassword: boolean;
  setShowPassword: (value: boolean) => void;
  error?: string;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  autoComplete?: string;
  children?: React.ReactNode;
};

function PasswordField({
  label,
  value,
  onChange,
  onBlur,
  showPassword,
  setShowPassword,
  error,
  disabled,
  required,
  id,
  autoComplete,
  children,
}: PasswordFieldProps) {
  const inputId = id || `field-${label.toLowerCase().replace(/\s+/g, '-')}`;
  const errorId = `${inputId}-error`;

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="text-base font-serif text-[#105E53] flex items-center justify-between">
        <span>
          {label}
          {required && <span className="text-red-500 ml-1" aria-hidden="true">*</span>}
        </span>
      </label>
      <div className="relative">
        <input
          id={inputId}
          type={showPassword ? 'text' : 'password'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
          autoComplete={autoComplete}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          className={`w-full border-0 border-b bg-transparent px-0 py-3 pr-10 text-base font-serif text-[#222424] focus:outline-none focus:ring-0 transition-colors ${
            error
              ? 'border-red-500 focus:border-red-600'
              : 'border-[#105E53] focus:border-[#105E53]'
          }`}
          disabled={disabled}
        />
        <button
          type="button"
          onClick={() => setShowPassword(!showPassword)}
          className="absolute inset-y-0 right-0 flex items-center text-[#105E53] hover:text-[#0c4c45] transition p-1"
          aria-label={showPassword ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
          disabled={disabled}
        >
          {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
      {error && (
        <p id={errorId} className="text-xs font-ui text-red-600">
          {error}
        </p>
      )}
      {children}
    </div>
  );
}

type DatePickerProps = {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: string;
  disabled?: boolean;
};

function DatePicker({ value, onChange, onBlur, error, disabled }: DatePickerProps) {
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
    onBlur?.();
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
        onBlur?.();
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open, onBlur]);

  return (
    <div className="relative" ref={pickerRef}>
      <button
        type="button"
        onClick={() => !disabled && setOpen((prev) => !prev)}
        disabled={disabled}
        aria-invalid={Boolean(error)}
        className={`w-full px-0 py-3 text-base font-serif text-left flex items-center justify-between border-0 border-b bg-transparent transition focus:outline-none focus:ring-0 ${
          error
            ? 'border-red-500 focus:border-red-600'
            : open
            ? 'border-[#105E53]'
            : 'border-[#105E53] hover:border-[#105E53]'
        } ${disabled ? 'cursor-not-allowed opacity-60' : ''}`}
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

      {error && (
        <p className="text-xs font-ui text-red-600 mt-1">
          {error}
        </p>
      )}

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
