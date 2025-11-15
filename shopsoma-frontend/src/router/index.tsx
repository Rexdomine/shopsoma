/**
 * React Router Configuration
 */
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Suspense, lazy } from 'react';
import { ROUTES } from '../config/constants';
import ErrorBoundary from '../components/error/ErrorBoundary';
import Loading from '../components/common/Loading';
import RootLayout from '../components/layout/RootLayout';

// Lazy load pages for code splitting
const Home = lazy(() => import('../pages/Home'));
const ProductDetail = lazy(() => import('../pages/products/ProductDetail'));
const ProductList = lazy(() => import('../pages/products/ProductList'));
const Cart = lazy(() => import('../pages/cart/Cart'));
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
