import { useState, useRef, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import { ArrowRight, ChevronDown, AlertCircle } from 'lucide-react';

const countryCodes = [
  { label: '+234', value: '+234' },
  { label: '+1', value: '+1' },
  { label: '+44', value: '+44' },
];

export default function VendorSignup() {
  const navigate = useNavigate();
  const location = useLocation();
  const preloaded = (location.state as any) || {};

  const [firstName, setFirstName] = useState(preloaded.firstName || '');
  const [lastName, setLastName] = useState(preloaded.lastName || '');
  const [phoneCode, setPhoneCode] = useState(preloaded.phoneCode || countryCodes[0].value);
  const [phoneNumber, setPhoneNumber] = useState(preloaded.phoneNumber || '');
  const [email, setEmail] = useState(preloaded.email || '');
  const [codeOpen, setCodeOpen] = useState(false);

  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);

  const firstNameRef = useRef<HTMLInputElement>(null);
  const lastNameRef = useRef<HTMLInputElement>(null);
  const phoneRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  // Field validation rules
  const errors = useMemo(() => {
    const errs: Record<string, string> = {};

    if (!firstName.trim()) {
      errs.firstName = 'First name is required';
    } else if (firstName.trim().length < 2) {
      errs.firstName = 'First name must be at least 2 characters';
    }

    if (!lastName.trim()) {
      errs.lastName = 'Last name is required';
    } else if (lastName.trim().length < 2) {
      errs.lastName = 'Last name must be at least 2 characters';
    }

    const digitsOnly = phoneNumber.replace(/\D/g, '');
    if (!phoneNumber.trim()) {
      errs.phoneNumber = 'Phone number is required';
    } else if (digitsOnly.length < 7 || digitsOnly.length > 15) {
      errs.phoneNumber = 'Please enter a valid phone number (7-15 digits)';
    }

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email.trim()) {
      errs.email = 'Email address is required';
    } else if (!emailRegex.test(email.trim())) {
      errs.email = 'Please enter a valid email address (e.g. name@example.com)';
    }

    return errs;
  }, [firstName, lastName, phoneNumber, email]);

  const hasErrors = Object.keys(errors).length > 0;

  const handleBlur = (field: string) => {
    setTouched((prev) => ({ ...prev, [field]: true }));
  };

  const handleNext = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitAttempted(true);
    setTouched({
      firstName: true,
      lastName: true,
      phoneNumber: true,
      email: true,
    });

    if (hasErrors) {
      // Focus the first invalid field
      if (errors.firstName) {
        firstNameRef.current?.focus();
      } else if (errors.lastName) {
        lastNameRef.current?.focus();
      } else if (errors.phoneNumber) {
        phoneRef.current?.focus();
      } else if (errors.email) {
        emailRef.current?.focus();
      }
      return;
    }

    // Pass validated data to next step via navigation state
    navigate(ROUTES.VENDOR_SIGNUP_BUSINESS, {
      state: {
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        phoneCode,
        phoneNumber: phoneNumber.trim(),
        email: email.trim().toLowerCase(),
      },
    });
  };

  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] px-6 py-12 flex flex-col items-center">
      <div className="flex flex-col items-center gap-6 mt-6 mb-10 text-center">
        <img src="/images/somalogo.svg" alt="Shopsoma" className="h-10 w-auto" />
        <div className="space-y-1">
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-display text-[#105E53]">Wanna join the Shopsoma Family?</h1>
          <h2 className="text-2xl sm:text-3xl md:text-4xl font-display text-[#105E53]">Sign up below!</h2>
        </div>
      </div>

      <form
        onSubmit={handleNext}
        noValidate
        className="w-full max-w-5xl bg-white/80 border border-gray-200 rounded-[32px] shadow-sm px-8 sm:px-12 py-10 space-y-6"
      >
        <div className="space-y-1 text-left">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-500 font-ui font-medium">Personal Info</p>
            <span className="text-xs font-semibold px-3 py-1 rounded-full bg-[#105E53]/10 text-[#105E53] font-ui">
              Step 1 of 2
            </span>
          </div>
          <h3 className="text-2xl font-display text-gray-800">Hello! We would love to know you</h3>
          <p className="text-sm text-gray-600 font-ui">Please fill in the information below to begin your vendor registration</p>
        </div>

        {/* Validation Summary Alert */}
        {submitAttempted && hasErrors && (
          <div
            role="alert"
            className="bg-red-50 border border-red-200 text-red-700 px-5 py-3.5 rounded-2xl flex items-start gap-3 text-sm font-ui animate-in fade-in duration-150"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0 text-red-500 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold text-red-800">Please fill in all required fields:</p>
              <ul className="list-disc list-inside text-xs text-red-600 space-y-0.5">
                {Object.values(errors).map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label htmlFor="firstName" className="text-sm text-gray-700 font-ui font-medium">
              First Name <span className="text-red-500">*</span>
            </label>
            <input
              id="firstName"
              ref={firstNameRef}
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              onBlur={() => handleBlur('firstName')}
              placeholder="First Name"
              aria-invalid={!!((touched.firstName || submitAttempted) && errors.firstName)}
              aria-describedby={(touched.firstName || submitAttempted) && errors.firstName ? 'firstName-error' : undefined}
              className={`w-full rounded-2xl border bg-white px-4 py-3 text-gray-800 focus:outline-none transition ${
                (touched.firstName || submitAttempted) && errors.firstName
                  ? 'border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-200 bg-red-50/20'
                  : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
              }`}
            />
            {(touched.firstName || submitAttempted) && errors.firstName && (
              <p id="firstName-error" className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.firstName}</span>
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <label htmlFor="lastName" className="text-sm text-gray-700 font-ui font-medium">
              Last Name <span className="text-red-500">*</span>
            </label>
            <input
              id="lastName"
              ref={lastNameRef}
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              onBlur={() => handleBlur('lastName')}
              placeholder="Last Name"
              aria-invalid={!!((touched.lastName || submitAttempted) && errors.lastName)}
              aria-describedby={(touched.lastName || submitAttempted) && errors.lastName ? 'lastName-error' : undefined}
              className={`w-full rounded-2xl border bg-white px-4 py-3 text-gray-800 focus:outline-none transition ${
                (touched.lastName || submitAttempted) && errors.lastName
                  ? 'border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-200 bg-red-50/20'
                  : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
              }`}
            />
            {(touched.lastName || submitAttempted) && errors.lastName && (
              <p id="lastName-error" className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                <span>{errors.lastName}</span>
              </p>
            )}
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="phoneNumber" className="text-sm text-gray-700 font-ui font-medium">
            Phone Number <span className="text-red-500">*</span>
          </label>
          <div
            className={`flex rounded-2xl border bg-white overflow-hidden transition focus-within:ring-1 ${
              (touched.phoneNumber || submitAttempted) && errors.phoneNumber
                ? 'border-red-400 focus-within:border-red-500 focus-within:ring-red-200 bg-red-50/20'
                : 'border-gray-200 focus-within:border-[#105E53] focus-within:ring-[#105E53]/30'
            }`}
          >
            <div className="relative min-w-[110px] border-r border-gray-200">
              <button
                type="button"
                onClick={() => setCodeOpen((v) => !v)}
                className="w-full h-full px-4 py-3 flex items-center justify-between text-gray-800"
                aria-label="Select country code"
              >
                <span>{phoneCode}</span>
                <ChevronDown className="h-4 w-4 text-gray-500" />
              </button>
              {codeOpen && (
                <div className="absolute z-20 top-full left-0 mt-1 w-full rounded-xl border border-gray-200 bg-white shadow-lg">
                  {countryCodes.map((code) => (
                    <button
                      key={code.value}
                      type="button"
                      onClick={() => {
                        setPhoneCode(code.value);
                        setCodeOpen(false);
                      }}
                      className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 ${
                        code.value === phoneCode ? 'text-[#105E53] font-semibold' : 'text-gray-700'
                      }`}
                    >
                      {code.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <input
              id="phoneNumber"
              ref={phoneRef}
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              onBlur={() => handleBlur('phoneNumber')}
              placeholder="000 000 0000"
              aria-invalid={!!((touched.phoneNumber || submitAttempted) && errors.phoneNumber)}
              aria-describedby={(touched.phoneNumber || submitAttempted) && errors.phoneNumber ? 'phoneNumber-error' : undefined}
              className="flex-1 px-4 py-3 text-gray-800 focus:outline-none bg-transparent"
            />
          </div>
          {(touched.phoneNumber || submitAttempted) && errors.phoneNumber && (
            <p id="phoneNumber-error" className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.phoneNumber}</span>
            </p>
          )}
        </div>

        <div className="space-y-1.5">
          <label htmlFor="email" className="text-sm text-gray-700 font-ui font-medium">
            Email <span className="text-red-500">*</span>
          </label>
          <input
            id="email"
            ref={emailRef}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => handleBlur('email')}
            placeholder="example@mail.com"
            aria-invalid={!!((touched.email || submitAttempted) && errors.email)}
            aria-describedby={(touched.email || submitAttempted) && errors.email ? 'email-error' : undefined}
            className={`w-full rounded-2xl border bg-white px-4 py-3 text-gray-800 focus:outline-none transition ${
              (touched.email || submitAttempted) && errors.email
                ? 'border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-200 bg-red-50/20'
                : 'border-gray-200 focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30'
            }`}
          />
          {(touched.email || submitAttempted) && errors.email && (
            <p id="email-error" className="text-xs text-red-600 flex items-center gap-1 font-ui mt-1">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errors.email}</span>
            </p>
          )}
        </div>

        <div className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-gray-100">
          <p className="text-xs text-gray-500 font-ui">
            * All fields are required
          </p>
          <button
            type="submit"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-full bg-[#105E53] hover:bg-[#0c4c45] active:bg-[#093c35] text-white px-8 py-3.5 font-ui text-sm font-medium tracking-wide transition shadow-sm hover:shadow cursor-pointer"
          >
            <span>Next: Business Information</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
