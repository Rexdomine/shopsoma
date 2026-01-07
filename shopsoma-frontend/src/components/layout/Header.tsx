import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Bookmark, Menu, Search, User, X } from 'lucide-react';
import { ROUTES } from '../../config/constants';
import { useCartStore } from '../../store/cartStore';
import { useAuth } from '../../context/AuthContext';
import { useCurrencyStore } from '../../store/currencyStore';
import type { Currency } from '../../store/currencyStore';
import { usePreferenceStore } from '../../store/preferenceStore';

export default function Header() {
  const [searchOpen, setSearchOpen] = useState(false);
  const [currencyDropdownOpen, setCurrencyDropdownOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const navigate = useNavigate();
  const cart = useCartStore((state) => state.cart);
  const itemCount = cart.summary.itemCount;
  const { isAuthenticated, user } = useAuth();
  const { currentCurrency, setCurrency } = useCurrencyStore();
  const setPreferredCurrency = usePreferenceStore((state) => state.setCurrency);
  const currencyDropdownRef = useRef<HTMLDivElement>(null);

  const handleProfileClick = () => {
    // Check localStorage directly - it's the source of truth
    // Don't rely on context state as it may not have re-rendered yet
    const token = localStorage.getItem('shopsoma_access_token');
    const userStr = localStorage.getItem('shopsoma_user');

    console.log('Profile Click Debug:', {
      isAuthenticated,
      hasToken: !!token,
      hasUser: !!user,
      hasUserInStorage: !!userStr
    });

    // Only check localStorage, not context state
    if (token && userStr) {
      navigate(ROUTES.PROFILE);
    } else {
      navigate(ROUTES.LOGIN);
    }
  };

  // Get user initials from full name
  const getUserInitials = (fullName: string): string => {
    const names = fullName.trim().split(' ');
    if (names.length === 1) {
      return names[0].charAt(0).toUpperCase();
    }
    return (names[0].charAt(0) + names[names.length - 1].charAt(0)).toUpperCase();
  };

  // Close currency dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (currencyDropdownRef.current && !currencyDropdownRef.current.contains(event.target as Node)) {
        setCurrencyDropdownOpen(false);
      }
    }

    if (currencyDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [currencyDropdownOpen]);

  // Handle currency selection
  const handleCurrencyChange = (currency: Currency) => {
    setCurrency(currency);
    setPreferredCurrency(currency);
    setCurrencyDropdownOpen(false);
  };

  // Get currency display info
  const getCurrencyDisplay = (currency: Currency) => {
    return currency === 'NGN'
      ? { symbol: '₦', code: 'NGN' }
      : { symbol: '$', code: 'USD' };
  };

  const currentCurrencyDisplay = getCurrencyDisplay(currentCurrency);

  return (
    <>
      <header className="bg-[var(--color-page-bg)] text-primary border-b border-primary relative z-30">
        <div className="max-w-6xl mx-auto px-4 sm:px-8 py-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 flex-1">
            <div className="flex items-center gap-3 sm:hidden">
              <button
                type="button"
                onClick={() => setMobileMenuOpen((prev) => !prev)}
                className="p-1.5 hover:text-primary-dark"
                aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
              >
                {mobileMenuOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
              </button>
              <button
                onClick={() => setSearchOpen(true)}
                className="p-1.5 hover:text-primary-dark"
                aria-label="Open search"
              >
                <Search className="w-6 h-6" />
              </button>
            </div>
            <button
              onClick={() => setSearchOpen(true)}
              className="hidden sm:flex items-center gap-2 header-nav-text text-primary hover:text-primary-dark transition-colors"
              aria-label="Open search"
            >
              <Search className="w-5 h-5" />
              <span>Search</span>
            </button>
          </div>

          <div className="flex items-center justify-center flex-shrink-0">
            <Link to={ROUTES.HOME} className="flex items-center justify-center">
              <img
                src="/images/somalogo.svg"
                alt="Shopsoma"
                className="h-8 w-auto"
              />
            </Link>
          </div>

          <div className="flex items-center justify-end gap-2 sm:gap-4 text-sm font-ui flex-1">
            {/* Currency Switcher */}
            <div className="hidden sm:block relative" ref={currencyDropdownRef}>
              <button
                onClick={() => setCurrencyDropdownOpen(!currencyDropdownOpen)}
                className="inline-flex items-center gap-1 text-primary hover:text-primary-dark transition-colors"
                aria-label="Change currency"
              >
                ({currentCurrencyDisplay.symbol}) {currentCurrencyDisplay.code}{' '}
                <span className="text-[10px]">▼</span>
              </button>

              {/* Currency Dropdown */}
              {currencyDropdownOpen && (
                <div className="absolute top-full right-0 mt-2 w-32 bg-white border border-primary shadow-lg z-50">
                  <button
                    onClick={() => handleCurrencyChange('NGN')}
                    className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors ${
                      currentCurrency === 'NGN' ? 'bg-gray-100 font-semibold' : ''
                    }`}
                    style={{ color: '#1E5053' }}
                  >
                    (₦) NGN
                  </button>
                  <button
                    onClick={() => handleCurrencyChange('USD')}
                    className={`w-full px-4 py-2 text-left text-sm hover:bg-gray-50 transition-colors ${
                      currentCurrency === 'USD' ? 'bg-gray-100 font-semibold' : ''
                    }`}
                    style={{ color: '#1E5053' }}
                  >
                    ($) USD
                  </button>
                </div>
              )}
            </div>

            <Link to={ROUTES.PROFILE_WISHLIST || ROUTES.PROFILE} className="hidden sm:inline-flex p-1.5 hover:text-primary-dark" aria-label="Wishlist">
              <Bookmark className="w-5 h-5" />
            </Link>
            <button onClick={handleProfileClick} className="p-1.5 hover:text-primary-dark" aria-label="Account">
              {isAuthenticated && user ? (
                <div className="w-8 h-8 rounded-full bg-primary text-white flex items-center justify-center text-xs font-semibold">
                  {getUserInitials(user.full_name)}
                </div>
              ) : (
                <User className="w-5 h-5" />
              )}
            </button>
            <Link to={ROUTES.CART} className="relative hover:text-primary-dark flex items-center gap-1" aria-label="Shopping bag">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/>
                <line x1="3" y1="6" x2="21" y2="6"/>
                <path d="M16 10a4 4 0 0 1-8 0"/>
              </svg>
              <span className="text-sm font-ui">({itemCount})</span>
            </Link>
          </div>
        </div>

        <nav className="hidden sm:block border-t border-primary">
          <div className="main-nav header-nav-text w-full mx-auto px-8 py-2 flex items-center justify-center gap-8 text-primary">
            <Link to={ROUTES.DESIGNERS} className="hover:text-primary-dark">Designers</Link>
            <Link to={ROUTES.NEW_ARRIVALS} className="hover:text-primary-dark">New</Link>
            <Link to={ROUTES.MEN} className="hover:text-primary-dark">Men</Link>
            <Link to={ROUTES.WOMEN} className="hover:text-primary-dark">Women</Link>
            <Link to={ROUTES.PERFUMES} className="hover:text-primary-dark">Perfumes</Link>
            <Link to={ROUTES.BAGS_WALLETS} className="hover:text-primary-dark">Bags &amp; Wallets</Link>
          </div>
        </nav>

        {mobileMenuOpen && (
          <div className="sm:hidden border-t border-primary bg-[var(--color-page-bg)] px-6 py-6">
            <div className="space-y-4 text-2xl font-serif" style={{ color: '#1E5053' }}>
              <Link to={ROUTES.NEW_ARRIVALS} className="block" onClick={() => setMobileMenuOpen(false)}>
                New
              </Link>
              <Link to={ROUTES.MEN} className="block" onClick={() => setMobileMenuOpen(false)}>
                Men
              </Link>
              <Link to={ROUTES.WOMEN} className="block" onClick={() => setMobileMenuOpen(false)}>
                Women
              </Link>
              <Link to={ROUTES.PERFUMES} className="block" onClick={() => setMobileMenuOpen(false)}>
                Perfumes
              </Link>
              <Link to={ROUTES.BAGS_WALLETS} className="block" onClick={() => setMobileMenuOpen(false)}>
                Bags And Wallets
              </Link>
            </div>
          </div>
        )}
      </header>
      <PremiumSearchOverlay open={searchOpen} onClose={() => setSearchOpen(false)} />
    </>
  );
}

type OverlayProps = {
  open: boolean;
  onClose: () => void;
};

function PremiumSearchOverlay({ open, onClose }: OverlayProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [activeFilter, setActiveFilter] = useState<string>('All');

  useEffect(() => {
    if (!open) return undefined;

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
      if (event.key === 'Enter' && searchQuery.trim()) {
        handleSearch();
      }
    };

    document.addEventListener('keydown', handleKey);
    inputRef.current?.focus();

    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onClose, searchQuery]);

  const handleSearch = () => {
    const params = new URLSearchParams();
    if (searchQuery.trim()) {
      params.set('q', searchQuery.trim());
    }
    if (activeFilter && activeFilter !== 'All') {
      params.set('category', activeFilter);
    }

    navigate(`${ROUTES.PRODUCTS}?${params.toString()}`);
    onClose();
    setSearchQuery('');
    setActiveFilter('All');
  };

  return (
    <div
      className={`fixed inset-0 z-40 transition-all duration-300 ${
        open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
      }`}
    >
      <div
        className={`absolute inset-0 bg-white/90 backdrop-blur-sm transition-opacity duration-300 ${
          open ? 'opacity-100' : 'opacity-0'
        }`}
        onClick={onClose}
      />
      <div className="relative z-10 max-w-5xl mx-auto px-4 sm:px-6">
        <div
          className={`mt-10 bg-white shadow-2xl border border-gray-100 overflow-hidden transition-all duration-300 ${
            open ? 'translate-y-0 opacity-100' : '-translate-y-6 opacity-0'
          }`}
        >
          <form onSubmit={(e) => { e.preventDefault(); handleSearch(); }}>
            <div className="relative">
              <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
              <input
                ref={inputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search for an item, a brand or a category..."
                className="w-full h-16 pl-14 pr-14 text-base sm:text-lg text-gray-800 placeholder:text-gray-400 border-b border-gray-100 focus:outline-none"
              />
              <button
                type="button"
                aria-label="Close search"
                className="absolute right-6 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-900 transition"
                onClick={onClose}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="px-8 py-6 text-center space-y-4">
              <div className="flex items-center justify-center flex-wrap gap-3 text-sm font-semibold uppercase tracking-[0.25em]">
                {['All', 'Women', 'Men', 'Girls', 'Boys', 'Home'].map((label) => {
                  const isActive = activeFilter === label;
                  return (
                    <button
                      key={label}
                      type="button"
                      onClick={() => setActiveFilter(label)}
                      className={`px-5 py-2 border transition focus:outline-none ${
                        isActive
                          ? 'border-primary text-primary bg-primary/5'
                          : 'border-transparent text-gray-500 hover:text-primary hover:border-primary/40'
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>

              <button
                type="submit"
                disabled={!searchQuery.trim()}
                className="px-8 py-3 bg-primary text-white font-semibold hover:bg-primary-dark transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Search
              </button>

              <div className="space-y-2">
                <p className="text-sm font-semibold text-gray-900">
                  Looking for something special?
                </p>
                <p className="text-sm text-gray-500">
                  Search curated designer brands, lifestyle edits, and categories crafted for you.
                </p>
              </div>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
