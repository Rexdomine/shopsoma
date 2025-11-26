import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarDays, ChevronDown } from 'lucide-react';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';

type ViewMode = 'list' | 'empty' | 'formStep1' | 'formStep2';

const mockReturns = [
  { id: '1', product: 'Twisted-Seam Striped Shirt', orderId: 'AD11234740', date: '01 - Jan - 2023', amount: 40000, reason: 'Received Wrong Item', status: 'submitted' },
  { id: '2', product: 'Twisted-Seam Striped Shirt', orderId: 'AD11234740', date: '01 - Jan - 2023', amount: 40000, reason: 'Received Wrong Item', status: 'approved' },
  { id: '3', product: 'Twisted-Seam Striped Shirt', orderId: 'AD11234740', date: '01 - Jan - 2023', amount: 40000, reason: 'Received Wrong Item', status: 'denied' },
];

export default function ProfileReturns() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<ViewMode>('list');
  const [returns] = useState(mockReturns);
  const [toastVisible, setToastVisible] = useState(false);

  const menuItems = [
    { label: 'Account Details', route: ROUTES.PROFILE },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
    { label: 'Return', route: ROUTES.PROFILE_RETURNS, active: true },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
    { label: 'Sign Out' },
  ];

  const handleReturnSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 4000);
    setTimeout(() => setMode('list'), 800);
  };

  const renderListView = () => (
    <>
      <header className="mb-8 flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Return</p>
        <button
          type="button"
          onClick={() => setMode('formStep1')}
          className="px-5 py-2 bg-primary text-white text-xs font-semibold uppercase tracking-[0.3em] rounded-sm hover:bg-primary-dark transition"
        >
          Request Return
        </button>
      </header>
      {mockReturns.length === 0 ? (
        <div className="max-w-md mx-auto py-12 px-6 text-center space-y-4">
          <div className="mx-auto w-12 h-12 flex items-center justify-center rounded-full bg-primary/10 text-primary text-xl">!</div>
          <div>
            <p className="text-sm font-semibold text-gray-800">You currently have no return requests</p>
            <p className="text-xs text-gray-500 mt-1">Once you make a return request, you can track it here.</p>
          </div>
          <button
            type="button"
            onClick={() => navigate(ROUTES.HOME)}
            className="px-6 py-3 rounded-sm bg-primary text-white text-sm font-semibold hover:bg-primary-dark transition"
          >
            Go to Shop
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {returns.map((item) => (
            <div key={item.id} className="border border-gray-200 rounded-sm p-8 space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 text-sm text-gray-700">
                <div>
                  <p className="font-semibold text-gray-900">
                    Product Name <span className="font-normal">{item.product}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Order Date <span className="font-normal">{item.date}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Quantity <span className="font-normal">1</span>
                  </p>
                  <span className={`inline-flex mt-3 px-3 py-1 rounded-sm text-xs font-semibold ${getReturnStatusStyles(item.status)}`}>
                    {item.status}
                  </span>
                </div>
                <div>
                  <p className="font-semibold text-gray-900">
                    Order ID <span className="font-normal">{item.orderId}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Amount <span className="font-normal">₦{item.amount.toLocaleString()}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Reason <span className="font-normal">{item.reason}</span>
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 justify-start">
                <button className="px-6 py-2 border border-primary text-primary text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-primary hover:text-white transition">
                  View Details
                </button>
                {item.status !== 'denied' && (
                  <button className="px-6 py-2 border border-gray-400 text-gray-600 text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-gray-100 transition">
                    {item.status === 'submitted' ? 'Edit Return Request' : 'Shipping Instructions'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );

  const renderFormStep1 = () => (
    <>
      <header className="mb-8 flex items-center gap-4">
        <button type="button" onClick={() => setMode('list')} className="text-primary text-xl" aria-label="Go back">
          ←
        </button>
        <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Request return</p>
      </header>
      <form className="space-y-6 max-w-3xl">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <InputField label="First Name" defaultValue="Evidence" />
          <InputField label="Last Name" defaultValue="Uwangue" />
        </div>
        <InputField label="Email Address" defaultValue="uwanguevidence@gmail.com" />
        <InputField label="Phone Number" defaultValue="+234 813 602 4753" />
        <InputField label="Product Name" defaultValue="Twisted - Seam Striped Shirt" />
        <InputField label="Order ID" defaultValue="AD11234740" />
        <DateField label="Order Date" defaultValue="2023-01-01" />
        <div className="flex gap-4 pt-4">
          <button type="button" onClick={() => setMode('list')} className="flex-1 border border-primary text-primary font-semibold rounded-sm py-3 hover:bg-primary hover:text-white transition">
            Back
          </button>
          <button type="button" onClick={() => setMode('formStep2')} className="flex-1 bg-primary text-white font-semibold rounded-sm py-3 hover:bg-primary-dark transition">
            Next
          </button>
        </div>
      </form>
    </>
  );

  const renderFormStep2 = () => (
    <>
      <header className="mb-8 flex items-center gap-4">
        <button type="button" onClick={() => setMode('formStep1')} className="text-primary text-xl" aria-label="Go back">
          ←
        </button>
        <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Request return</p>
      </header>
      <form className="space-y-6 max-w-3xl" onSubmit={handleReturnSubmit}>
        <InputField label="Product Name" defaultValue="Aduke Jetson" />
        <InputField label="Model" defaultValue="Twisted - Seam Striped Shirt" />
        <InputField label="Quantity" defaultValue="1" />
        <SelectField label="Reason" options={['Received Wrong Item', 'Damaged Item', 'Changed Mind']} defaultValue="Received Wrong Item" />
        <SelectField label="Opened" options={['Unopened', 'Opened']} defaultValue="Unopened" />
        <SelectField label="Return Action" options={['Refund', 'Replacement']} defaultValue="Refund" />
        <TextAreaField label="Faulty or other details" placeholder="Faulty or other detail" />
        <div className="flex gap-4 pt-4">
          <button type="button" onClick={() => setMode('formStep1')} className="flex-1 border border-primary text-primary font-semibold rounded-sm py-3 hover:bg-primary hover:text-white transition">
            Back
          </button>
          <button type="submit" className="flex-1 bg-primary text-white font-semibold rounded-sm py-3 hover:bg-primary-dark transition">
            Submit
          </button>
        </div>
      </form>
    </>
  );

  return (
    <Layout>
      {toastVisible && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            <p className="font-semibold uppercase tracking-[0.3em]">Return request</p>
            <p className="text-white/90">Return submitted successfully</p>
          </div>
        </div>
      )}
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />
          <section className="flex-1">
            {mode === 'formStep1'
              ? renderFormStep1()
              : mode === 'formStep2'
                ? renderFormStep2()
                : renderListView()}
          </section>
        </div>
      </div>
    </Layout>
  );
}

function getReturnStatusStyles(status: string): string {
  switch (status) {
    case 'submitted':
      return 'bg-amber-50 text-amber-700 border border-amber-200';
    case 'approved':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    case 'denied':
      return 'bg-red-50 text-red-700 border border-red-200';
    default:
      return 'bg-gray-100 text-gray-600 border border-gray-200';
  }
}

interface InputFieldProps {
  label: string;
  defaultValue?: string;
}

function InputField({ label, defaultValue }: InputFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <input type="text" defaultValue={defaultValue} className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary" />
    </div>
  );
}

interface SelectFieldProps {
  label: string;
  options: string[];
  defaultValue?: string;
}

function SelectField({ label, options, defaultValue }: SelectFieldProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(defaultValue ?? options[0] ?? '');
  const selectRef = useRef<HTMLDivElement | null>(null);
  const inputName = label.toLowerCase().replace(/\s+/g, '-');

  useEffect(() => {
    if (defaultValue) {
      setValue(defaultValue);
    }
  }, [defaultValue]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (selectRef.current && !selectRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  return (
    <div className="space-y-1" ref={selectRef}>
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          className={`w-full border rounded-sm px-3 py-2 text-sm flex items-center justify-between transition focus:outline-none ${
            open ? 'border-primary' : 'border-gray-300 hover:border-primary/70'
          }`}
        >
          <span className={value ? 'text-gray-900' : 'text-gray-400'}>{value || 'Select option'}</span>
          <ChevronDown className={`w-4 h-4 text-primary transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        <input type="hidden" value={value} name={inputName} readOnly />
        {open && (
          <div className="absolute z-20 mt-1 w-full border border-gray-200 bg-white shadow-2xl rounded-sm">
            {options.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setValue(option);
                  setOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-sm transition ${
                  option === value ? 'bg-primary/10 text-primary font-semibold' : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface TextAreaFieldProps {
  label: string;
  placeholder?: string;
}

function TextAreaField({ label, placeholder }: TextAreaFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <textarea placeholder={placeholder} rows={4} className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary"></textarea>
    </div>
  );
}

interface DateFieldProps {
  label: string;
  defaultValue?: string;
}

function DateField({ label, defaultValue = '' }: DateFieldProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(defaultValue);
  const inputName = label.toLowerCase().replace(/\s+/g, '-');

  const selectedParts = useMemo(() => {
    if (!value) return null;
    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) return null;
    return { year, month: month - 1, day };
  }, [value]);

  const selectedDate = selectedParts ? new Date(selectedParts.year, selectedParts.month, selectedParts.day) : null;
  const [currentMonth, setCurrentMonth] = useState<Date>(selectedDate ?? new Date());

  useEffect(() => {
    setValue(defaultValue);
    if (defaultValue) {
      const next = new Date(defaultValue);
      if (!Number.isNaN(next.getTime())) {
        setCurrentMonth(next);
      }
    }
  }, [defaultValue]);

  const daysInMonth = (date: Date) => new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate();
  const startDay = (date: Date) => new Date(date.getFullYear(), date.getMonth(), 1).getDay();

  const days = useMemo(() => {
    const total = daysInMonth(currentMonth);
    const offset = startDay(currentMonth);
    return Array.from({ length: offset + total }, (_, idx) => (idx < offset ? null : idx - offset + 1));
  }, [currentMonth]);

  const displayValue =
    selectedDate && !Number.isNaN(selectedDate.getTime())
      ? selectedDate.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
      : 'Select order date';

  const handleSelectDay = (day: number) => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth() + 1;
    const padded = (n: number) => (n < 10 ? `0${n}` : `${n}`);
    const iso = `${year}-${padded(month)}-${padded(day)}`;
    setValue(iso);
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
    return Array.from({ length: 15 }, (_, idx) => currentYear - idx);
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
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <div className="relative" ref={pickerRef}>
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          className={`w-full border rounded-sm px-3 py-2 text-sm flex items-center justify-between transition focus:outline-none ${
            open ? 'border-primary' : 'border-gray-300 hover:border-primary/70'
          }`}
        >
          <span className={selectedDate ? 'text-gray-900' : 'text-gray-400'}>{displayValue}</span>
          <CalendarDays className="w-4 h-4 text-primary" />
        </button>
        <input type="hidden" value={value} name={inputName} readOnly />
        {open && (
          <div className="absolute z-20 mt-2 w-full rounded-sm border border-gray-200 bg-white shadow-2xl p-4">
            <div className="flex items-center justify-between mb-3 text-xs font-semibold text-gray-600 uppercase tracking-[0.3em]">
              <button type="button" onClick={prevMonth} aria-label="Previous month" className="text-lg hover:text-primary">
                ‹
              </button>
              <div className="flex items-center gap-2 normal-case tracking-normal">
                <select
                  value={currentMonth.getMonth()}
                  onChange={(e) => {
                    const next = new Date(currentMonth);
                    next.setMonth(Number(e.target.value));
                    setCurrentMonth(next);
                  }}
                  className="border border-gray-300 rounded-sm px-2 py-1 text-xs focus:outline-none focus:border-primary"
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
                  className="border border-gray-300 rounded-sm px-2 py-1 text-xs focus:outline-none focus:border-primary"
                >
                  {years.map((yr) => (
                    <option key={yr} value={yr}>
                      {yr}
                    </option>
                  ))}
                </select>
              </div>
              <button type="button" onClick={nextMonth} aria-label="Next month" className="text-lg hover:text-primary">
                ›
              </button>
            </div>
            <div className="grid grid-cols-7 text-[10px] uppercase tracking-[0.3em] text-gray-400 mb-1">
              {['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'].map((day) => (
                <span key={day} className="text-center">
                  {day}
                </span>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1 text-xs">
              {days.map((day, idx) =>
                day ? (
                  <button
                    key={`${day}-${idx}`}
                    type="button"
                    onClick={() => handleSelectDay(day)}
                    className={`h-8 w-full rounded-sm border text-center font-semibold transition ${
                      selectedDate &&
                      day === selectedDate.getDate() &&
                      currentMonth.getMonth() === selectedDate.getMonth() &&
                      currentMonth.getFullYear() === selectedDate.getFullYear()
                        ? 'bg-primary text-white border-primary'
                        : 'border-transparent text-gray-700 hover:border-gray-200'
                    }`}
                  >
                    {day}
                  </button>
                ) : (
                  <span key={idx} className="h-8 block" />
                ),
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
