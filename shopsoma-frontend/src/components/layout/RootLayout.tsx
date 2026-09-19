import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import ComingSoon from '../../pages/ComingSoon';
import { getComingSoonSettings } from '../../services/settingsService';

/**
 * Root Layout Component
 * Wraps all routes and handles scroll restoration
 */
export default function RootLayout() {
  const { pathname } = useLocation();
  const [comingSoon, setComingSoon] = useState(false);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  useEffect(() => {
    if (pathname.startsWith('/admin') || pathname === '/login') {
      setComingSoon(false);
      return undefined;
    }
    let mounted = true;
    getComingSoonSettings().then((settings) => {
      if (mounted) setComingSoon(settings.enabled);
    }).catch(() => {
      if (mounted) setComingSoon(false);
    });
    return () => { mounted = false; };
  }, [pathname]);

  return comingSoon ? <ComingSoon /> : <Outlet />;
}
