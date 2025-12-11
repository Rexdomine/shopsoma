import {
  Bell,
  CreditCard,
  ChevronRight,
  User,
  Truck,
  Boxes,
  Palette,
  Store,
  BarChart3,
  Wallet,
  MessageSquare,
  HelpCircle,
  Settings,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useVendor } from '../../context/VendorContext';
import { ROUTES } from '../../config/constants';

type SidebarProps = {
  disableMain?: boolean;
  activePrimary?: 'settings' | 'products';
  activeSettings?: 'brand-info' | 'payout' | 'security';
  pendingOrders?: number;
  completedOrders?: number;
  onViewStore?: () => void;
};

export default function VendorSidebar({
  disableMain = false,
  activePrimary,
  activeSettings,
  pendingOrders = 0,
  completedOrders = 0,
  onViewStore,
}: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { isOnboarding } = useVendor();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/vendor/login');
    } catch (error) {
      console.error('Logout error:', error);
    }
  };

  // Override disableMain if vendor is in onboarding mode
  const shouldDisableMain = disableMain || isOnboarding;

  const mainNav = useMemo(
    () => [
      { label: 'Dashboard', route: ROUTES.VENDOR_DASHBOARD, icon: 'dashboard', section: 'dashboard' },
      { label: 'Orders', route: ROUTES.VENDOR_ORDERS, icon: 'orders', section: 'orders' },
      { label: 'Products', route: ROUTES.VENDOR_PRODUCTS, icon: 'products', section: 'products' },
      { label: 'Collections', route: '/vendor/collections', icon: 'collections', section: 'collections' },
      { label: 'Marketing', route: '/vendor/marketing', icon: 'marketing', section: 'marketing' },
      { label: 'Analytics', route: '/vendor/analytics', icon: 'analytics', section: 'analytics' },
      { label: 'Earnings & Payout', route: ROUTES.VENDOR_EARNINGS, icon: 'earnings', section: 'earnings' },
    ],
    []
  );

  const renderIcon = (type: string, isActive: boolean = false) => {
    const className = `w-5 h-5 ${isActive ? 'text-[#105E53]' : ''}`;

    switch (type) {
      case 'dashboard':
        return <LayoutDashboard className={className} />;
      case 'orders':
        return <Truck className={className} />;
      case 'products':
        return <Boxes className={className} />;
      case 'collections':
        return <Palette className={className} />;
      case 'marketing':
        return <Store className={className} />;
      case 'analytics':
        return <BarChart3 className={className} />;
      case 'earnings':
        return <Wallet className={className} />;
      case 'settings':
        return <Settings className={className} />;
      case 'messaging':
        return <MessageSquare className={className} />;
      case 'help':
        return <HelpCircle className={className} />;
      default:
        return <Truck className={className} />;
    }
  };

  const handleNav = (route: string, disabled?: boolean) => {
    if (disabled) return;
    navigate(route);
  };

  // Determine active section from current path
  const currentSection = activePrimary || mainNav.find(item =>
    location.pathname.startsWith(item.route)
  )?.section;

  return (
    <aside className={`${isCollapsed ? 'w-[80px]' : 'w-[320px]'} bg-[#F6F6F3] border-r border-gray-200 px-5 py-6 flex flex-col justify-between min-h-screen sticky top-0 transition-all duration-300`}>
      <div className="space-y-6">
        {/* Top brand row */}
        <div className="flex items-center justify-between">
          {!isCollapsed && <span className="text-sm font-semibold tracking-wide text-[#105E53]">SHOPSOMA</span>}
          <div className="flex items-center gap-3 text-gray-700">
            {!isCollapsed && (
              <>
                <Bell className="w-4 h-4" />
                <CreditCard className="w-4 h-4" />
              </>
            )}
            <button
              type="button"
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="p-1.5 hover:bg-gray-200 rounded-lg transition"
              title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              {isCollapsed ? (
                <PanelLeftOpen className="w-4 h-4" />
              ) : (
                <PanelLeftClose className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>

        {/* Vendor card */}
        {!isCollapsed ? (
          <button
            type="button"
            className="w-full bg-white rounded-2xl border border-gray-200 shadow-sm px-3 py-3 flex items-center gap-3 text-left hover:shadow-md transition"
          >
            <div className="h-10 w-10 rounded-full bg-[#105E53]/10 flex items-center justify-center text-[#105E53]">
              <User className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-gray-900 truncate">{user?.full_name || 'Your Brand'}</p>
              <p className="text-xs text-gray-500 truncate">{user?.email || 'email@brand.com'}</p>
            </div>
            <div className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center text-gray-500">
              <ChevronRight className="w-4 h-4" />
            </div>
          </button>
        ) : (
          <div className="flex justify-center">
            <div className="h-10 w-10 rounded-full bg-[#105E53]/10 flex items-center justify-center text-[#105E53]">
              <User className="w-5 h-5" />
            </div>
          </div>
        )}

        {/* Order status */}
        {!isCollapsed && (
          <div className="flex items-center gap-6 text-[12px] font-ui text-[#222] mb-6">
            <span className="flex items-center gap-2 whitespace-nowrap">
              <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
              <span>Pending Orders: {pendingOrders}</span>
            </span>
            <span className="flex items-center gap-2 whitespace-nowrap">
              <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
              <span>Completed Orders: {completedOrders}</span>
            </span>
          </div>
        )}

        {/* Main menu */}
        <nav className="space-y-1">
          {mainNav.map((item) => {
            const isActive = currentSection === item.section;

            return (
              <button
                key={item.label}
                type="button"
                onClick={() => handleNav(item.route, shouldDisableMain)}
                className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2.5 rounded-lg text-[15px] font-medium font-ui transition ${
                  shouldDisableMain
                    ? 'text-gray-400 cursor-not-allowed opacity-60 pointer-events-none'
                    : isActive
                    ? 'bg-white text-[#105E53] shadow-sm border border-gray-100'
                    : 'text-gray-900 hover:bg-gray-100'
                }`}
                title={isCollapsed ? item.label : ''}
              >
                {renderIcon(item.icon, isActive)}
                {!isCollapsed && <span>{item.label}</span>}
              </button>
            );
          })}
        </nav>

        {/* View store */}
        <button
          type="button"
          onClick={() => (onViewStore ? onViewStore() : navigate(ROUTES.PRODUCTS))}
          className={`w-full bg-[#105E53] text-white rounded-full py-3 text-sm font-ui flex items-center justify-center ${isCollapsed ? '' : 'gap-2'} hover:bg-[#0c4c45] transition`}
          title={isCollapsed ? 'View Store' : ''}
        >
          {isCollapsed ? <Store className="w-4 h-4" /> : <>View Store <span aria-hidden>→</span></>}
        </button>
      </div>

      {/* Bottom */}
      <div className="space-y-3 pt-6">
        <button
          type="button"
          onClick={() => handleNav(ROUTES.VENDOR_BRAND_INFO)}
          className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2.5 rounded-lg text-sm font-ui transition ${
            location.pathname.startsWith(ROUTES.VENDOR_BRAND_INFO)
              ? 'bg-white text-[#105E53] shadow-sm border border-gray-100'
              : 'text-gray-700 hover:bg-gray-100'
          }`}
          title={isCollapsed ? 'Storefront Settings' : ''}
        >
          {renderIcon('settings', location.pathname.startsWith(ROUTES.VENDOR_BRAND_INFO))}
          {!isCollapsed && <span>Storefront Settings</span>}
        </button>
        <button
          type="button"
          className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-sm font-ui text-gray-700 hover:bg-gray-100 transition`}
          title={isCollapsed ? 'Messaging' : ''}
        >
          {renderIcon('messaging', false)}
          {!isCollapsed && <span>Messaging</span>}
        </button>
        <button
          type="button"
          className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-sm font-ui text-gray-700 hover:bg-gray-100 transition`}
          title={isCollapsed ? 'Help & Support' : ''}
        >
          {renderIcon('help', false)}
          {!isCollapsed && <span>Help & Support</span>}
        </button>

        {/* Logout Button */}
        <button
          type="button"
          onClick={handleLogout}
          className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-sm font-ui text-red-600 hover:bg-red-50 transition border-t border-gray-200 mt-2 pt-4`}
          title={isCollapsed ? 'Logout' : ''}
        >
          <LogOut className="w-5 h-5" />
          {!isCollapsed && <span>Logout</span>}
        </button>
      </div>
    </aside>
  );
}
