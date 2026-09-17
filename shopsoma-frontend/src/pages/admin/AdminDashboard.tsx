import {
  BarChart3,
  FileText,
  Package,
  Settings,
  ShoppingCart,
  UserRound,
  Users,
  Wallet,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import AdminSidebar from '../../components/admin/AdminSidebar';
import { ROUTES } from '../../config/constants';

const overviewLinks = [
  {
    label: 'Vendor Applications',
    description: 'Review and approve new vendor applications.',
    route: ROUTES.ADMIN_VENDOR_APPLICATIONS,
    icon: FileText,
  },
  {
    label: 'Vendors',
    description: 'Manage approved vendors and storefront access.',
    route: ROUTES.ADMIN_VENDORS,
    icon: Users,
  },
  {
    label: 'Users',
    description: 'Review customer accounts and account status.',
    route: ROUTES.ADMIN_USERS,
    icon: UserRound,
  },
  {
    label: 'Orders',
    description: 'Monitor orders and fulfillment activity.',
    route: '/admin/orders',
    icon: ShoppingCart,
  },
  {
    label: 'Returns',
    description: 'Review and manage customer return requests.',
    route: ROUTES.ADMIN_RETURNS,
    icon: Package,
  },
  {
    label: 'Products',
    description: 'Moderate and manage the marketplace catalog.',
    route: ROUTES.ADMIN_PRODUCTS,
    icon: Package,
  },
  {
    label: 'Payouts',
    description: 'Review vendor payout activity and records.',
    route: ROUTES.ADMIN_PAYOUTS,
    icon: Wallet,
  },
  {
    label: 'Analytics',
    description: 'View marketplace performance insights.',
    route: '/admin/analytics',
    icon: BarChart3,
  },
  {
    label: 'Settings',
    description: 'Configure platform-wide operational settings.',
    route: '/admin/settings',
    icon: Settings,
  },
] as const;

export default function AdminDashboard() {
  return (
    <div className="min-h-screen bg-[var(--color-page-bg)] md:flex">
      <AdminSidebar activePrimary="dashboard" />
      <main className="min-w-0 flex-1 p-5 sm:p-8">
        <div className="mx-auto max-w-6xl space-y-8">
          <header className="border-b border-gray-200 pb-6">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#105E53]">ShopSoma admin</p>
            <h1 className="mt-2 font-display text-3xl font-semibold text-gray-900 sm:text-4xl">Overview</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-gray-600">
              Move directly to the area you need to manage. Each workspace below opens the existing admin flow.
            </p>
          </header>

          <section aria-labelledby="admin-workspaces-heading">
            <div className="mb-4 flex items-end justify-between gap-4">
              <div>
                <h2 id="admin-workspaces-heading" className="text-lg font-semibold text-gray-900">Admin workspaces</h2>
                <p className="mt-1 text-sm text-gray-500">Choose a workspace to continue.</p>
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {overviewLinks.map(({ label, description, route, icon: Icon }) => (
                <Link
                  key={label}
                  to={route}
                  className="group flex min-h-36 flex-col justify-between rounded-2xl border border-gray-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-[#105E53]/40 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-[#105E53] focus:ring-offset-2"
                >
                  <span className="flex items-start justify-between gap-4">
                    <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#105E53]/10 text-[#105E53]">
                      <Icon aria-hidden="true" className="h-5 w-5" />
                    </span>
                    <span aria-hidden="true" className="text-lg text-gray-400 transition group-hover:translate-x-1 group-hover:text-[#105E53]">→</span>
                  </span>
                  <span className="mt-6">
                    <span className="block text-sm font-semibold text-gray-900">{label}</span>
                    <span className="mt-1 block text-sm leading-5 text-gray-500">{description}</span>
                  </span>
                </Link>
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
