import {
  ArrowLeft,
  Calendar,
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

type WithdrawalRow = {
  id: string;
  amount: number;
  initiated: string;
  withdrawn: string;
  destination: string;
  status: 'delivered' | 'pending';
};

const mockWithdrawals: WithdrawalRow[] = Array.from({ length: 10 }).map((_, idx) => ({
  id: `wd-${idx + 1}`,
  amount: 774000,
  initiated: '19/04/2026',
  withdrawn: '21/04/2026',
  destination: 'Wema Bank (xxx4673)',
  status: 'delivered',
}));

function StatusBadge({ status }: { status: WithdrawalRow['status'] }) {
  if (status === 'delivered') {
    return <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700">Delivered</span>;
  }
  return <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700">Pending</span>;
}

export default function VendorWithdrawals() {
  const navigate = useNavigate();
  const [showWithdraw, setShowWithdraw] = useState(false);

  return (
    <div className="flex min-h-screen bg-gray-50">
      <VendorSidebar activePrimary="earnings" />

      <div className="flex-1">
        <div className="px-8 py-8 space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <button
                type="button"
                onClick={() => navigate(ROUTES.VENDOR_EARNINGS)}
                className="flex items-center gap-2 text-gray-600 hover:text-gray-900"
              >
                <ArrowLeft className="w-4 h-4" />
                Back to Earnings Graph
              </button>
            </div>
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

          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5 flex flex-wrap items-start gap-6">
            <div className="flex-1 space-y-3 min-w-[280px]">
              <div className="flex items-center gap-2 text-sm text-emerald-600">
                <span className="h-6 w-6 rounded-full border border-emerald-200 bg-emerald-50 flex items-center justify-center text-emerald-600">
                  ●
                </span>
                <span>Current Withdrawal</span>
              </div>
              <div className="flex items-center gap-3 flex-wrap">
                <p className="text-4xl font-semibold text-gray-900 tracking-tight">₦500,000</p>
                <span className="text-sm font-semibold text-emerald-600 flex items-center gap-1">
                  <TrendingUp className="w-4 h-4" />
                  16%
                </span>
              </div>
              <div className="flex items-center gap-4 text-sm text-gray-600">
                <span>Initiated: 19/08/2025</span>
                <span>Expected: 21/08/2025</span>
              </div>

              <div>
                <p className="text-sm text-gray-500 mb-1">Destination Account</p>
                <div className="w-full max-w-md px-4 py-3 rounded-lg border border-gray-200 bg-gray-50 text-gray-700">
                  Wema Bank (xxx4673)
                </div>
              </div>
            </div>

            <div className="flex flex-col items-end gap-3 min-w-[200px]">
              <button
                type="button"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-rose-100 bg-rose-50 text-rose-700 text-sm font-semibold hover:bg-rose-100 transition"
              >
                <Upload className="w-4 h-4" />
                Cancel Withdrawal
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2 text-gray-700 text-sm">
              <Upload className="w-4 h-4 text-gray-500" />
              <span>Withdrawal History</span>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="space-y-1 text-sm">
                <p className="text-gray-400">Showing info for:</p>
                <p className="text-gray-800 font-semibold">Jan 01, 2025 - Dec 28, 2025</p>
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
                  className="h-10 w-10 rounded-lg border border-gray-200 flex items-center justify-center bg-white"
                >
                  <Calendar className="w-4 h-4 text-gray-600" />
                </button>
              </div>
            </div>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">S/N</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Amount Withdrawn</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Initiated</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Withdrawn</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Destination Account</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-gray-500"> </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {mockWithdrawals.map((row, idx) => (
                  <tr key={row.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-800">{String(idx + 1).padStart(2, '0')}.</td>
                    <td className="px-4 py-3 font-semibold text-gray-900">₦{row.amount.toLocaleString()}</td>
                    <td className="px-4 py-3 text-gray-800">{row.initiated}</td>
                    <td className="px-4 py-3 text-gray-800">{row.withdrawn}</td>
                    <td className="px-4 py-3 text-gray-800">{row.destination}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={row.status} />
                    </td>
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
