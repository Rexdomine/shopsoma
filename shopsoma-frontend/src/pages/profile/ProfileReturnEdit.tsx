import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import ProfileMenu from './ProfileMenu';
import { ROUTES } from '../../config/constants';
import { userService, type ReturnRequest } from '../../services/userService';

const MENU_ITEMS = [
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

export default function ProfileReturnEdit() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [returnRequest, setReturnRequest] = useState<ReturnRequest | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const [toastMessage, setToastMessage] = useState('Return request updated successfully');
  const [toastTone, setToastTone] = useState<'success' | 'error'>('success');

  const [reason, setReason] = useState('Received Wrong Item');
  const [opened, setOpened] = useState('Unopened');
  const [returnAction, setReturnAction] = useState('Refund');
  const [details, setDetails] = useState('');

  useEffect(() => {
    let isMounted = true;

    const loadReturn = async () => {
      if (!id) return;
      try {
        setLoading(true);
        const response = await userService.getReturn(id);
        if (!isMounted) return;
        setReturnRequest(response);
        setReason(response.reason || 'Received Wrong Item');
        setOpened(response.opened || 'Unopened');
        setReturnAction(response.return_action || 'Refund');
        setDetails(response.description || '');
      } catch (error) {
        console.error('Failed to load return request', error);
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    loadReturn();

    return () => {
      isMounted = false;
    };
  }, [id]);

  const formattedDate = useMemo(() => {
    if (!returnRequest?.order_date) return '—';
    const parsed = new Date(returnRequest.order_date);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }, [returnRequest?.order_date]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!returnRequest || !id) return;
    if (saving) return;

    try {
      setSaving(true);
      const updated = await userService.updateReturn(id, {
        reason,
        opened,
        return_action: returnAction,
        description: details,
      });
      setReturnRequest(updated);
      setToastMessage('Return request updated successfully');
      setToastTone('success');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
      navigate(`${ROUTES.PROFILE_RETURNS}/${id}`);
    } catch (error: any) {
      console.error('Failed to update return request', error);
      setToastMessage(error?.message || 'Failed to update return request');
      setToastTone('error');
      setToastVisible(true);
      setTimeout(() => setToastVisible(false), 4000);
    } finally {
      setSaving(false);
    }
  };

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
          <ProfileMenu items={MENU_ITEMS} onNavigate={(route) => navigate(route)} />
          <section className="flex-1">
            <header className="mb-8 flex items-center gap-4">
              <button
                type="button"
                onClick={() => navigate(ROUTES.PROFILE_RETURNS)}
                className="text-primary text-xl"
                aria-label="Go back"
              >
                ←
              </button>
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Edit return request</p>
            </header>

            {loading ? (
              <div className="py-20 text-center text-sm text-gray-500">Loading return request...</div>
            ) : returnRequest ? (
              <div className="bg-white border border-gray-200 rounded-sm p-8 space-y-8 shadow-sm">
                <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                  <div className="flex items-start gap-6">
                    <div className="h-20 w-20 rounded-sm border border-gray-200 overflow-hidden bg-gray-50">
                      {returnRequest.product_image_url ? (
                        <img
                          src={returnRequest.product_image_url}
                          alt={returnRequest.product_title || 'Return item'}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="h-full w-full flex items-center justify-center text-gray-400 text-xs">No Image</div>
                      )}
                    </div>
                    <div className="space-y-2">
                      <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Return Number</p>
                        <p className="text-lg font-semibold text-gray-900">{returnRequest.return_number}</p>
                      </div>
                      <span className="inline-flex px-3 py-1 rounded-sm text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                        {returnRequest.status}
                      </span>
                    </div>
                  </div>
                  <div className="text-right text-sm text-gray-600 space-y-1">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Order ID</p>
                    <p className="font-semibold text-gray-900">{returnRequest.order_number || returnRequest.order_id}</p>
                    <p className="text-gray-500">{formattedDate}</p>
                  </div>
                </div>

                <form className="space-y-6" onSubmit={handleSubmit}>
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 text-sm">
                    <div className="space-y-2">
                      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Product Name</p>
                      <p className="text-base font-semibold text-gray-900">{returnRequest.product_title || '—'}</p>
                    </div>
                    <div className="space-y-2">
                      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Amount</p>
                      <p className="text-base font-semibold text-gray-900">₦{(returnRequest.amount ?? 0).toLocaleString()}</p>
                    </div>
                  </div>

                  <SelectField label="Reason" options={['Received Wrong Item', 'Damaged Item', 'Changed Mind']} value={reason} onChange={setReason} />
                  <SelectField label="Opened" options={['Unopened', 'Opened']} value={opened} onChange={setOpened} />
                  <SelectField label="Return Action" options={['Refund', 'Replacement']} value={returnAction} onChange={setReturnAction} />
                  <TextAreaField label="Faulty or other details" value={details} onChange={setDetails} placeholder="Faulty or other detail" />

                  <div className="flex flex-wrap gap-3 pt-2">
                    <button
                      type="button"
                      onClick={() => navigate(`${ROUTES.PROFILE_RETURNS}/${id}`)}
                      className="px-6 py-2 border border-primary text-primary text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-primary hover:text-white transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={saving}
                      className={`px-6 py-2 bg-primary text-white text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-primary-dark transition ${saving ? 'opacity-70 cursor-not-allowed' : ''}`}
                    >
                      {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              <div className="py-20 text-center text-sm text-gray-500">Return request not found.</div>
            )}
          </section>
        </div>
      </div>
    </Layout>
  );
}

interface SelectFieldProps {
  label: string;
  options: string[];
  value: string;
  onChange: (value: string) => void;
}

function SelectField({ label, options, value, onChange }: SelectFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary bg-white"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

interface TextAreaFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

function TextAreaField({ label, value, onChange, placeholder }: TextAreaFieldProps) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase tracking-[0.3em] text-gray-400">{label}</p>
      <textarea
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        placeholder={placeholder}
        className="w-full border border-gray-300 rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-primary"
      />
    </div>
  );
}
