import { useEffect, useState } from 'react';
import { Minus, Plus } from 'lucide-react';
import { useNavigate, Link } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { productService } from '../../services/productService';
import type { Product, ProductVariant } from '../../types';
import { IMAGE_CONFIG, ROUTES } from '../../config/constants';
import ProductCard from '../../components/products/ProductCard';
import { useCartStore } from '../../store/cartStore';
import { useWishlistActions } from '../../hooks/useWishlistActions';
import EditVariantModal from '../../components/modals/EditVariantModal';
import { usePreferenceStore } from '../../store/preferenceStore';
import { useCurrencyStore } from '../../store/currencyStore';
import { convertCurrencyWithRates, formatAmount, formatPriceWithConversion, type Currency } from '../../utils/pricing';

export default function Cart() {
  const navigate = useNavigate();
  const cart = useCartStore((state) => state.cart);
  const updateQuantity = useCartStore((state) => state.updateQuantity);
  const updateVariant = useCartStore((state) => state.updateVariant);
  const removeItem = useCartStore((state) => state.removeItem);
  const preferredCurrency = usePreferenceStore((state) => state.currency);
  const exchangeRates = useCurrencyStore((state) => state.exchangeRates);
  const { favorites, toggleFavorite } = useWishlistActions();
  const [toastMessage, setToastMessage] = useState('');
  const [toastVisible, setToastVisible] = useState(false);

  const [recommended, setRecommended] = useState<Product[]>([]);
  const [editingItem, setEditingItem] = useState<{
    itemId: string;
    product: Product;
    variant: ProductVariant;
  } | null>(null);

  const subtotalInSelectedCurrency = cart.items.reduce((sum, item) => {
    return sum + convertCurrencyWithRates(
      item.subtotal,
      item.product.currency || 'NGN',
      preferredCurrency,
      exchangeRates
    );
  }, 0);

  const subtotalInNgn = cart.items.reduce((sum, item) => {
    return sum + convertCurrencyWithRates(
      item.subtotal,
      item.product.currency || 'NGN',
      'NGN',
      exchangeRates
    );
  }, 0);

  const minimumOrderInSelectedCurrency = convertCurrencyWithRates(60000, 'NGN', preferredCurrency, exchangeRates);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await productService.getProducts({ page_size: 6 });
        setRecommended(response.products);
      } catch (err) {
        console.error('Failed to load recommended', err);
      }
    };
    load();
  }, []);

  const handleQuantityChange = (itemId: string, direction: 'inc' | 'dec') => {
    const item = cart.items.find((i) => i.id === itemId);
    if (!item) return;

    const newQuantity = direction === 'inc' ? item.quantity + 1 : Math.max(1, item.quantity - 1);
    updateQuantity({ itemId, quantity: newQuantity });
  };

  const handleRemoveItem = (itemId: string) => {
    removeItem(itemId);
  };

  const handleEditVariant = (itemId: string) => {
    const item = cart.items.find((i) => i.id === itemId);
    if (!item) return;

    setEditingItem({
      itemId,
      product: item.product,
      variant: item.variant,
    });
  };

  const handleSaveVariant = (newVariant: ProductVariant) => {
    if (!editingItem) return;

    // Update variant in place (preserves order)
    updateVariant({
      itemId: editingItem.itemId,
      newVariant,
    });

    setEditingItem(null);
  };

  const handleContinueShopping = () => {
    navigate(ROUTES.PRODUCTS);
  };

  const showToast = (message: string) => {
    setToastMessage(message);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 3500);
  };

  const handleCheckout = () => {
    if (subtotalInNgn < 60000) {
      showToast(`Minimum order is ${formatAmount(minimumOrderInSelectedCurrency, preferredCurrency)} (₦60,000 equivalent). Please add more items before checkout.`);
      return;
    }
    navigate(ROUTES.CHECKOUT);
  };

  return (
    <Layout>
      {toastVisible && (
        <div className="fixed inset-x-0 top-0 z-40">
          <div className="mx-auto max-w-[1200px] bg-primary text-white px-8 py-4 border-b border-primary-dark flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-[0.4em] text-white/70">Shopping Bag</p>
              <p className="text-sm font-semibold tracking-wide">{toastMessage}</p>
            </div>
            <button
              type="button"
              onClick={() => setToastVisible(false)}
              className="text-[10px] uppercase tracking-[0.4em] text-white/70 hover:text-white"
            >
              Close
            </button>
          </div>
        </div>
      )}

      <section className="bg-white py-12 lg:py-16">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h1 className="text-2xl font-display font-semibold text-center text-dark tracking-wide mb-12">
            Shopping Bag
          </h1>
          {cart.items.length === 0 ? (
            <div className="py-24 flex flex-col items-center text-center gap-6">
              <div className="w-16 h-16 bg-[#f0f4f2] flex items-center justify-center text-primary text-2xl font-semibold border border-gray-200">
                !
              </div>
              <div className="space-y-2">
                <p className="text-sm uppercase tracking-[0.3em] text-gray-400">Shopping Bag Empty</p>
                <p className="text-gray-500">You currently have no items in your shopping bag.</p>
              </div>
              <Link
                to={ROUTES.PRODUCTS}
                className="px-8 py-3 bg-primary text-white text-sm font-semibold hover:bg-primary-dark transition border border-primary"
              >
                Go to Shop
              </Link>
            </div>
          ) : (
            <>
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-10">
            <div className="space-y-6">
              {cart.items.map((item) => {
                const thumbnail = item.product.images?.[0]?.image_url ?? IMAGE_CONFIG.PLACEHOLDER;
                const brand = item.product.vendor_name ?? 'Shopsoma Collective';
                const category = item.product.category_name ?? '';

                const showMoveToWishlist = !favorites.has(item.product_id);
                return (
                  <article key={item.id} className="border-b border-gray-200 pb-6">
                    <div className="flex flex-col sm:flex-row gap-6">
                      <div className="w-36 h-36 bg-[#f5f7f8] overflow-hidden border border-gray-200">
                        <img
                          src={thumbnail}
                          alt={item.product.title}
                          className="w-full h-full object-cover"
                          onError={(event) => {
                            event.currentTarget.src = IMAGE_CONFIG.PLACEHOLDER;
                          }}
                        />
                      </div>
                      <div className="flex-1 space-y-2">
                        <div className="flex items-center justify-between">
                          <div>
                            <p className="text-[11px] uppercase tracking-[0.3em] text-gray-400">
                              {brand}
                            </p>
                            <h2 className="text-lg font-display font-semibold text-dark">
                              {item.product.title}
                            </h2>
                            <p className="text-sm text-gray-500">{category}</p>
                          </div>
                          <div className="inline-flex items-center border border-gray-300">
                            <button
                              type="button"
                              className="px-3 py-1 text-gray-500 hover:text-primary"
                              onClick={() => handleQuantityChange(item.id, 'dec')}
                            >
                              <Minus className="w-4 h-4" />
                            </button>
                            <span className="px-4 py-1 text-sm font-semibold">{item.quantity}</span>
                            <button
                              type="button"
                              className="px-3 py-1 text-gray-500 hover:text-primary"
                              onClick={() => handleQuantityChange(item.id, 'inc')}
                            >
                              <Plus className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                        <div className="text-sm text-gray-600 space-y-1">
                          <p>Size: {item.variant.size}</p>
                          <p>Color: {item.variant.color}</p>
                        </div>
                        <div className="flex items-center justify-between pt-2 text-sm">
                          {showMoveToWishlist ? (
                            <button
                              type="button"
                              className="text-primary underline"
                              onClick={() => toggleFavorite(item.product_id)}
                            >
                              Move to Wishlist
                            </button>
                          ) : (
                            <span className="text-xs uppercase tracking-[0.2em] text-gray-400">
                              Already in Wishlist
                            </span>
                          )}
                          <span className="text-base font-semibold text-dark">
                            {formatPriceWithConversion(
                              item.subtotal,
                              item.product.currency || 'NGN',
                              preferredCurrency,
                              exchangeRates
                            )}
                          </span>
                        </div>
                        <div className="flex items-center justify-end gap-3 pt-2">
                          <button
                            type="button"
                            onClick={() => handleEditVariant(item.id)}
                            className="px-5 py-2 border border-gray-300 text-xs font-semibold text-gray-600 hover:border-primary hover:text-primary transition"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="h-9 w-9 border border-gray-300 text-sm text-gray-500 hover:text-red-500"
                            aria-label="Remove item"
                            onClick={() => handleRemoveItem(item.id)}
                          >
                            ×
                          </button>
                        </div>
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>

            <aside className="space-y-6">
              <div className="border border-gray-200 p-6 space-y-4">
                <h3 className="text-sm font-semibold tracking-[0.3em] text-gray-500 uppercase">
                  Order Summary
                </h3>
                <div className="text-sm space-y-2">
                  <SummaryRow
                    label="Subtotal"
                    value={subtotalInSelectedCurrency}
                    currency={preferredCurrency}
                  />
                  <div className="flex items-center justify-between text-xs text-gray-400 italic">
                    <span>Shipping</span>
                    <span>Calculated at checkout</span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-gray-400 italic">
                    <span>Tax (VAT 7.5%)</span>
                    <span>Calculated at checkout</span>
                  </div>
                </div>
                <div className="border-t border-gray-200 pt-4">
                  <SummaryRow
                    label="Estimated Total"
                    value={subtotalInSelectedCurrency}
                    bold
                    currency={preferredCurrency}
                  />
                </div>
                <div className="space-y-3 pt-2">
                  <button
                    type="button"
                    onClick={handleCheckout}
                    disabled={cart.items.length === 0}
                    className="w-full bg-primary text-white py-3 text-sm font-semibold hover:bg-primary-dark transition disabled:opacity-50 disabled:cursor-not-allowed border border-primary"
                  >
                    Proceed to Checkout
                  </button>
                  <button
                    type="button"
                    onClick={handleContinueShopping}
                    className="w-full border border-gray-300 text-sm font-semibold py-3 text-gray-700 hover:border-primary hover:text-primary transition"
                  >
                    Continue Shopping
                  </button>
                </div>
              </div>

              <Accordion title="Returns" content="Complimentary returns within 7 days of delivery." />
              <Accordion title="Secure Payment" content="Transactions are encrypted and secured." />
              <Accordion title="Need Help?" content="Reach support@shopsoma.com or +234 800 000 0000." />
            </aside>
          </div>

          {recommended.length > 0 && (
            <div className="mt-16">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400 mb-6">Recommended</p>
              <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
                {recommended.slice(0, 5).map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
            </div>
          )}
          </>
          )}
        </div>
      </section>

      {editingItem && (
        <EditVariantModal
          open={true}
          product={editingItem.product}
          currentVariant={editingItem.variant}
          onClose={() => setEditingItem(null)}
          onSave={handleSaveVariant}
        />
      )}
    </Layout>
  );
}

function SummaryRow({
  label,
  value,
  bold,
  currency,
}: {
  label: string;
  value: number;
  bold?: boolean;
  currency: Currency;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-gray-500">{label}</span>
      <span className={`text-sm ${bold ? 'font-semibold text-dark' : 'text-gray-700'}`}>
        {formatAmount(value, currency)}
      </span>
    </div>
  );
}

function Accordion({ title, content }: { title: string; content: string }) {
  return (
    <details className="border border-gray-200 px-4 py-3">
      <summary className="flex items-center justify-between text-sm font-semibold text-gray-700 cursor-pointer">
        {title}
        <span className="text-primary">+</span>
      </summary>
      <p className="mt-2 text-sm text-gray-500">{content}</p>
    </details>
  );
}
