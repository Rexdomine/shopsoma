import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import { ArrowRight, ChevronDown } from 'lucide-react';

const countryCodes = [
  { label: '+234', value: '+234' },
  { label: '+1', value: '+1' },
  { label: '+44', value: '+44' },
];

export default function VendorSignup() {
  const navigate = useNavigate();
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phoneCode, setPhoneCode] = useState(countryCodes[0].value);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [email, setEmail] = useState('');
  const [codeOpen, setCodeOpen] = useState(false);

  const isValid = firstName.trim() !== '' && lastName.trim() !== '' && phoneNumber.trim() !== '' && email.trim() !== '';

  const handleNext = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    // Pass data to next step via navigation state
    navigate(ROUTES.VENDOR_SIGNUP_BUSINESS, {
      state: {
        firstName,
        lastName,
        phoneCode,
        phoneNumber,
        email,
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
        className="w-full max-w-5xl bg-white/80 border border-gray-200 rounded-[32px] shadow-sm px-8 sm:px-12 py-10 space-y-6"
      >
        <div className="space-y-1 text-left">
          <p className="text-sm text-gray-500 font-ui">Personal Info</p>
          <h3 className="text-2xl font-display text-gray-800">Hello! We would love to know you</h3>
          <p className="text-sm text-gray-600 font-ui">Please fill the information below</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-sm text-gray-700 font-ui">First Name</label>
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="First Name"
              className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              required
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm text-gray-700 font-ui">Last Name</label>
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Last Name"
              className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
              required
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm text-gray-700 font-ui">Phone Number</label>
          <div className="flex rounded-2xl border border-gray-200 bg-white overflow-hidden focus-within:border-[#105E53] focus-within:ring-1 focus-within:ring-[#105E53]/30">
            <div className="relative min-w-[110px] border-r border-gray-200">
              <button
                type="button"
                onClick={() => setCodeOpen((v) => !v)}
                className="w-full h-full px-4 py-3 flex items-center justify-between text-gray-800"
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
              type="tel"
              value={phoneNumber}
              onChange={(e) => setPhoneNumber(e.target.value)}
              placeholder="000 000 000"
              className="flex-1 px-4 py-3 text-gray-800 focus:outline-none"
              required
            />
          </div>
        </div>

        <div className="space-y-2">
          <label className="text-sm text-gray-700 font-ui">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="example@mail.com"
            className="w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-gray-800 focus:outline-none focus:border-[#105E53] focus:ring-1 focus:ring-[#105E53]/30"
            required
          />
        </div>

        <div className="pt-2">
          <button
            type="submit"
            disabled={!isValid}
            className="inline-flex items-center gap-2 rounded-full bg-[#105E53] text-white px-6 py-3 font-ui text-sm tracking-wide disabled:opacity-60"
          >
            Next
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </form>
    </div>
  );
}
