import type { Currency } from '../../store/currencyStore';

const CURRENCIES: Currency[] = ['NGN', 'USD'];

interface CurrencySwitcherProps {
  value: Currency;
  onChange: (currency: Currency) => void;
  label?: string;
  className?: string;
}

export default function CurrencySwitcher({
  value,
  onChange,
  label = 'Currency',
  className,
}: CurrencySwitcherProps) {
  return (
    <div className={`flex items-center gap-2 ${className || ''}`}>
      <span className="text-sm text-gray-600">{label}:</span>
      <div className="inline-flex rounded-lg border border-gray-300 bg-white overflow-hidden">
        {CURRENCIES.map((currency) => {
          const isActive = currency === value;
          return (
            <button
              key={currency}
              type="button"
              onClick={() => {
                try {
                  onChange(currency);
                } catch (error) {
                  console.error('[CurrencySwitcher] Failed to change currency', {
                    from: value,
                    to: currency,
                    error,
                  });
                }
              }}
              className={`px-3 py-1.5 text-xs font-semibold transition ${
                isActive
                  ? 'bg-[#105E53] text-white'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {currency}
            </button>
          );
        })}
      </div>
    </div>
  );
}
