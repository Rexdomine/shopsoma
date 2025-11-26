/**
 * React Router Configuration
 */
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { ROUTES } from '../config/constants';
import ErrorBoundary from '../components/error/ErrorBoundary';
import Loading from '../components/common/Loading';
import ProtectedRoute from '../components/common/ProtectedRoute';
import RootLayout from '../components/layout/RootLayout';

// Lazy load pages for code splitting
const Home = lazy(() => import('../pages/Home'));
const ProductDetail = lazy(() => import('../pages/products/ProductDetail'));
const ProductList = lazy(() => import('../pages/products/ProductList'));
const Cart = lazy(() => import('../pages/cart/Cart'));
const Checkout = lazy(() => import('../pages/checkout/Checkout'));
const Register = lazy(() => import('../pages/auth/Register'));
const Login = lazy(() => import('../pages/auth/Login'));
const ForgotPassword = lazy(() => import('../pages/auth/ForgotPassword'));
const VerifyEmail = lazy(() => import('../pages/auth/VerifyEmail'));
const ClaimAccount = lazy(() => import('../pages/auth/ClaimAccount'));
const OrderSuccess = lazy(() => import('../pages/orders/OrderSuccess'));
const OrderTracking = lazy(() => import('../pages/orders/OrderTracking'));
const Profile = lazy(() => import('../pages/profile/Profile'));
const ProfileEdit = lazy(() => import('../pages/profile/ProfileEdit'));
const ProfilePassword = lazy(() => import('../pages/profile/ProfilePassword'));
const ProfileAddress = lazy(() => import('../pages/profile/ProfileAddress'));
const ProfileOrders = lazy(() => import('../pages/profile/ProfileOrders'));
const ProfileReturns = lazy(() => import('../pages/profile/ProfileReturns'));
const ProfileWishlist = lazy(() => import('../pages/profile/ProfileWishlist'));
const ProfileNewsletter = lazy(() => import('../pages/profile/ProfileNewsletter'));
const ProfileManagePreference = lazy(() => import('../pages/profile/ProfileManagePreference'));
const ProfilePayments = lazy(() => import('../pages/profile/ProfilePayments'));
const AdminUsers = lazy(() => import('../pages/admin/AdminUsers'));
const Debug = lazy(() => import('../pages/Debug'));
const NotFound = lazy(() => import('../pages/errors/NotFound'));
const ServerError = lazy(() => import('../pages/errors/ServerError'));

// Create router
const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      {
        path: ROUTES.HOME,
        element: (
          <ErrorBoundary>
            <Suspense fallback={<Loading fullScreen message="Loading..." />}>
              <Home />
            </Suspense>
          </ErrorBoundary>
        ),
      },
      {
        path: ROUTES.PRODUCT_DETAIL,
        element: (
          <ErrorBoundary>
            <Suspense fallback={<Loading fullScreen message="Loading product..." />}>
              <ProductDetail />
            </Suspense>
          </ErrorBoundary>
        ),
      },
  {
    path: ROUTES.PRODUCTS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading products..." />}>
          <ProductList />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.CART,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading cart..." />}>
          <Cart />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.CHECKOUT,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading checkout..." />}>
          <Checkout />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ORDER_SUCCESS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <OrderSuccess />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: '/orders/:orderId',
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading order..." />}>
          <OrderSuccess />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ORDER_TRACKING,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading order..." />}>
          <OrderTracking />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.REGISTER,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading register..." />}>
          <Register />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.LOGIN,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading login..." />}>
          <Login />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.FORGOT_PASSWORD,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ForgotPassword />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VERIFY_EMAIL,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Verifying email..." />}>
          <VerifyEmail />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.CLAIM_ACCOUNT,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ClaimAccount />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading profile..." />}>
          <Profile />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_EDIT,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading profile..." />}>
          <ProfileEdit />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_PASSWORD,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfilePassword />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_ADDRESS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfileAddress />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_ORDERS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfileOrders />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_RETURNS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfileReturns />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_WISHLIST,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfileWishlist />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_NEWSLETTER,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfileNewsletter />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_MANAGE_PREFERENCE,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfileManagePreference />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.PROFILE_PAYMENTS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProfilePayments />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ADMIN_USERS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminUsers />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: '/debug',
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <Debug />
        </Suspense>
      </ErrorBoundary>
    ),
  },
      {
        path: ROUTES.NOT_FOUND,
        element: (
          <Suspense fallback={<Loading fullScreen />}>
            <NotFound />
          </Suspense>
        ),
      },
      {
        path: ROUTES.SERVER_ERROR,
        element: (
          <Suspense fallback={<Loading fullScreen />}>
            <ServerError />
          </Suspense>
        ),
      },
      {
        path: '*',
        element: (
          <Suspense fallback={<Loading fullScreen />}>
            <NotFound />
          </Suspense>
        ),
      },
    ],
  },
]);

export default function AppRouter() {
  return <RouterProvider router={router} />;
}
