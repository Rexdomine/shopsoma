import { useEffect, useRef, useState } from 'react';
import { X, ChevronDown, Check } from 'lucide-react';

type WithdrawModalProps = {
  open: boolean;
  onClose: () => void;
};

const accounts = [
  'Wema Bank (xxx4673)',
  'GTBank (xxx1920)',
  'Access Bank (xxx8844)',
];

export default function WithdrawModal({ open, onClose }: WithdrawModalProps) {
  const [amount, setAmount] = useState(500000);
  const [account, setAccount] = useState(accounts[0]);
  const [openAccountList, setOpenAccountList] = useState(false);
  const listRef = useRef<HTMLDivElement | null>(null);
  const minAmount = 50000;
  const step = 50000;

  useEffect(() => {
    if (!open) {
      setAmount(500000);
      setAccount(accounts[0]);
      setOpenAccountList(false);
    }
  }, [open]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (listRef.current && !listRef.current.contains(e.target as Node)) {
        setOpenAccountList(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (!open) return null;

  const handleIncrement = () => setAmount((prev) => prev + step);
  const handleDecrement = () => setAmount((prev) => Math.max(minAmount, prev - step));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-[1px] px-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-6 relative">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-4 top-4 text-gray-400 hover:text-gray-600"
          aria-label="Close"
        >
          <X className="w-5 h-5" />
        </button>
        <h3 className="text-sm font-semibold text-gray-800 mb-6">Withdraw Earnings</h3>

        <div className="flex items-center justify-center gap-4 mb-2">
          <button
            type="button"
            onClick={handleDecrement}
            className="h-8 w-8 rounded-full border border-gray-300 flex items-center justify-center text-lg text-gray-700 hover:bg-gray-50"
            aria-label="Decrease amount"
          >
            –
          </button>
          <div className="text-3xl font-semibold text-gray-900 tracking-tight">
            ₦{amount.toLocaleString()}
          </div>
          <button
            type="button"
            onClick={handleIncrement}
            className="h-8 w-8 rounded-full border border-gray-300 flex items-center justify-center text-lg text-gray-700 hover:bg-gray-50"
            aria-label="Increase amount"
          >
            +
          </button>
        </div>
        <p className="text-xs text-gray-500 text-center mb-6">Est. Transfer Time: 3 days</p>

        <div className="space-y-2">
          <p className="text-sm text-gray-600">Choose Account</p>
          <div className="relative" ref={listRef}>
            <button
              type="button"
              onClick={() => setOpenAccountList((prev) => !prev)}
              className="w-full border border-gray-300 rounded-lg px-4 py-3 text-sm text-gray-800 bg-white flex items-center justify-between focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:border-transparent"
            >
              <span className="truncate">{account}</span>
              <ChevronDown className={`w-4 h-4 text-gray-500 transition ${openAccountList ? 'rotate-180' : ''}`} />
            </button>
            {openAccountList && (
              <div className="absolute z-10 mt-2 w-full bg-white border border-gray-200 rounded-lg shadow-lg overflow-hidden">
                {accounts.map((acc) => (
                  <button
                    key={acc}
                    type="button"
                    onClick={() => {
                      setAccount(acc);
                      setOpenAccountList(false);
                    }}
                    className={`w-full px-4 py-3 text-left text-sm flex items-center justify-between hover:bg-gray-50 ${
                      acc === account ? 'text-gray-900 font-semibold' : 'text-gray-700'
                    }`}
                  >
                    <span className="truncate">{acc}</span>
                    {acc === account && <Check className="w-4 h-4 text-[#105E53]" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <button
          type="button"
          className="mt-6 w-full bg-[#105E53] text-white font-semibold rounded-lg py-3 hover:bg-[#0c4c45] transition"
          onClick={onClose}
        >
          Begin Withdrawal
        </button>
      </div>
    </div>
  );
}
