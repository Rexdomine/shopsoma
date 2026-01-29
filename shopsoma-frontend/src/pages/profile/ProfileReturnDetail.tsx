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

export default function ProfileReturnDetail() {
  const navigate = useNavigate();
  const { id } = useParams();
  const [returnRequest, setReturnRequest] = useState<ReturnRequest | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;

    const loadReturn = async () => {
      if (!id) return;
      try {
        setLoading(true);
        const response = await userService.getReturn(id);
        if (!isMounted) return;
        setReturnRequest(response);
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

  const displayStatus = (status?: string) => {
    if (!status) return 'submitted';
    switch (status) {
      case 'requested':
        return 'submitted';
      case 'rejected':
        return 'denied';
      default:
        return status;
    }
  };

  const formattedDate = useMemo(() => {
    if (!returnRequest?.order_date) return '—';
    const parsed = new Date(returnRequest.order_date);
    if (Number.isNaN(parsed.getTime())) return '—';
    return parsed.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  }, [returnRequest?.order_date]);

  return (
    <Layout>
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
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Return details</p>
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
                      <span className={`inline-flex px-3 py-1 rounded-sm text-xs font-semibold ${getReturnStatusStyles(displayStatus(returnRequest.status))}`}>
                        {displayStatus(returnRequest.status)}
                      </span>
                    </div>
                  </div>
                  <div className="text-right text-sm text-gray-600 space-y-1">
                    <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Order ID</p>
                    <p className="font-semibold text-gray-900">{returnRequest.order_number || returnRequest.order_id}</p>
                    <p className="text-gray-500">{formattedDate}</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 text-sm">
                  <div className="space-y-3">
                    <p className="font-semibold text-gray-900">
                      Product Name <span className="font-normal">{returnRequest.product_title || '—'}</span>
                    </p>
                    <p className="font-semibold text-gray-900">
                      Quantity <span className="font-normal">{returnRequest.quantity ?? 1}</span>
                    </p>
                    <p className="font-semibold text-gray-900">
                      Amount <span className="font-normal">₦{(returnRequest.amount ?? 0).toLocaleString()}</span>
                    </p>
                  </div>
                  <div className="space-y-3">
                    <p className="font-semibold text-gray-900">
                      Reason <span className="font-normal">{returnRequest.reason}</span>
                    </p>
                    {returnRequest.rejection_reason && (
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-gray-900">Rejection Reason</span>
                        <span className="inline-flex px-3 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-700 border border-red-200">
                          {returnRequest.rejection_reason}
                        </span>
                      </div>
                    )}
                    <p className="font-semibold text-gray-900">
                      Notes <span className="font-normal">{returnRequest.description || '—'}</span>
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => navigate(`${ROUTES.PROFILE_RETURNS}/${returnRequest.id}/edit`)}
                    className="px-6 py-2 border border-gray-400 text-gray-600 text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-gray-100 transition"
                  >
                    Edit Return Request
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(ROUTES.PROFILE_RETURNS)}
                    className="px-6 py-2 border border-primary text-primary text-xs uppercase tracking-[0.3em] rounded-sm hover:bg-primary hover:text-white transition"
                  >
                    Back to Returns
                  </button>
                </div>
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
