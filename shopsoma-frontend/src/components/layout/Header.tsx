import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, ShoppingCart, User, X } from 'lucide-react';

export default function Header() {
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <>
    <header className="bg-white border-b border-gray-200">
      {/* Top Bar - Primary Navigation */}
      <div className="border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-12">
            {/* Logo */}
            <Link to="/" className="flex items-center">
              <img
                src="/images/logo.svg"
                alt="Shopsoma"
                className="h-8 w-auto"
              />
            </Link>

            {/* Primary Nav */}
            <nav className="hidden md:flex items-center space-x-8">
              <Link to="/men" className="text-sm font-medium text-gray-600 hover:text-gray-900">
                MEN
              </Link>
              <Link to="/women" className="text-sm font-medium text-gray-600 hover:text-gray-900">
                WOMEN
              </Link>
              <Link to="/" className="text-sm font-medium text-primary">
                HOME
              </Link>
            </nav>

            {/* Right Icons */}
            <div className="flex items-center space-x-4">
              <button className="p-2 text-gray-600 hover:text-gray-900" onClick={() => setSearchOpen(true)}>
                <Search className="w-5 h-5" />
              </button>
              <button className="p-2 text-gray-600 hover:text-gray-900 relative">
                <ShoppingCart className="w-5 h-5" />
              </button>
              <button className="p-2 text-gray-600 hover:text-gray-900">
                <User className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Secondary Navigation */}
      <div className="bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex items-center justify-center space-x-8 h-12">
            <Link to="/new" className="text-xs font-medium text-gray-600 hover:text-gray-900 uppercase">
              NEW
            </Link>
            <Link to="/collections" className="text-xs font-medium text-gray-600 hover:text-gray-900 uppercase">
              COLLECTIONS
            </Link>
            <Link to="/home-accessories" className="text-xs font-medium text-gray-600 hover:text-gray-900 uppercase">
              HOME ACCESSORIES
            </Link>
            <Link to="/guides" className="text-xs font-medium text-gray-600 hover:text-gray-900 uppercase">
              CUSTOMERS & GUIDES
            </Link>
            <Link to="/furniture" className="text-xs font-medium text-gray-600 hover:text-gray-900 uppercase">
              FURNITURE
            </Link>
            <Link to="/deals" className="text-xs font-medium text-gray-600 hover:text-gray-900 uppercase">
              DEALS
            </Link>
          </nav>
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
  const [activeFilter, setActiveFilter] = useState<string>('Women');

  useEffect(() => {
    if (!open) return undefined;

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKey);
    inputRef.current?.focus();

    return () => document.removeEventListener('keydown', handleKey);
  }, [open, onClose]);

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
          className={`mt-10 rounded-[32px] bg-white shadow-2xl border border-gray-100 overflow-hidden transition-all duration-300 ${
            open ? 'translate-y-0 opacity-100' : '-translate-y-6 opacity-0'
          }`}
        >
          <div className="relative">
            <Search className="absolute left-6 top-1/2 -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              ref={inputRef}
              type="text"
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

          <div className="px-8 py-6 text-center space-y-3">
            <div className="flex items-center justify-center flex-wrap gap-3 text-sm font-semibold uppercase tracking-[0.25em]">
              {['Women', 'Men', 'Girls', 'Boys', 'Home'].map((label) => {
                const isActive = activeFilter === label;
                return (
                  <button
                    key={label}
                    type="button"
                    onClick={() => setActiveFilter(label)}
                    className={`px-5 py-2 rounded-full border transition focus:outline-none ${
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
            <div className="space-y-2">
              <p className="text-sm font-semibold text-gray-900">
                Looking for something special?
              </p>
              <p className="text-sm text-gray-500">
                Search curated designer brands, lifestyle edits, and categories crafted for you.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
