import { useEffect, useMemo, useRef, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Heart, Search, ShoppingBag, User, Menu, X } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import useCartStore from '../../store/cartStore';
import CartModal from '../cart/CartModal';
import SearchModal from '../search/SearchModal';
import UserMenu from './UserMenu';
import { usePreferenceStore } from '../../store/preferenceStore';
import { useWishlistStore } from '../../store/wishlistStore';

const mainNavItems = [
  { label: 'New', path: '/products/new' },
  { label: 'Men', path: '/products/men' },
  { label: 'Women', path: '/products/women' },
  { label: 'Perfumes', path: '/products/perfumes' },
  { label: 'Bags and Wallets', path: '/products/bags-wallets' },
];

const utilityNavItems = [
  { label: 'Designers', path: '/designers' },
];

const pathIsCategory = (path: string) =>
  ['/products/men', '/products/women', '/products/perfumes', '/products/bags-wallets'].includes(path);

const useHeaderLinks = () => {
  const { pathname } = useLocation();
  return useMemo(() => {
    if (pathname === '/') {
      return { primary: utilityNavItems, secondary: mainNavItems };
    }
    return { primary: mainNavItems, secondary: utilityNavItems };
  }, [pathname]);
};

export default function Header() {
  const { user } = useAuth();
  const { cartItems, toggleCart } = useCartStore();
  const isCartOpen = useCartStore((state) => state.isCartOpen);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const navLinks = useHeaderLinks();
  const { wishlistItems } = useWishlistStore();
  const { interest } = usePreferenceStore();
  const navigate = useNavigate();

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogoClick = () => {
    navigate('/');
  };

  return (
    <header className="sticky top-0 z-40 bg-[#f0f5f3] border-b border-[#1E5053]">
      {/* Desktop Navigation */}
      <div className="hidden lg:block">
        <div className="max-w-7xl mx-auto px-4">
          <div className="flex items-center justify-between py-4">
            <div className="flex-1 flex items-center space-x-4">
              {navLinks.primary.map((item) => (
                <NavLink
                  key={item.label}
                  to={item.path}
                  className={({ isActive }) =>
                    `text-sm font-ui uppercase tracking-wider ${
                      isActive ? 'text-primary font-semibold' : 'text-gray-700'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>

            <div className="flex-1 text-center">
              <button
                type="button"
                onClick={handleLogoClick}
                className="text-2xl font-logo text-[#1E5053]"
              >
                SHOPSOMA
              </button>
            </div>

            <div className="flex-1 flex items-center justify-end space-x-4">
              <button
                type="button"
                className="text-gray-700"
                onClick={() => setIsSearchOpen(true)}
              >
                <Search className="w-5 h-5" />
              </button>
              <NavLink to="/wishlist" className="text-gray-700">
                <Heart className="w-5 h-5" />
              </NavLink>
              <div className="relative" ref={userMenuRef}>
                <button
                  type="button"
                  className="text-gray-700"
                  onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                >
                  <User className="w-5 h-5" />
                </button>
                {isUserMenuOpen && <UserMenu onClose={() => setIsUserMenuOpen(false)} />}
              </div>
              <button
                type="button"
                className="relative text-gray-700"
                onClick={toggleCart}
              >
                <ShoppingBag className="w-5 h-5" />
                {cartItems.length > 0 && (
                  <span className="absolute -top-2 -right-2 bg-primary text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                    {cartItems.length}
                  </span>
                )}
              </button>
            </div>
          </div>

          <nav className="flex justify-center space-x-6 pb-4">
            {navLinks.secondary.map((item) => (
              <NavLink
                key={item.label}
                to={item.path}
                className={({ isActive }) =>
                  `text-sm font-ui uppercase tracking-wider ${
                    isActive ? 'text-primary font-semibold' : 'text-gray-700'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>

      {/* Mobile Navigation */}
      <div className="lg:hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-4">
            <button
              type="button"
              className="text-[#1E5053]"
              onClick={() => setIsMobileMenuOpen(true)}
            >
              <Menu className="w-6 h-6" />
            </button>
            <button
              type="button"
              className="text-[#1E5053]"
              onClick={() => setIsSearchOpen(true)}
            >
              <Search className="w-6 h-6" />
            </button>
          </div>

          <button
            type="button"
            onClick={handleLogoClick}
            className="text-xl font-logo text-[#1E5053]"
          >
            SHOPSOMA
          </button>

          <div className="flex items-center gap-4">
            <NavLink to={user ? '/profile' : '/login'} className="text-[#1E5053]">
              <User className="w-6 h-6" />
            </NavLink>
            <button
              type="button"
              className="relative text-[#1E5053]"
              onClick={toggleCart}
            >
              <ShoppingBag className="w-6 h-6" />
              {cartItems.length > 0 && (
                <span className="absolute -top-2 -right-2 bg-primary text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                  {cartItems.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {isMobileMenuOpen && (
          <div className="fixed inset-0 z-50 bg-[#f0f5f3]">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E5053]">
              <div className="flex items-center gap-4">
                <button
                  type="button"
                  className="text-[#1E5053]"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  <X className="w-6 h-6" />
                </button>
                <button
                  type="button"
                  className="text-[#1E5053]"
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    setIsSearchOpen(true);
                  }}
                >
                  <Search className="w-6 h-6" />
                </button>
              </div>
              <button
                type="button"
                onClick={handleLogoClick}
                className="text-xl font-logo text-[#1E5053]"
              >
                SHOPSOMA
              </button>
              <div className="flex items-center gap-4">
                <NavLink to={user ? '/profile' : '/login'} className="text-[#1E5053]">
                  <User className="w-6 h-6" />
                </NavLink>
                <button
                  type="button"
                  className="relative text-[#1E5053]"
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    toggleCart();
                  }}
                >
                  <ShoppingBag className="w-6 h-6" />
                  {cartItems.length > 0 && (
                    <span className="absolute -top-2 -right-2 bg-primary text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
                      {cartItems.length}
                    </span>
                  )}
                </button>
              </div>
            </div>

            <nav className="px-6 py-6 space-y-6">
              {mainNavItems.map((item) => (
                <NavLink
                  key={item.label}
                  to={item.path}
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `block text-2xl font-serif ${
                      isActive ? 'text-primary' : 'text-[#1E5053]'
                    }`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </div>
        )}
      </div>

      {isSearchOpen && <SearchModal onClose={() => setIsSearchOpen(false)} />}
      {isCartOpen && <CartModal onClose={toggleCart} />}
    </header>
  );
}
