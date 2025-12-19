import {
  Calendar,
  Eye,
  Filter,
  Search,
  TrendingUp,
  Upload,
} from 'lucide-react';
import { useMemo } from 'react';
import VendorSidebar from '../../components/vendor/VendorSidebar';
import { ROUTES } from '../../config/constants';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import WithdrawModal from '../../components/vendor/WithdrawModal';

type ExpenseRow = {
  id: string;
  orderNumber: string;
  itemsListed: string;
  status: 'complete' | 'pending';
  quantity: number;
  cutTaken: number;
  earnings: number;
  date: string;
};

const mockExpenses: ExpenseRow[] = Array.from({ length: 12 }).map((_, idx) => ({
  id: `exp-${idx + 1}`,
  orderNumber: 'Order UYCSG2',
  itemsListed: 'Next yolo brooklyn big viral probably +1.',
  status: 'complete',
  quantity: 16,
  cutTaken: idx % 2 === 0 ? 6811 : 1822,
  earnings: 1822,
  date: '12/09/25',
}));

function StatusPill({ status }: { status: ExpenseRow['status'] }) {
  if (status === 'complete') {
    return <span className="px-4 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Complete</span>;
  }
  return <span className="px-4 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700">Pending</span>;
}

export default function VendorExpenses() {
  const navigate = useNavigate();
  const [showWithdraw, setShowWithdraw] = useState(false);
  const rows = useMemo(() => mockExpenses, []);

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
            <div className="flex-1 space-y-4">
              <div className="space-y-1">
                <p className="text-sm text-gray-400">Current Expenses</p>
                <div className="flex items-center gap-3">
                  <p className="text-4xl font-semibold text-gray-900 tracking-tight">₦432,298</p>
                  <span className="text-sm font-semibold text-emerald-600 flex items-center gap-1">
                    <TrendingUp className="w-4 h-4" />
                    16%
                  </span>
                  <span className="text-gray-500 text-sm">vs Last Week</span>
                  <span className="text-gray-400">▼</span>
                </div>
                <p className="text-sm text-gray-500">The current cut percentage is 12%</p>
              </div>

              <div className="space-y-1">
                <p className="text-sm text-gray-400">Current Earnings</p>
                <div className="flex items-center gap-3">
                  <p className="text-2xl font-semibold text-gray-900 tracking-tight">₦2,732,983</p>
                  <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1">
                    <TrendingUp className="w-4 h-4" />
                    16%
                  </span>
                </div>
                <button
                  type="button"
                  className="text-sm text-gray-500 underline"
                  onClick={() => navigate(ROUTES.VENDOR_EARNINGS)}
                >
                  View All
                </button>
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
                    className={`px-4 py-2 rounded-lg text-xs font-semibold border ${
                      range === '6M' ? 'bg-gray-900 text-white border-gray-900' : 'border-gray-200 text-gray-700 bg-white'
                    }`}
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
                className="px-3 py-1.5 rounded-full text-sm font-semibold text-gray-600 hover:bg-gray-100"
              >
                Products
              </button>
              <button
                type="button"
                className="px-3 py-1.5 rounded-full text-sm font-semibold bg-gray-100 text-gray-800"
              >
                Orders (26)
              </button>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Order Number</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Items Listed</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Quantity</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Cut Taken</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Earnings</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Date</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500"> </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((row) => (
                  <tr key={row.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-900">{row.orderNumber}</td>
                    <td className="px-4 py-3 text-gray-800">{row.itemsListed}</td>
                    <td className="px-4 py-3">
                      <StatusPill status={row.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-800">{row.quantity}</td>
                    <td className="px-4 py-3 font-semibold text-gray-900">${row.cutTaken}</td>
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
