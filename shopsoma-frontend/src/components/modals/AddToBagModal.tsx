import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import type { Product, ProductVariant } from '../../types';
import { ROUTES } from '../../config/constants';
import ProductCard from '../products/ProductCard';
import { IMAGE_CONFIG } from '../../config/constants';
import { formatPriceWithConversion } from '../../utils/pricing';
import { usePreferenceStore } from '../../store/preferenceStore';
import { useCurrencyStore } from '../../store/currencyStore';

interface AddToBagModalProps {
  open: boolean;
  product: Product;
  variant: ProductVariant | null;
  quantity: number;
  recommendations?: Product[];
  onClose: () => void;
}

export default function AddToBagModal({
  open,
  product,
  variant,
  quantity: _quantity,
  recommendations = [],
  onClose,
}: AddToBagModalProps) {
  const preferredCurrency = usePreferenceStore((state) => state.currency);
  const exchangeRates = useCurrencyStore((state) => state.exchangeRates);
  if (!open) return null;

  const brand = product.vendor_name ?? 'Shopsoma Collective';
  const model = product.title;
  const price = variant?.price ?? product.base_price;
  const size = variant?.size ?? 'Unique';
  const color = variant?.color ?? 'As shown';
  const stockCount = variant?.stock ?? product.total_stock ?? 0;
  const availability = stockCount > 0
    ? `In Stock (${stockCount} available)`
    : 'Out of Stock';
  const thumbnail = product.images?.[0]?.image_url ?? IMAGE_CONFIG.PLACEHOLDER;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 py-8">
      <div className="relative w-full max-w-[700px] max-h-[90vh] bg-white shadow-2xl overflow-y-auto border border-gray-100">
        <button
          type="button"
          className="absolute top-4 right-4 text-gray-400 hover:text-dark z-10"
          aria-label="Close"
          onClick={onClose}
        >
          <X className="w-5 h-5" />
        </button>
        <div className="p-5 sm:p-6 space-y-4">
          <div className="flex items-start gap-3">
            <div className="w-16 h-20 overflow-hidden bg-[#f5f7f8] border border-gray-200 flex-shrink-0">
              <img
                src={thumbnail}
                alt={product.title}
                className="w-full h-full object-cover"
                onError={(event) => {
                  event.currentTarget.src = IMAGE_CONFIG.PLACEHOLDER;
                }}
              />
            </div>
            <div className="flex-1 min-w-0 pr-8">
              <p className="text-[10px] uppercase tracking-[0.3em] text-gray-400 mb-1">
                Added to shopping bag
              </p>
              <h3 className="text-lg font-display font-semibold text-dark leading-tight">
                {product.title}
              </h3>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <InfoRow label="Brand" value={brand} />
            <InfoRow label="Size" value={size} />
            <InfoRow label="Model" value={model} />
            <InfoRow label="Color" value={color} />
            <InfoRow
              label="Price"
              value={formatPriceWithConversion(
                Number(price),
                product.currency,
                preferredCurrency,
                exchangeRates
              )}
              bold
            />
            <InfoRow label="Availability" value={availability} />
          </div>

          <p className="text-[11px] text-gray-500 leading-relaxed py-2">
            Please note: Until you checkout, items in your shopping bag are not reserved and may
            still be purchased by other customers.
          </p>

          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-gray-300 py-2.5 text-sm font-semibold text-gray-700 hover:border-primary hover:text-primary transition"
            >
              Continue Shopping
            </button>
            <Link
              to={ROUTES.CART}
              className="flex-1 py-2.5 text-sm font-semibold text-white text-center bg-primary hover:bg-primary-dark transition border border-primary"
            >
              Go to Bag
            </Link>
          </div>
        </div>

        {recommendations.length > 0 && (
          <div className="border-t border-gray-200 p-5 sm:p-6 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Others also viewed</p>
              <span className="text-[10px] text-gray-400">You may also like</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {recommendations.slice(0, 3).map((item) => (
                <div key={item.id} onClick={onClose}>
                  <ProductCard product={item} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface InfoRowProps {
  label: string;
  value: string;
  bold?: boolean;
}

function InfoRow({ label, value, bold = false }: InfoRowProps) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-[10px] font-semibold uppercase tracking-[0.25em] text-gray-500">
        {label}
      </span>
      <span className={`text-sm ${bold ? 'font-semibold text-dark' : 'text-gray-700'}`}>
        {value}
      </span>
    </div>
  );
}
