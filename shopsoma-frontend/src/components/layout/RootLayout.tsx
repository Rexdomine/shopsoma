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

type GateState = 'loading' | 'open' | 'closed';

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
  const [gateState, setGateState] = useState<GateState>('loading');

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  const bypassComingSoon = shouldBypassComingSoon(pathname, user?.role);

  useEffect(() => {
    if (bypassComingSoon) {
      setGateState('open');
      return undefined;
    }
    let mounted = true;
    setGateState('loading');
    getComingSoonSettings().then((settings) => {
      if (mounted) setGateState(settings.enabled ? 'closed' : 'open');
    }).catch(() => {
      if (mounted) setGateState('open');
    });
    return () => { mounted = false; };
  }, [bypassComingSoon]);

  if (authLoading || (!bypassComingSoon && gateState === 'loading')) {
    return <Loading fullScreen message="Preparing ShopSoma..." />;
  }

  if (gateState === 'closed' && !bypassComingSoon) {
    return <ComingSoon onReleased={() => setGateState('open')} />;
  }

  return <Outlet />;
}
