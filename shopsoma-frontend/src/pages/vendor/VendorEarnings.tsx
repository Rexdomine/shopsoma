import {
  Calendar,
  ChevronDown,
  Eye,
  Filter,
  Search,
  TrendingUp,
  Upload,
} from 'lucide-react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import { useState } from 'react';
import WithdrawModal from '../../components/vendor/WithdrawModal';

type EarningsRow = {
  id: string;
  product: string;
  price: number;
  quantity: number;
  expense: number;
  earnings: number;
  date: string;
  status: 'complete' | 'pending';
};

const mockRows: EarningsRow[] = Array.from({ length: 9 }).map((_, idx) => ({
  id: `row-${idx + 1}`,
  product: 'Semiotics twee williamsburg helvetica offal sustainable juice church.',
  price: 423,
  quantity: 16,
  expense: idx % 2 === 0 ? 123 : 83,
  earnings: 1822,
  date: '12/09/25',
  status: 'complete',
}));

function StatusPill({ status }: { status: EarningsRow['status'] }) {
  if (status === 'complete') {
    return <span className="px-4 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Complete</span>;
  }
  return <span className="px-4 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700">Pending</span>;
}

export default function VendorEarnings() {
  const navigate = useNavigate();
  const [showWithdraw, setShowWithdraw] = useState(false);
  return (
    <div className="flex min-h-screen bg-gray-50">
      <VendorSidebar activePrimary="earnings" />

      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <h1 className="text-2xl font-semibold text-gray-900">Earnings & Payout</h1>
            <div className="flex items-center gap-3 flex-1 justify-end">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search"
                  className="pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent w-64"
                />
              </div>
              <button
                type="button"
                className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                <Filter className="h-5 w-5 text-gray-600" />
              </button>
              <button
                type="button"
                className="p-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition"
              >
                <Upload className="h-5 w-5 text-gray-600" />
              </button>
            </div>
          </div>

          <div className="w-full flex items-start justify-between gap-8">
            <div className="flex-1 space-y-6">
              <div className="space-y-3">
                <p className="text-sm text-gray-400">Current Earnings</p>
                <div className="flex items-center gap-4">
                  <p className="text-4xl font-semibold text-gray-900 tracking-tight">₦2,732,983</p>
                  <div className="flex items-center gap-2 text-sm">
                    <span className="flex items-center gap-1 text-emerald-600 font-semibold">
                      <TrendingUp className="w-4 h-4" />
                      6%
                    </span>
                    <span className="text-gray-500">vs Last Week</span>
                    <ChevronDown className="w-4 h-4 text-gray-400" />
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-start gap-8">
                  <div className="space-y-1">
                    <p className="text-sm text-gray-400">Projected Earnings</p>
                    <div className="flex items-center gap-2">
                      <p className="text-2xl font-semibold text-gray-900 tracking-tight">₦3,032,832</p>
                      <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
                        <TrendingUp className="w-4 h-4" />
                        16%
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <p className="text-sm text-gray-400 flex items-center gap-2">
                      <span className="h-5 w-5 rounded-full border border-gray-300 text-gray-500 flex items-center justify-center text-xs">i</span>
                      Expenses
                    </p>
                    <div className="flex items-center gap-2">
                      <p className="text-2xl font-semibold text-gray-900 tracking-tight">₦432,298</p>
                      <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
                        <TrendingUp className="w-4 h-4" />
                        16%
                      </span>
                    </div>
                    <button
                      type="button"
                      className="text-sm text-gray-500 underline"
                      onClick={() => navigate(ROUTES.VENDOR_EXPENSES)}
                    >
                      View All
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col items-end gap-3 w-full max-w-xs">
              <div className="space-y-1 text-right">
                <p className="text-sm text-gray-400">Showing info for:</p>
                <p className="text-sm font-semibold text-gray-800">Jan 01, 2025 - Dec 28, 2025</p>
              </div>

              <div className="flex items-center gap-2">
                {['1D', '7D', '1M', '6M'].map((range) => (
                  <button
                    key={range}
                    type="button"
                    className="px-4 py-2 rounded-lg text-xs font-semibold border border-gray-200 bg-white text-gray-700"
                  >
                    {range}
                  </button>
                ))}
                <button
                  type="button"
                  className="h-10 w-10 rounded-lg border border-gray-900 bg-gray-900 flex items-center justify-center text-white"
                >
                  <Calendar className="w-4 h-4" />
                </button>
              </div>

              <button
                type="button"
                className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-full border border-gray-200 bg-white shadow-sm text-sm font-semibold text-gray-800"
                onClick={() => navigate(ROUTES.VENDOR_WITHDRAWALS)}
              >
                <Eye className="w-4 h-4 text-gray-600" />
                View Withdrawals
              </button>
            </div>
          </div>

          <div className="flex items-center gap-4 text-sm text-gray-700">
            <span className="text-gray-500">View by:</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="px-3 py-1.5 rounded-full text-sm font-semibold bg-gray-100 text-gray-800"
              >
                Products (19)
              </button>
              <button
                type="button"
                className="px-3 py-1.5 rounded-full text-sm font-semibold text-gray-600 hover:bg-gray-100"
              >
                Orders
              </button>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="w-16 px-4 py-3 text-left text-xs font-semibold text-gray-500"> </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Product Name</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Price</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Quantity</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Expense</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Earnings</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Date</th>
                  <th className="w-12 px-4 py-3 text-right text-xs font-semibold text-gray-500"> </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {mockRows.map((row) => (
                  <tr key={row.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="h-12 w-10 rounded-full bg-gray-100 border border-gray-200"></div>
                    </td>
                    <td className="px-4 py-3 text-gray-900">{row.product}</td>
                    <td className="px-4 py-3">
                      <StatusPill status={row.status} />
                    </td>
                    <td className="px-4 py-3 font-semibold text-gray-900">${row.price}</td>
                    <td className="px-4 py-3 text-gray-800">{row.quantity}</td>
                    <td className="px-4 py-3 font-semibold text-gray-900">${row.expense}</td>
                    <td className="px-4 py-3 font-semibold text-gray-900">${row.earnings}</td>
                    <td className="px-4 py-3 text-gray-700">{row.date}</td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center hover:bg-gray-100"
                        aria-label="View details"
                      >
                        <Eye className="w-4 h-4 text-gray-600" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="fixed bottom-6 left-0 right-0 flex justify-center md:justify-end md:pr-[22%] md:-translate-x-[50px] pointer-events-none">
        <button
          type="button"
          className="pointer-events-auto inline-flex items-center gap-2 px-6 py-3 rounded-full bg-[#105E53] text-white font-semibold shadow-lg hover:bg-[#0c4c45] transition whitespace-nowrap"
          onClick={() => setShowWithdraw(true)}
        >
          <Upload className="w-4 h-4" />
          Withdraw Funds
        </button>
      </div>
      <WithdrawModal open={showWithdraw} onClose={() => setShowWithdraw(false)} />
    </div>
  );
}
