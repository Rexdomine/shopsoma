/**
 * Header Component - Exact Figma Design Match
 */
import { Link } from 'react-router-dom';
import { Search, ShoppingCart, User } from 'lucide-react';

export default function Header() {
  return (
    <header className="bg-white border-b border-gray-200">
      {/* Top Bar - Primary Navigation */}
      <div className="border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-12">
            {/* Logo */}
            <Link to="/" className="flex items-center">
              <span className="text-xl font-display font-bold text-primary">SHOP SOMA</span>
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
              <button className="p-2 text-gray-600 hover:text-gray-900">
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
  );
}
