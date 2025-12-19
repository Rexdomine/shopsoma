import {
  LayoutDashboard,
  Users,
  FileText,
  Package,
  ShoppingCart,
  Folder,
  Megaphone,
  BarChart3,
  Wallet,
  Settings,
  HelpCircle,
  LogOut,
  ChevronRight,
  User as UserIcon,
  PanelLeftClose,
  PanelLeftOpen,
  Store,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ROUTES } from '../../config/constants';

type AdminSidebarProps = {
  activeSection?: string;
  activePrimary?: string;
};

export default function AdminSidebar({ activeSection, activePrimary }: AdminSidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);

  const mainNav = useMemo(
    () => [
      { label: 'Overview', route: ROUTES.ADMIN_DASHBOARD, icon: 'dashboard', section: 'dashboard' },
      { label: 'Vendor Applications', route: '/admin/vendor-applications', icon: 'applications', section: 'vendor-applications' },
      { label: 'Vendors', route: ROUTES.ADMIN_VENDORS, icon: 'vendors', section: 'vendors' },
      { label: 'Users', route: ROUTES.ADMIN_USERS, icon: 'users', section: 'users' },
      { label: 'Orders', route: '/admin/orders', icon: 'orders', section: 'orders' },
      { label: 'Products', route: ROUTES.ADMIN_PRODUCTS, icon: 'products', section: 'products' },
      { label: 'Collections', route: '/admin/collections', icon: 'collections', section: 'collections' },
      { label: 'Marketing', route: '/admin/marketing', icon: 'marketing', section: 'marketing' },
      { label: 'Analytics', route: '/admin/analytics', icon: 'analytics', section: 'analytics' },
      { label: 'Payouts', route: '/admin/payouts', icon: 'payouts', section: 'payouts' },
    ],
    []
  );

  const renderIcon = (type: string, isActive: boolean) => {
    const className = `w-5 h-5 ${isActive ? 'text-[#105E53]' : 'text-gray-600'}`;

    switch (type) {
      case 'dashboard':
        return <LayoutDashboard className={className} />;
      case 'applications':
        return <FileText className={className} />;
      case 'vendors':
        return <Users className={className} />;
      case 'users':
        return <UserIcon className={className} />;
      case 'orders':
        return <ShoppingCart className={className} />;
      case 'products':
        return <Package className={className} />;
      case 'collections':
        return <Folder className={className} />;
      case 'marketing':
        return <Megaphone className={className} />;
      case 'analytics':
        return <BarChart3 className={className} />;
      case 'payouts':
        return <Wallet className={className} />;
      case 'settings':
        return <Settings className={className} />;
      case 'help':
        return <HelpCircle className={className} />;
      default:
        return <LayoutDashboard className={className} />;
    }
  };

  const handleNav = (route: string) => {
    navigate(route);
  };

  const handleLogout = async () => {
    await logout();
    navigate(ROUTES.LOGIN);
  };

  // Determine active section from current path
  const currentSection = activeSection || mainNav.find(item =>
    location.pathname.startsWith(item.route)
  )?.section;

  return (
    <aside className={`${isCollapsed ? 'w-[80px]' : 'w-[280px]'} bg-[var(--color-page-bg)] border-r border-gray-200 px-4 py-6 flex flex-col justify-between min-h-screen sticky top-0 transition-all duration-300`}>
      <div className="space-y-6">
        {/* Top brand row */}
        <div className="flex items-center justify-between">
          {!isCollapsed && <span className="text-sm font-semibold tracking-wide text-[#105E53]">SHOPSOMA ADMIN</span>}
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 hover:bg-gray-200 rounded-lg transition ml-auto"
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {isCollapsed ? (
              <PanelLeftOpen className="w-4 h-4" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        </div>

        {/* Admin profile card */}
        {!isCollapsed ? (
          <button
            type="button"
            onClick={() => navigate('/admin/profile')}
            className="w-full bg-white rounded-2xl border border-gray-200 shadow-sm px-3 py-3 flex items-center gap-3 text-left hover:shadow-md transition"
          >
            <div className="h-10 w-10 rounded-full bg-[#105E53]/10 flex items-center justify-center text-[#105E53]">
              <UserIcon className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold text-gray-900 truncate">{user?.full_name || 'Admin'}</p>
              <p className="text-xs text-gray-500 truncate">{user?.email || 'admin@shopsoma.com'}</p>
            </div>
            <div className="h-8 w-8 rounded-full border border-gray-200 flex items-center justify-center text-gray-500">
              <ChevronRight className="w-4 h-4" />
            </div>
          </button>
        ) : (
          <div className="flex justify-center">
            <div className="h-10 w-10 rounded-full bg-[#105E53]/10 flex items-center justify-center text-[#105E53]">
              <UserIcon className="w-5 h-5" />
            </div>
          </div>
        )}

        {/* Main navigation */}
        <nav className="space-y-1">
          {mainNav.map((item) => {
            const isActive = currentSection === item.section;

            return (
              <button
                key={item.label}
                type="button"
                onClick={() => handleNav(item.route)}
                className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2.5 rounded-lg text-[15px] font-medium font-ui transition ${
                  isActive
                    ? 'bg-white text-[#105E53] shadow-sm border border-gray-100'
                    : 'text-gray-700 hover:bg-gray-100'
                }`}
                title={isCollapsed ? item.label : ''}
              >
                {renderIcon(item.icon, isActive)}
                {!isCollapsed && (
                  <>
                    <span>{item.label}</span>
                    {item.label === 'Vendor Applications' && (
                      <span className="ml-auto bg-amber-100 text-amber-800 text-xs px-2 py-0.5 rounded-full font-semibold">
                        New
                      </span>
                    )}
                  </>
                )}
              </button>
            );
          })}
        </nav>

        {/* View store button */}
        <button
          type="button"
          onClick={() => navigate(ROUTES.HOME)}
          className={`w-full bg-[#105E53] text-white rounded-full py-3 text-sm font-ui flex items-center justify-center ${isCollapsed ? '' : 'gap-2'} hover:bg-[#0c4c45] transition`}
          title={isCollapsed ? 'View Storefront' : ''}
        >
          {isCollapsed ? <Store className="w-4 h-4" /> : <>View Storefront <span aria-hidden>→</span></>}
        </button>
      </div>

      {/* Bottom section */}
      <div className="space-y-3 pt-6 border-t border-gray-200">
        <button
          type="button"
          onClick={() => navigate('/admin/settings')}
          className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-sm font-ui transition ${
            activePrimary === 'settings' || location.pathname.startsWith('/admin/settings')
              ? 'text-[#105E53] bg-white border border-gray-100'
              : 'text-gray-700 hover:bg-gray-100'
          }`}
          title={isCollapsed ? 'Settings' : ''}
        >
          {renderIcon('settings', activePrimary === 'settings' || location.pathname.startsWith('/admin/settings'))}
          {!isCollapsed && <span>Settings</span>}
        </button>
        <button
          type="button"
          onClick={() => navigate('/admin/help')}
          className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-sm font-ui text-gray-700 hover:bg-gray-100 transition`}
          title={isCollapsed ? 'Help & Support' : ''}
        >
          {renderIcon('help', false)}
          {!isCollapsed && <span>Help & Support</span>}
        </button>
        <button
          type="button"
          onClick={handleLogout}
          className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'gap-3'} px-3 py-2 rounded-lg text-sm font-ui text-red-600 hover:bg-red-50 transition`}
          title={isCollapsed ? 'Logout' : ''}
        >
          <LogOut className="w-5 h-5" />
          {!isCollapsed && <span>Logout</span>}
        </button>
      </div>
    </aside>
  );
}
