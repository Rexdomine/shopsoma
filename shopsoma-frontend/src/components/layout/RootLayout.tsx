import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import ComingSoon from '../../pages/ComingSoon';
import { getComingSoonSettings } from '../../services/settingsService';
import { useAuth } from '../../context/AuthContext';
import type { User } from '../../types';
import Loading from '../common/Loading';

const AUTH_ENTRY_PATHS = new Set([
  '/login',
  '/vendor/login',
  '/forgot-password',
  '/reset-password',
  '/verify-email',
  '/claim-account',
]);

export function shouldBypassComingSoon(pathname: string, role?: User['role'] | null): boolean {
  return role === 'admin'
    || pathname.startsWith('/admin')
    || pathname.startsWith('/vendor')
    || AUTH_ENTRY_PATHS.has(pathname);
}

/**
 * Root Layout Component
 * Wraps all routes and handles scroll restoration
 */
export default function RootLayout() {
  const { pathname } = useLocation();
  const { user, isLoading: authLoading } = useAuth();
  const [comingSoon, setComingSoon] = useState(false);
  const [comingSoonLoading, setComingSoonLoading] = useState(true);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  const bypassComingSoon = shouldBypassComingSoon(pathname, user?.role);

  useEffect(() => {
    if (bypassComingSoon) {
      setComingSoon(false);
      setComingSoonLoading(false);
      return undefined;
    }
    let mounted = true;
    setComingSoonLoading(true);
    getComingSoonSettings().then((settings) => {
      if (mounted) setComingSoon(settings.enabled);
    }).catch(() => {
      if (mounted) setComingSoon(false);
    }).finally(() => {
      if (mounted) setComingSoonLoading(false);
    });
    return () => { mounted = false; };
  }, [bypassComingSoon]);

  if (authLoading || (!bypassComingSoon && comingSoonLoading)) {
    return <Loading fullScreen message="Preparing ShopSoma..." />;
  }

  return comingSoon && !bypassComingSoon ? <ComingSoon /> : <Outlet />;
}
