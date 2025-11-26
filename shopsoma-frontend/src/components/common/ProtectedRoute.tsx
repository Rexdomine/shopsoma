/**
 * Protected Route Component
 * Restricts access based on authentication and user roles
 */
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ROUTES } from '../../config/constants';
import Loading from './Loading';

interface ProtectedRouteProps {
  children: React.ReactNode;
  roles?: ('customer' | 'vendor' | 'admin')[];
  requireAuth?: boolean;
}

export default function ProtectedRoute({
  children,
  roles,
  requireAuth = true,
}: ProtectedRouteProps) {
  const { isAuthenticated, user, isLoading } = useAuth();
  const location = useLocation();

  // Show loading while checking auth status
  if (isLoading) {
    return <Loading fullScreen message="Checking authentication..." />;
  }

  // Redirect to login if authentication is required but user is not authenticated
  if (requireAuth && !isAuthenticated) {
    return <Navigate to={ROUTES.LOGIN} state={{ from: location }} replace />;
  }

  // Check if user has required role
  if (roles && roles.length > 0 && user) {
    if (!roles.includes(user.role)) {
      // User doesn't have required role, redirect to appropriate page
      if (user.role === 'vendor') {
        return <Navigate to={ROUTES.VENDOR_DASHBOARD} replace />;
      } else if (user.role === 'admin') {
        return <Navigate to={ROUTES.ADMIN_DASHBOARD} replace />;
      } else {
        return <Navigate to={ROUTES.HOME} replace />;
      }
    }
  }

  // User is authenticated and has required role (if specified)
  return <>{children}</>;
}
