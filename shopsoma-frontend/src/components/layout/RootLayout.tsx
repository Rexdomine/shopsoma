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

const TRANSACTIONAL_RETURN_PATHS = [
  '/checkout',
  '/order-success',
  '/orders',
  '/track',
  '/profile/payments',
];

type GateState = 'loading' | 'open' | 'closed';

function startsAtPath(pathname: string, path: string): boolean {
  return pathname === path || pathname.startsWith(`${path}/`);
}

export function shouldBypassComingSoon(pathname: string, role?: User['role'] | null): boolean {
  return role === 'admin'
    || pathname.startsWith('/admin')
    || pathname.startsWith('/vendor')
    || AUTH_ENTRY_PATHS.has(pathname)
    || TRANSACTIONAL_RETURN_PATHS.some((path) => startsAtPath(pathname, path));
}

export function gateLocationKey(pathname: string, search: string): string {
  return `${pathname}${search}`;
}

/**
 * Root Layout Component
 * Wraps all routes and handles scroll restoration
 */
export default function RootLayout() {
  const { pathname } = useLocation();
  const { user, isLoading: authLoading } = useAuth();
  const [gateState, setGateState] = useState<GateState>('loading');
  const [resolvedScope, setResolvedScope] = useState<'public' | 'bypass' | null>(null);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  const bypassComingSoon = shouldBypassComingSoon(pathname, user?.role);
  const gateScope = bypassComingSoon ? 'bypass' : 'public';

  useEffect(() => {
    if (resolvedScope === gateScope) return undefined;
    if (bypassComingSoon) {
      setGateState('open');
      setResolvedScope('bypass');
      return undefined;
    }

    let mounted = true;
    setGateState('loading');
    getComingSoonSettings().then((settings) => {
      if (mounted) {
        setGateState(settings.enabled ? 'closed' : 'open');
        setResolvedScope('public');
      }
    }).catch(() => {
      if (mounted) {
        setGateState('open');
        setResolvedScope('public');
      }
    });
    return () => { mounted = false; };
  }, [bypassComingSoon, gateScope, resolvedScope]);

  if (authLoading || (!bypassComingSoon && (gateState === 'loading' || resolvedScope !== 'public'))) {
    return <Loading fullScreen message="Preparing ShopSoma..." />;
  }

  if (gateState === 'closed' && !bypassComingSoon) {
    return <ComingSoon onReleased={() => setGateState('open')} />;
  }

  return <Outlet />;
}
