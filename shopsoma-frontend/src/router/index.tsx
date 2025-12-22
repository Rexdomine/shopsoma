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
import VendorLayout from '../components/vendor/VendorLayout';

// Lazy load pages for code splitting
const Home = lazy(() => import('../pages/Home'));
const ProductDetail = lazy(() => import('../pages/products/ProductDetail'));
const ProductList = lazy(() => import('../pages/products/ProductList'));
const MenStorefront = lazy(() => import('../pages/products/MenStorefront'));
const WomenStorefront = lazy(() => import('../pages/products/WomenStorefront'));
const Cart = lazy(() => import('../pages/cart/Cart'));
const Checkout = lazy(() => import('../pages/checkout/Checkout'));
const Register = lazy(() => import('../pages/auth/Register'));
const Login = lazy(() => import('../pages/auth/Login'));
const VendorLogin = lazy(() => import('../pages/auth/VendorLogin'));
const VendorSignup = lazy(() => import('../pages/vendor/VendorSignup'));
const VendorSignupBusiness = lazy(() => import('../pages/vendor/VendorSignupBusiness'));
const VendorSignupThankYou = lazy(() => import('../pages/vendor/VendorSignupThankYou'));
const VendorProducts = lazy(() => import('../pages/vendor/VendorProducts'));
const VendorProductAdd = lazy(() => import('../pages/vendor/VendorProductAdd'));
const VendorProductView = lazy(() => import('../pages/vendor/VendorProductView'));
const VendorProductEdit = lazy(() => import('../pages/vendor/VendorProductEdit'));
const VendorOrders = lazy(() => import('../pages/vendor/VendorOrders'));
const VendorOrderDetail = lazy(() => import('../pages/vendor/VendorOrderDetail'));
const VendorEarnings = lazy(() => import('../pages/vendor/VendorEarnings'));
const VendorExpenses = lazy(() => import('../pages/vendor/VendorExpenses'));
const VendorWithdrawals = lazy(() => import('../pages/vendor/VendorWithdrawals'));
const VendorOtp = lazy(() => import('../pages/auth/VendorOtp'));
const VendorSetPassword = lazy(() => import('../pages/auth/VendorSetPassword'));
const VendorDashboard = lazy(() => import('../pages/vendor/VendorDashboard'));
const ForgotPassword = lazy(() => import('../pages/auth/ForgotPassword'));
const VerifyEmail = lazy(() => import('../pages/auth/VerifyEmail'));
const ClaimAccount = lazy(() => import('../pages/auth/ClaimAccount'));
const OrderSuccess = lazy(() => import('../pages/orders/OrderSuccess'));
const OrderTracking = lazy(() => import('../pages/orders/OrderTracking'));
const BrandInfoSettings = lazy(() => import('../pages/vendor/BrandInfoSettings'));
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
const AdminProducts = lazy(() => import('../pages/admin/AdminProducts'));
const AdminProductDetail = lazy(() => import('../pages/admin/AdminProductDetail'));
const AdminProductEdit = lazy(() => import('../pages/admin/AdminProductEdit'));
const AdminVendorApplications = lazy(() => import('../pages/admin/AdminVendorApplications'));
const AdminVendorApplicationDetail = lazy(() => import('../pages/admin/AdminVendorApplicationDetail'));
const AdminVendors = lazy(() => import('../pages/admin/AdminVendors'));
const AdminVendorDetail = lazy(() => import('../pages/admin/AdminVendorDetail'));
const AdminSettings = lazy(() => import('../pages/admin/AdminSettings'));
const AdminOrders = lazy(() => import('../pages/admin/AdminOrders'));
const AdminOrderDetail = lazy(() => import('../pages/admin/AdminOrderDetail'));
const AdminPayouts = lazy(() => import('../pages/admin/AdminPayouts'));
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
    path: ROUTES.WOMEN,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading womenswear..." />}>
          <WomenStorefront />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.MEN,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading menswear..." />}>
          <MenStorefront />
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
    path: ROUTES.VENDOR_LOGIN,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading vendor login..." />}>
          <VendorLogin />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_SIGNUP,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading vendor signup..." />}>
          <VendorSignup />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_SIGNUP_BUSINESS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading business info..." />}>
          <VendorSignupBusiness />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_SIGNUP_THANK_YOU,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading confirmation..." />}>
          <VendorSignupThankYou />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_PRODUCTS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading products..." />}>
          <VendorLayout>
            <VendorProducts />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: `${ROUTES.VENDOR_PRODUCTS}/new`,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <VendorLayout>
            <VendorProductAdd />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: `${ROUTES.VENDOR_PRODUCTS}/:id/view`,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading product..." />}>
          <VendorLayout>
            <VendorProductView />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: `${ROUTES.VENDOR_PRODUCTS}/:id/edit`,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading product..." />}>
          <VendorLayout>
            <VendorProductEdit />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_ORDERS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading orders..." />}>
          <VendorLayout>
            <VendorOrders />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_ORDER_DETAIL,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading order..." />}>
          <VendorLayout>
            <VendorOrderDetail />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_BRAND_INFO,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading settings..." />}>
          <VendorLayout>
            <BrandInfoSettings />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_EARNINGS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading earnings..." />}>
          <VendorLayout>
            <VendorEarnings />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_EXPENSES,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading expenses..." />}>
          <VendorLayout>
            <VendorExpenses />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_WITHDRAWALS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading withdrawals..." />}>
          <VendorLayout>
            <VendorWithdrawals />
          </VendorLayout>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_OTP,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading verification..." />}>
          <VendorOtp />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_SET_PASSWORD,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading..." />}>
          <VendorSetPassword />
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.VENDOR_DASHBOARD,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading dashboard..." />}>
          <ProtectedRoute roles={['vendor']}>
            <VendorLayout>
              <VendorDashboard />
            </VendorLayout>
          </ProtectedRoute>
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
    path: ROUTES.ADMIN_PRODUCTS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading products..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminProducts />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ADMIN_PRODUCT_DETAIL,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading product..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminProductDetail />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ADMIN_PRODUCT_EDIT,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading product..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminProductEdit />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ADMIN_VENDOR_APPLICATIONS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading applications..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminVendorApplications />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: '/admin/vendor-applications/:id',
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading application..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminVendorApplicationDetail />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ADMIN_VENDORS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading vendors..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminVendors />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: '/admin/vendors/:id',
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading vendor details..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminVendorDetail />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: '/admin/settings',
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading settings..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminSettings />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: '/admin/orders',
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading orders..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminOrders />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: '/admin/orders/:orderId',
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading order details..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminOrderDetail />
          </ProtectedRoute>
        </Suspense>
      </ErrorBoundary>
    ),
  },
  {
    path: ROUTES.ADMIN_PAYOUTS,
    element: (
      <ErrorBoundary>
        <Suspense fallback={<Loading fullScreen message="Loading payouts..." />}>
          <ProtectedRoute roles={['admin']}>
            <AdminPayouts />
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
