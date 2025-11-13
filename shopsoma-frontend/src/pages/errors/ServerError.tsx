/**
 * 500 Server Error Page
 */
import { Link } from 'react-router-dom';
import { ROUTES } from '../../config/constants';

export default function ServerError() {
  const handleRefresh = () => {
    window.location.reload();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full text-center">
        <div className="mb-8">
          <h1 className="text-9xl font-bold text-gray-200">500</h1>
          <div className="relative -mt-16">
            <svg
              className="w-24 h-24 mx-auto text-red-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
        </div>

        <h2 className="text-3xl font-bold text-gray-900 mb-4">
          Server Error
        </h2>

        <p className="text-lg text-gray-600 mb-8">
          Something went wrong on our end. Our team has been notified and is working on it.
        </p>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-8">
          <p className="text-sm text-blue-800">
            If the problem persists, please contact support at{' '}
            <a
              href="mailto:support@shopsoma.com"
              className="font-medium underline"
            >
              support@shopsoma.com
            </a>
          </p>
        </div>

        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <button
            onClick={handleRefresh}
            className="px-6 py-3 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors font-medium"
          >
            Refresh Page
          </button>
          <Link
            to={ROUTES.HOME}
            className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
          >
            Go Home
          </Link>
        </div>

        <div className="mt-12 pt-8 border-t border-gray-200">
          <p className="text-xs text-gray-500">
            Error Reference: {Date.now().toString(36).toUpperCase()}
          </p>
        </div>
      </div>
    </div>
  );
}
