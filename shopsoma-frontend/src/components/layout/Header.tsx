import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Search, ShoppingCart, User, X } from 'lucide-react';
import { ROUTES } from '../../config/constants';
import { useCartStore } from '../../store/cartStore';

export default function Header() {
  const [searchOpen, setSearchOpen] = useState(false);
  const cart = useCartStore((state) => state.cart);
  const itemCount = cart.summary.itemCount;

  return (
    <>
    <header className="bg-white">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
        <div className="grid grid-cols-3 items-center">
          {/* Left nav stack */}
          <div className="flex flex-col gap-3 pt-4">
            <nav className="flex items-center space-x-6 text-sm font-semibold text-primary">
              <Link to="/men" className="hover:text-primary">
                MEN
              </Link>
              <span className="text-gray-300">|</span>
              <Link to="/women" className="hover:text-primary">
                WOMEN
              </Link>
              <span className="text-gray-300">|</span>
            <Link to="/beauty" className="hover:text-primary">
              BEAUTY
            </Link>
            </nav>
            <nav className="flex items-center space-x-6 text-xs font-semibold text-primary uppercase pt-1">
              <Link to="/new" className="hover:text-primary-dark">
                New
              </Link>
              <Link to="/designer" className="hover:text-primary-dark">
                Designer
              </Link>
              <Link to="/clothing" className="hover:text-primary-dark">
                Clothing
              </Link>
            <Link to="/accessories" className="hover:text-primary-dark">
              Accessories
            </Link>
              <Link to="/jewelry" className="hover:text-primary-dark">
                Jewelry
              </Link>
              <Link to="/sales" className="hover:text-primary-dark">
                Sales
              </Link>
            </nav>
          </div>

          {/* Center logo */}
          <div className="flex items-center justify-center">
            <Link to="/" className="flex items-center justify-center">
              <img
                src="/images/somalogo.svg"
                alt="Shopsoma"
                className="h-12 w-auto"
              />
            </Link>
          </div>

          {/* Right icons and search */}
          <div className="flex items-center justify-end gap-4">
            <div className="hidden md:flex items-center bg-white border border-gray-200 px-3 py-2 text-sm text-gray-400">
              <Search className="w-4 h-4 mr-2" />
              <input
                type="text"
                placeholder="Search"
                className="outline-none bg-transparent text-gray-700 w-40"
                onFocus={() => setSearchOpen(true)}
                readOnly
              />
            </div>
            <button className="p-2 text-gray-600 hover:text-gray-900" onClick={() => setSearchOpen(true)}>
              <Search className="w-5 h-5 md:hidden" />
            </button>
            <Link to={ROUTES.CART} className="p-2 text-gray-600 hover:text-gray-900 relative">
              <ShoppingCart className="w-5 h-5" />
              {itemCount > 0 && (
                <span className="absolute -top-1 -right-1 bg-primary text-white text-[10px] font-semibold rounded-full h-4 w-4 flex items-center justify-center">
                  {itemCount > 9 ? '9+' : itemCount}
                </span>
              )}
            </Link>
            <button className="p-2 text-gray-600 hover:text-gray-900">
              <User className="w-5 h-5" />
            </button>
          </div>
        </div>
      </div>
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
