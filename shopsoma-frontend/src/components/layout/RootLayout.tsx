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
  '/register',
]);

const TRANSACTIONAL_RETURN_PATHS = [
  '/checkout',
  '/order-success',
  '/orders',
  '/track',
  '/profile/payments',
];

type GateState = 'loading' | 'open' | 'closed';

export const COMING_SOON_CACHE_MS = 30_000;

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

export function isGateCacheFresh(
  resolvedScope: 'public' | 'bypass' | null,
  gateScope: 'public' | 'bypass',
  resolvedAt: number | null,
  now = Date.now(),
): boolean {
  return resolvedScope === gateScope
    && resolvedAt !== null
    && now - resolvedAt < COMING_SOON_CACHE_MS;
}

export function shouldShowGateLoading(
  authLoading: boolean,
  bypassComingSoon: boolean,
  gateState: GateState,
  resolvedScope: 'public' | 'bypass' | null,
  gateScope: 'public' | 'bypass',
): boolean {
  return authLoading || (!bypassComingSoon && (gateState === 'loading' || resolvedScope !== gateScope));
}

export function gateStateAfterRefreshFailure(
  currentState: GateState,
  isBackgroundRevalidation: boolean,
): GateState {
  return isBackgroundRevalidation ? currentState : 'open';
}

/**
 * Root Layout Component
 * Wraps all routes and handles scroll restoration
 */
export default function RootLayout() {
  const { pathname, search } = useLocation();
  const { user, isLoading: authLoading } = useAuth();
  const [gateState, setGateState] = useState<GateState>('loading');
  const [resolvedScope, setResolvedScope] = useState<'public' | 'bypass' | null>(null);
  const [resolvedAt, setResolvedAt] = useState<number | null>(null);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  const bypassComingSoon = shouldBypassComingSoon(pathname, user?.role);
  const gateScope = bypassComingSoon ? 'bypass' : 'public';
  const locationKey = gateLocationKey(pathname, search);

  useEffect(() => {
    if (isGateCacheFresh(resolvedScope, gateScope, resolvedAt)) return undefined;
    if (bypassComingSoon) {
      setGateState('open');
      setResolvedScope('bypass');
      setResolvedAt(Date.now());
      return undefined;
    }

    let mounted = true;
    const isBackgroundRevalidation = resolvedScope === gateScope;
    if (!isBackgroundRevalidation) setGateState('loading');
    getComingSoonSettings().then((settings) => {
      if (mounted) {
        setGateState(settings.enabled ? 'closed' : 'open');
        setResolvedScope('public');
        setResolvedAt(Date.now());
      }
    }).catch(() => {
      if (mounted) {
        setGateState((currentState) => gateStateAfterRefreshFailure(currentState, isBackgroundRevalidation));
        if (!isBackgroundRevalidation) {
          setResolvedScope('public');
        }
        setResolvedAt(Date.now());
      }
    });
    return () => { mounted = false; };
  }, [bypassComingSoon, gateScope, locationKey, resolvedAt, resolvedScope]);

  useEffect(() => {
    if (resolvedAt === null) return undefined;
    const timeout = window.setTimeout(() => setResolvedAt(null), COMING_SOON_CACHE_MS);
    return () => window.clearTimeout(timeout);
  }, [resolvedAt]);

  if (shouldShowGateLoading(authLoading, bypassComingSoon, gateState, resolvedScope, gateScope)) {
    return <Loading fullScreen message="Preparing ShopSoma..." />;
  }

  if (gateState === 'closed' && !bypassComingSoon) {
    return <ComingSoon onReleased={() => setGateState('open')} />;
  }

  return <Outlet />;
}
