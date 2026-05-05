import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { CalendarDays, ChevronDown } from 'lucide-react';
import Layout from '../../components/layout/Layout';
import { ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { useAuth } from '../../context/AuthContext';
import { userService } from '../../services/userService';
import type { Order as UserOrder } from '../../services/userService';
import type { ReturnRequest } from '../../services/userService';

type ViewMode = 'list' | 'empty' | 'formStep1' | 'formStep2';

export default function ProfileReturns() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<ViewMode>('list');
  const [returns, setReturns] = useState<ReturnRequest[]>([]);
  const [returnsLoading, setReturnsLoading] = useState(false);
  const [submittingReturn, setSubmittingReturn] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const [toastMessage, setToastMessage] = useState('Return submitted successfully');
  const [toastTone, setToastTone] = useState<'success' | 'error'>('success');
  const { user, updateUser } = useAuth();
  const [orders, setOrders] = useState<UserOrder[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(false);
  const [selectedOrderNumber, setSelectedOrderNumber] = useState('');
  const [selectedProductId, setSelectedProductId] = useState('');
  const [reason, setReason] = useState('Received Wrong Item');
  const [opened, setOpened] = useState('Unopened');
  const [returnAction, setReturnAction] = useState('Refund');
  const [details, setDetails] = useState('');
  const [formProfile, setFormProfile] = useState({
    firstName: '',
    lastName: '',
    email: '',
    phone: '',
  });

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

  const handleReturnSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submittingReturn || !selectedOrder || !selectedProductId) return;

    try {
      setSubmittingReturn(true);
      const newReturn = await userService.createReturn({
        order_id: selectedOrder.id,
        order_item_id: selectedProductId,
        reason,
        opened,
        return_action: returnAction,
        description: details,
      });
      setReturns((prev) => [newReturn, ...prev]);
      setToastMessage('Return submitted successfully');
      setToastTone('success');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
      setMode('list');
      setSelectedOrderNumber('');
      setSelectedProductId('');
      setDetails('');
    } catch (error) {
      console.error('Failed to submit return', error);
      setToastMessage('Failed to submit return request');
      setToastTone('error');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
    } finally {
      setSubmittingReturn(false);
    }
  };

  useEffect(() => {
    let isMounted = true;

    const applyProfile = (profile: typeof user) => {
      if (!profile) return;
      const fullName = profile.full_name?.trim() || '';
      const [first = '', ...rest] = fullName.split(' ');
      setFormProfile({
        firstName: first,
        lastName: rest.join(' '),
        email: profile.email || '',
        phone: profile.phone_number || '',
      });
    };

    if (user && user.phone_number) {
      applyProfile(user);
      return () => {
        isMounted = false;
      };
    }

    const loadProfile = async () => {
      try {
        const profile = await userService.getProfile();
        if (!isMounted) return;
        updateUser(profile);
        applyProfile(profile);
      } catch (error) {
        console.error('Failed to load profile for return request', error);
      }
    };

    loadProfile();

    return () => {
      isMounted = false;
    };
  }, [user, updateUser]);

  useEffect(() => {
    let isMounted = true;
    const loadOrders = async () => {
      try {
        setOrdersLoading(true);
        const response = await userService.getOrders(1, 50);
        if (!isMounted) return;
        setOrders(response.orders || []);
      } catch (error) {
        console.error('Failed to load orders', error);
        if (isMounted) setOrders([]);
      } finally {
        if (isMounted) setOrdersLoading(false);
      }
    };

    loadOrders();
    return () => {
      isMounted = false;
    };
  }, []);

  useEffect(() => {
    let isMounted = true;
    const loadReturns = async () => {
      try {
        setReturnsLoading(true);
        const response = await userService.getReturns();
        if (!isMounted) return;
        setReturns(response || []);
      } catch (error) {
        console.error('Failed to load returns', error);
        if (isMounted) setReturns([]);
      } finally {
        if (isMounted) setReturnsLoading(false);
      }
    };

    loadReturns();
    return () => {
      isMounted = false;
    };
  }, []);

  const orderOptions = useMemo(() => {
    const options = orders.map((order) => order.order_number || order.id);
    return Array.from(new Set(options)).filter(Boolean);
  }, [orders]);

  const selectedOrder = useMemo(
    () => orders.find((order) => (order.order_number || order.id) === selectedOrderNumber) || null,
    [orders, selectedOrderNumber]
  );

  const parseOrderItems = (
    order: UserOrder & { order_content?: string }
  ): Array<{ id: string; label: string; image?: string; quantity?: number; amount?: number }> => {
    const orderItems = (order as any).items as Array<any> | undefined;
    if (Array.isArray(orderItems) && orderItems.length) {
      return orderItems
        .map((item) => ({
          id: item?.id || '',
          label: item?.product_title || item?.title || item?.name || item?.product_name || '',
          image: item?.product_image_url || '',
          quantity: item?.quantity || 1,
          amount: item?.subtotal ?? item?.total ?? item?.amount ?? 0,
        }))
        .filter((item) => item.label && item.id);
    }
    if (!order.order_content) return [];
    try {
      const parsed = JSON.parse(order.order_content);
      const items = parsed?.items || parsed?.order_items || parsed?.cart_items || parsed?.products || [];
      if (!Array.isArray(items)) return [];
      return items
        .map((item: any) => ({
          id: item?.id || item?.product_id || '',
          label: item?.product_title || item?.title || item?.name || item?.product_name || '',
          image: item?.image_url || item?.product_image_url || '',
          quantity: item?.quantity || 1,
          amount: item?.subtotal ?? item?.total ?? item?.amount ?? 0,
        }))
        .filter((item) => item.label && item.id);
    } catch {
      return [];
    }
  };

  const productOptions = useMemo(() => {
    if (!selectedOrder) return [];
    return parseOrderItems(selectedOrder);
  }, [selectedOrder]);

  useEffect(() => {
    if (!selectedOrderNumber && orderOptions.length) {
      setSelectedOrderNumber(orderOptions[0]);
    }
  }, [orderOptions, selectedOrderNumber]);

  useEffect(() => {
    if (productOptions.length) {
      setSelectedProductId(productOptions[0].id);
    } else {
      setSelectedProductId('');
    }
  }, [productOptions]);

  const selectedProduct = useMemo(
    () => productOptions.find((option) => option.id === selectedProductId) || null,
    [productOptions, selectedProductId]
  );

  const displayStatus = (status: string) => {
    switch (status) {
      case 'requested':
        return 'submitted';
      case 'rejected':
        return 'denied';
      default:
        return status;
    }
  };

  const selectedOrderDate = useMemo(() => {
    if (!selectedOrder?.created_at) return '';
    const date = new Date(selectedOrder.created_at);
    if (Number.isNaN(date.getTime())) return '';
    const year = date.getFullYear();
    const month = `${date.getMonth() + 1}`.padStart(2, '0');
    const day = `${date.getDate()}`.padStart(2, '0');
    return `${year}-${month}-${day}`;
  }, [selectedOrder]);

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
      {returnsLoading || returns.length === 0 ? (
        <div className="max-w-md mx-auto py-12 px-6 text-center space-y-4">
          <div className="mx-auto w-12 h-12 flex items-center justify-center rounded-full bg-primary/10 text-primary text-xl">!</div>
          <div>
            <p className="text-sm font-semibold text-gray-800">
              {returnsLoading ? 'Loading return requests...' : 'You currently have no return requests'}
            </p>
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
                    Product Name <span className="font-normal">{item.product_title || '—'}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Order Date <span className="font-normal">{item.order_date ? new Date(item.order_date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Quantity <span className="font-normal">{item.quantity ?? 1}</span>
                  </p>
                  <span className={`inline-flex mt-3 px-3 py-1 rounded-sm text-xs font-semibold ${getReturnStatusStyles(displayStatus(item.status))}`}>
                    {displayStatus(item.status)}
                  </span>
                </div>
                <div>
                  <p className="font-semibold text-gray-900">
                    Order ID <span className="font-normal">{item.order_number || item.order_id}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Amount <span className="font-normal">₦{(item.amount ?? 0).toLocaleString()}</span>
                  </p>
                  <p className="font-semibold text-gray-900">
                    Reason <span className="font-normal">{item.reason}</span>
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 justify-start">
                <button
                  type="button"
                  onClick={() => navigate(`${ROUTES.PROFILE_RETURNS}/${item.id}`)}
                  className="px-6 py-2 border border-primary text-primary text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-primary hover:text-white transition"
                >
                  View Details
                </button>
                {displayStatus(item.status) !== 'denied' && (
                  <button
                    type="button"
                    onClick={() =>
                      navigate(
                        displayStatus(item.status) === 'submitted'
                          ? `${ROUTES.PROFILE_RETURNS}/${item.id}/edit`
                          : `${ROUTES.PROFILE_RETURNS}/${item.id}`
                      )
                    }
                    className="px-6 py-2 border border-gray-400 text-gray-600 text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-gray-100 transition"
                  >
                    {displayStatus(item.status) === 'submitted' ? 'Edit Return Request' : 'Shipping Instructions'}
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
          <InputField label="First Name" value={formProfile.firstName} onChange={(value) => setFormProfile((prev) => ({ ...prev, firstName: value }))} />
          <InputField label="Last Name" value={formProfile.lastName} onChange={(value) => setFormProfile((prev) => ({ ...prev, lastName: value }))} />
        </div>
        <InputField label="Email Address" value={formProfile.email} onChange={(value) => setFormProfile((prev) => ({ ...prev, email: value }))} />
        <InputField label="Phone Number" value={formProfile.phone} onChange={(value) => setFormProfile((prev) => ({ ...prev, phone: value }))} />
        <SelectField
          label="Order ID"
          options={orderOptions.length ? orderOptions : [ordersLoading ? 'Loading orders...' : 'No orders found']}
          defaultValue={selectedOrderNumber}
          onChange={(value) => setSelectedOrderNumber(value)}
          disabled={!orderOptions.length}
        />
        <ProductSelectField
          label="Product Name"
          options={productOptions}
          defaultValue={selectedProductId}
          onChange={(value) => setSelectedProductId(value)}
          disabled={!productOptions.length}
          emptyLabel={selectedOrder ? 'No products found' : 'Select an order first'}
        />
        <DateField label="Order Date" defaultValue={selectedOrderDate} />
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
        <InputField label="Quantity" value={`${selectedProduct?.quantity ?? 1}`} disabled />
        <SelectField label="Reason" options={['Received Wrong Item', 'Damaged Item', 'Changed Mind']} defaultValue={reason} onChange={setReason} />
        <SelectField label="Opened" options={['Unopened', 'Opened']} defaultValue={opened} onChange={setOpened} />
        <SelectField label="Return Action" options={['Refund', 'Replacement']} defaultValue={returnAction} onChange={setReturnAction} />
        <TextAreaField label="Faulty or other details" placeholder="Faulty or other detail" value={details} onChange={setDetails} />
        <div className="flex gap-4 pt-4">
          <button type="button" onClick={() => setMode('formStep1')} className="flex-1 border border-primary text-primary font-semibold rounded-sm py-3 hover:bg-primary hover:text-white transition">
            Back
          </button>
          <button
            type="submit"
            disabled={submittingReturn}
            className={`flex-1 bg-primary text-white font-semibold rounded-sm py-3 hover:bg-primary-dark transition ${submittingReturn ? 'opacity-70 cursor-not-allowed' : ''}`}
          >
            {submittingReturn ? 'Submitting...' : 'Submit'}
          </button>
        </div>
      </form>
    </>
  );

  return (
    <Layout>
      {toastVisible && (
        <div className={`fixed top-0 inset-x-0 z-50 ${toastTone === 'success' ? 'bg-primary' : 'bg-red-600'} text-white shadow-md`}>
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            <p className="font-semibold uppercase tracking-[0.3em]">Return request</p>
            <p className="text-white/90">{toastMessage}</p>
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
    case 'requested':
    case 'submitted':
      return 'bg-amber-50 text-amber-700 border border-amber-200';
    case 'approved':
    case 'received':
    case 'refunded':
      return 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    case 'rejected':
    case 'denied':
      return 'bg-red-50 text-red-700 border border-red-200';
    default:
      return 'bg-gray-100 text-gray-600 border border-gray-200';
  }
}

interface InputFieldProps {
  label: string;
  defaultValue?: string;
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
}

function InputField({ label, defaultValue, value, onChange, disabled = false }: InputFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <input
        type="text"
        defaultValue={value === undefined ? defaultValue : undefined}
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        disabled={disabled}
        className={`w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary ${disabled ? 'bg-gray-50 text-gray-400 cursor-not-allowed' : ''}`}
      />
    </div>
  );
}

interface SelectFieldProps {
  label: string;
  options: string[];
  defaultValue?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
}

function SelectField({ label, options, defaultValue, onChange, disabled = false }: SelectFieldProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(defaultValue ?? options[0] ?? '');
  const selectRef = useRef<HTMLDivElement | null>(null);
  const inputName = label.toLowerCase().replace(/\s+/g, '-');

  useEffect(() => {
    if (defaultValue !== undefined) {
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
          onClick={() => !disabled && setOpen((prev) => !prev)}
          className={`w-full border rounded-sm px-3 py-2 text-sm flex items-center justify-between transition focus:outline-none ${
            open ? 'border-primary' : 'border-gray-300 hover:border-primary/70'
          } ${disabled ? 'bg-gray-50 text-gray-400 cursor-not-allowed' : ''}`}
        >
          <span className={value ? 'text-gray-900' : 'text-gray-400'}>{value || 'Select option'}</span>
          <ChevronDown className={`w-4 h-4 text-primary transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        <input type="hidden" value={value} name={inputName} readOnly />
        {open && !disabled && (
          <div className="absolute z-20 mt-1 w-full border border-gray-200 bg-white shadow-2xl rounded-sm">
            {options.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setValue(option);
                  onChange?.(option);
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

interface ProductSelectOption {
  id: string;
  label: string;
  image?: string;
  quantity?: number;
  amount?: number;
}

interface ProductSelectFieldProps {
  label: string;
  options: ProductSelectOption[];
  defaultValue?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  emptyLabel?: string;
}

function ProductSelectField({
  label,
  options,
  defaultValue,
  onChange,
  disabled = false,
  emptyLabel = 'Select option',
}: ProductSelectFieldProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState(defaultValue ?? '');
  const selectRef = useRef<HTMLDivElement | null>(null);
  const inputName = label.toLowerCase().replace(/\s+/g, '-');

  useEffect(() => {
    if (defaultValue !== undefined) {
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

  const selected = options.find((option) => option.id === value);
  const displayLabel = selected?.label || emptyLabel;

  return (
    <div className="space-y-1" ref={selectRef}>
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <div className="relative">
        <button
          type="button"
          onClick={() => !disabled && setOpen((prev) => !prev)}
          className={`w-full border rounded-sm px-3 py-2 text-sm flex items-center justify-between transition focus:outline-none ${
            open ? 'border-primary' : 'border-gray-300 hover:border-primary/70'
          } ${disabled ? 'bg-gray-50 text-gray-400 cursor-not-allowed' : ''}`}
        >
          <span className={value ? 'text-gray-900' : 'text-gray-400'}>{displayLabel}</span>
          <ChevronDown className={`w-4 h-4 text-primary transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        <input type="hidden" value={value} name={inputName} readOnly />
        {open && !disabled && (
          <div className="absolute z-20 mt-1 w-full border border-gray-200 bg-white shadow-2xl rounded-sm max-h-64 overflow-y-auto">
            {options.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => {
                  setValue(option.id);
                  onChange?.(option.id);
                  setOpen(false);
                }}
                className={`w-full text-left px-4 py-2 text-sm transition flex items-center gap-3 ${
                  option.id === value ? 'bg-primary/10 text-primary font-semibold' : 'text-gray-700 hover:bg-gray-50'
                }`}
              >
                {option.image ? (
                  <img
                    src={option.image}
                    alt={option.label}
                    className="h-8 w-8 rounded-sm object-cover border border-gray-200"
                  />
                ) : (
                  <div className="h-8 w-8 rounded-sm border border-gray-200 bg-gray-100" />
                )}
                <span className="truncate">{option.label}</span>
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
  value?: string;
  onChange?: (value: string) => void;
}

function TextAreaField({ label, placeholder, value, onChange }: TextAreaFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <textarea
        placeholder={placeholder}
        rows={4}
        value={value}
        onChange={(event) => onChange?.(event.target.value)}
        className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary"
      />
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
