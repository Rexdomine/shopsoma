import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import type { Product, ProductVariant } from '../../types';
import { ROUTES } from '../../config/constants';
import ProductCard from '../products/ProductCard';
import { IMAGE_CONFIG } from '../../config/constants';

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
  if (!open) return null;

  const brand = product.vendor_name ?? 'Shopsoma Collective';
  const model = product.title;
  const price = variant?.price ?? product.base_price;
  const size = variant?.size ?? 'Unique';
  const color = variant?.color ?? 'As shown';
  const availability = (variant?.stock ?? product.total_stock ?? 0) > 0 ? 'Now available' : 'Pre-order';
  const thumbnail = product.images?.[0]?.image_url ?? IMAGE_CONFIG.PLACEHOLDER;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4 py-8">
      <div className="relative w-full max-w-[700px] bg-white rounded-[24px] shadow-2xl overflow-hidden border border-gray-100">
        <button
          type="button"
          className="absolute top-6 right-6 text-gray-400 hover:text-dark"
          aria-label="Close"
          onClick={onClose}
        >
          <X className="w-5 h-5" />
        </button>
        <div className="p-6 sm:p-8 space-y-6">
          <div className="flex items-start gap-4">
            <div className="w-20 h-24 rounded-xl overflow-hidden bg-[#f5f7f8]">
              <img
                src={thumbnail}
                alt={product.title}
                className="w-full h-full object-cover"
                onError={(event) => {
                  event.currentTarget.src = IMAGE_CONFIG.PLACEHOLDER;
                }}
              />
            </div>
            <div className="flex-1">
              <p className="text-xs uppercase tracking-[0.4em] text-gray-400 mb-1">
                This item has been added to your shopping bag
              </p>
              <h3 className="text-2xl font-display font-semibold text-dark">
                {product.title}
              </h3>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 text-sm">
            <InfoRow label="Brand" value={brand} />
            <InfoRow label="Size" value={size} />
            <InfoRow label="Model" value={model} />
            <InfoRow label="Color" value={color} />
            <InfoRow label="Price" value={`₦${Number(price).toLocaleString()}`} bold />
            <InfoRow label="Availability" value={availability} />
          </div>

          <p className="text-xs text-gray-500 leading-relaxed">
            Please note: Until you checkout, items in your shopping bag are not reserved and may
            still be purchased by other customers.
          </p>

          <div className="flex flex-col sm:flex-row gap-3">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 border border-gray-300 py-3 rounded-full text-sm font-semibold text-gray-700 hover:border-primary hover:text-primary transition"
            >
              Continue Shopping
            </button>
            <Link
              to={ROUTES.CART}
              className="flex-1 py-3 rounded-full text-sm font-semibold text-white text-center bg-primary hover:bg-primary-dark transition"
            >
              Go to Bag
            </Link>
          </div>
        </div>

        {recommendations.length > 0 && (
          <div className="border-t border-gray-200 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm uppercase tracking-[0.3em] text-gray-400">Others also viewed</p>
              <span className="text-xs text-gray-400">You may also like</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
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
    <div className="flex items-center justify-between">
      <span className="text-xs font-semibold uppercase tracking-[0.3em] text-gray-500">
        {label}
      </span>
      <span className={`text-sm ${bold ? 'font-semibold text-dark' : 'text-gray-700'}`}>
        {value}
      </span>
    </div>
  );
}
