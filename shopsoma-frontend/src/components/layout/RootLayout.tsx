import { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

/**
 * Root Layout Component
 * Wraps all routes and handles scroll restoration
 */
export default function RootLayout() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return <Outlet />;
}
