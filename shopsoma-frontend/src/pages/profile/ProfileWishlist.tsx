import { useState, useEffect } from 'react';
import { Heart } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Layout from '../../components/layout/Layout';
import { IMAGE_CONFIG, ROUTES } from '../../config/constants';
import ProfileMenu from './ProfileMenu';
import { wishlistService, type WishlistItem } from '../../services/wishlistService';
import { useAuth } from '../../context/AuthContext';
import { usePreferenceStore } from '../../store/preferenceStore';
import { formatPriceWithCurrency } from '../../utils/pricing';

export default function ProfileWishlist() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const [items, setItems] = useState<WishlistItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [toast, setToast] = useState('');
  const preferredCurrency = usePreferenceStore((state) => state.currency);

  useEffect(() => {
    loadWishlist();
  }, []);

  const loadWishlist = async () => {
    setIsLoading(true);
    try {
      const data = await wishlistService.getWishlist();
      setItems(data.items);
    } catch (error) {
      console.error('Error loading wishlist:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const showToast = (message: string) => {
    setToast(message);
    setTimeout(() => setToast(''), 3500);
  };

  const handleRemove = async (productId: string) => {
    try {
      await wishlistService.removeFromWishlist(productId);
      setItems((prev) => prev.filter((item) => item.product_id !== productId));
      showToast('Item removed from wishlist');
    } catch (error) {
      console.error('Error removing from wishlist:', error);
      showToast('Failed to remove item');
    }
  };

  const handleProductClick = (slug: string) => {
    navigate(ROUTES.PRODUCT_DETAIL.replace(':id', slug));
  };

  const handleSignOut = async () => {
    await logout();
    navigate(ROUTES.LOGIN, { replace: true });
  };

  const menuItems = [
    { label: 'Account Details', route: ROUTES.PROFILE },
    { label: 'Password', route: ROUTES.PROFILE_PASSWORD },
    { label: 'Order History', route: ROUTES.PROFILE_ORDERS },
    { label: 'Address', route: ROUTES.PROFILE_ADDRESS },
    { label: 'Return', route: ROUTES.PROFILE_RETURNS },
    { label: 'Wishlist', route: ROUTES.PROFILE_WISHLIST, active: true },
    { label: 'Newsletter', route: ROUTES.PROFILE_NEWSLETTER },
    { label: 'Manage Preference', route: ROUTES.PROFILE_MANAGE_PREFERENCE },
    { label: 'Payments', route: ROUTES.PROFILE_PAYMENTS },
    { label: 'Sign Out', onClick: handleSignOut },
  ];

  const formatPrice = (price: number, salePrice?: number) => {
    const displayPrice = salePrice && salePrice < price ? salePrice : price;
    return formatPriceWithCurrency(displayPrice, preferredCurrency);
  };

  const getWishlistImage = (item: WishlistItem) => {
    return item.product_image && item.product_image.trim().length > 0
      ? item.product_image
      : IMAGE_CONFIG.PLACEHOLDER;
  };

  return (
    <Layout>
      {toast && (
        <div className="fixed top-0 inset-x-0 z-50 bg-primary text-white shadow-md">
          <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-3 text-center text-sm">
            <p className="font-semibold uppercase tracking-[0.3em]">Wishlist</p>
            <p className="text-white/90">{toast}</p>
          </div>
        </div>
      )}
      <div className="bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-10 lg:py-16 flex flex-col gap-10 lg:flex-row">
          <ProfileMenu items={menuItems} onNavigate={(route) => navigate(route)} />
          <section className="flex-1">
            <header className="mb-8">
              <p className="text-xs uppercase tracking-[0.3em] text-gray-400">Wishlist</p>
            </header>

            {isLoading ? (
              <div className="flex items-center justify-center py-12">
                <div className="text-sm text-gray-500">Loading wishlist...</div>
              </div>
            ) : items.length === 0 ? (
              <div className="text-center py-16 space-y-4">
                <p className="text-sm font-semibold text-gray-700">You haven't saved any items yet.</p>
                <p className="text-xs text-gray-500">Explore collections and tap the heart icon to add favourites.</p>
                <button
                  type="button"
                  onClick={() => navigate(ROUTES.HOME)}
                  className="px-6 py-3 bg-primary text-white rounded-sm text-sm font-semibold hover:bg-primary-dark transition"
                >
                  Start Shopping
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
                {items.map((item) => (
                  <article key={item.id} className="flex flex-col h-full space-y-4">
                    <div
                      className="relative bg-gray-100 aspect-[3/4] rounded-sm flex items-center justify-center overflow-hidden cursor-pointer group"
                      onClick={() => handleProductClick(item.product_slug)}
                    >
                      <img
                        src={getWishlistImage(item)}
                        alt={item.product_title}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        onError={(event) => {
                          event.currentTarget.src = IMAGE_CONFIG.PLACEHOLDER;
                          event.currentTarget.onerror = null;
                        }}
                      />
                      <Heart className="absolute top-4 right-4 w-5 h-5 text-white fill-white" />
                      {!item.is_active && (
                        <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                          <span className="text-white text-xs uppercase tracking-[0.3em]">Unavailable</span>
                        </div>
                      )}
                    </div>
                    <div className="space-y-1 text-sm text-gray-700">
                      <p className="text-xs uppercase tracking-[0.3em] text-gray-500">{item.product_vendor_name}</p>
                      <p
                        className="text-sm text-gray-900 hover:underline cursor-pointer"
                        onClick={() => handleProductClick(item.product_slug)}
                      >
                        {item.product_title}
                      </p>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-gray-900">
                          {formatPrice(item.product_price, item.product_sale_price)}
                        </p>
                        {item.product_sale_price && item.product_sale_price < item.product_price && (
                          <p className="text-xs text-gray-500 line-through">
                            {formatPriceWithCurrency(item.product_price, preferredCurrency)}
                          </p>
                        )}
                      </div>
                    </div>
                    <div className="space-y-3 mt-auto">
                      <button
                        type="button"
                        onClick={() => handleProductClick(item.product_slug)}
                        disabled={!item.is_active}
                        className="w-full rounded-sm bg-primary text-white text-xs font-semibold uppercase tracking-[0.3em] py-3 hover:bg-primary-dark transition disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {item.is_active ? 'View Product' : 'Unavailable'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRemove(item.product_id)}
                        className="w-full rounded-sm border border-primary text-primary text-xs font-semibold uppercase tracking-[0.3em] py-3 hover:bg-primary hover:text-white transition"
                      >
                        Remove item
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </Layout>
  );
}
