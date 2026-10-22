import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { ROUTES } from '../../config/constants';
import {
  useCookieConsentStore,
  type OptionalCookieCategory,
} from '../../store/cookieConsentStore';

const OPTIONAL_CATEGORY_DETAILS: Array<{
  key: OptionalCookieCategory;
  title: string;
  description: string;
}> = [
  {
    key: 'preferences',
    title: 'Preference Cookies',
    description:
      'Remember your choices and settings on this device to make your browsing experience more convenient.',
  },
  {
    key: 'analytics',
    title: 'Analytics Cookies',
    description:
      'Help us understand how visitors use ShopSoma, including which pages are visited and how customers interact with the Website, so we can improve performance and user experience.',
  },
  {
    key: 'marketing',
    title: 'Marketing Cookies',
    description:
      'Where enabled and permitted, help us assess the effectiveness of our marketing and provide more relevant advertising.',
  },
];

export default function CookieConsentBanner() {
  const {
    hasValidConsent,
    isBannerVisible,
    isPreferencesOpen,
    draftCategories,
    acceptAll,
    declineOptional,
    savePreferences,
    openPreferences,
    closePreferences,
    setDraftCategory,
    resetConsent,
    syncFromStorage,
  } = useCookieConsentStore();

  useEffect(() => {
    syncFromStorage();
    const handleStorage = () => syncFromStorage();
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, [syncFromStorage]);

  if (!isBannerVisible && !isPreferencesOpen) {
    return null;
  }

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-50 p-3 sm:p-6 pointer-events-none"
      data-testid="cookie-consent-container"
    >
      <div className="pointer-events-auto max-w-6xl mx-auto bg-white border border-[#1E5053] shadow-2xl p-4 sm:p-6 text-[#1E5053] max-h-[85vh] overflow-y-auto">
        {!isPreferencesOpen ? (
          <section
            role="region"
            aria-label="Cookie consent"
            className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 sm:gap-6"
          >
            <div className="space-y-1.5 max-w-3xl">
              <p className="text-[11px] font-ui uppercase tracking-[0.25em] font-semibold text-[#1E5053]">
                Cookie Notice
              </p>
              <p className="text-xs sm:text-sm font-serif leading-relaxed text-[#222424]">
                We use essential cookies to keep ShopSoma working properly, and optional preference,
                analytics, and marketing cookies to remember your settings, understand how visitors
                use our website, and improve your experience. Read our{' '}
                <Link
                  to={ROUTES.COOKIES}
                  className="underline underline-offset-2 font-medium text-[#1E5053] hover:opacity-80"
                >
                  Cookie Policy
                </Link>{' '}
                to learn more.
              </p>
            </div>

            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shrink-0">
              <button
                type="button"
                onClick={acceptAll}
                className="bg-[#1E5053] text-white px-5 py-2.5 text-xs font-ui uppercase tracking-[0.2em] hover:bg-[#105E53] transition text-center"
              >
                Accept All
              </button>
              <button
                type="button"
                onClick={declineOptional}
                className="border border-[#1E5053] bg-white text-[#1E5053] px-5 py-2.5 text-xs font-ui uppercase tracking-[0.2em] hover:bg-[#F0F5F4] transition text-center"
              >
                Decline Optional
              </button>
              <button
                type="button"
                onClick={openPreferences}
                className="border border-transparent underline underline-offset-4 text-[#1E5053] px-3 py-2.5 text-xs font-ui uppercase tracking-[0.2em] hover:opacity-80 transition text-center"
              >
                Manage Preferences
              </button>
            </div>
          </section>
        ) : (
          <div
            role="dialog"
            aria-modal="false"
            aria-labelledby="cookie-preferences-heading"
            className="space-y-5"
          >
            <div className="flex items-start justify-between gap-4 border-b border-[#1E5053]/20 pb-3">
              <div className="space-y-1">
                <p
                  id="cookie-preferences-heading"
                  className="text-xs sm:text-sm font-ui uppercase tracking-[0.25em] font-semibold text-[#1E5053]"
                >
                  Manage Cookie Preferences
                </p>
                <p className="text-xs sm:text-sm font-serif text-[#222424]">
                  Choose which optional cookies to allow on ShopSoma. Essential cookies are always
                  enabled to support core site functions. For full details, visit our{' '}
                  <Link
                    to={ROUTES.COOKIES}
                    className="underline underline-offset-2 font-medium text-[#1E5053]"
                  >
                    Cookie Policy
                  </Link>
                  .
                </p>
              </div>
              <button
                type="button"
                onClick={closePreferences}
                aria-label="Close cookie preferences"
                className="text-xs font-ui uppercase tracking-[0.2em] px-2 py-1 border border-[#1E5053]/30 text-[#1E5053] hover:bg-[#F0F5F4] transition shrink-0"
              >
                Close
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
              <div className="border border-[#1E5053]/20 p-3.5 bg-[#F0F5F4]/50 space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <label
                    htmlFor="cookie-category-essential"
                    className="text-xs font-ui uppercase tracking-[0.18em] font-semibold text-[#1E5053]"
                  >
                    Essential Cookies
                  </label>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-ui uppercase tracking-[0.15em] text-[#1E5053] font-medium">
                      Always Active
                    </span>
                    <input
                      id="cookie-category-essential"
                      type="checkbox"
                      checked
                      disabled
                      aria-label="Essential Cookies"
                      className="h-4 w-4 accent-[#1E5053]"
                    />
                  </div>
                </div>
                <p className="text-xs font-serif text-[#222424] leading-relaxed">
                  Enable core Website functions such as navigation, account access, guest checkout,
                  shopping bag functionality, checkout and security.
                </p>
              </div>

              {OPTIONAL_CATEGORY_DETAILS.map((item) => (
                <div
                  key={item.key}
                  className="border border-[#1E5053]/20 p-3.5 bg-white space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <label
                      htmlFor={`cookie-category-${item.key}`}
                      className="text-xs font-ui uppercase tracking-[0.18em] font-semibold text-[#1E5053] cursor-pointer"
                    >
                      {item.title}
                    </label>
                    <input
                      id={`cookie-category-${item.key}`}
                      type="checkbox"
                      checked={draftCategories[item.key]}
                      onChange={(e) => setDraftCategory(item.key, e.target.checked)}
                      aria-label={item.title}
                      className="h-4 w-4 accent-[#1E5053] cursor-pointer"
                    />
                  </div>
                  <p className="text-xs font-serif text-[#222424] leading-relaxed">
                    {item.description}
                  </p>
                </div>
              ))}
            </div>

            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-2 border-t border-[#1E5053]/20">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => savePreferences(draftCategories)}
                  className="bg-[#1E5053] text-white px-5 py-2.5 text-xs font-ui uppercase tracking-[0.2em] hover:bg-[#105E53] transition text-center"
                >
                  Save Preferences
                </button>
                <button
                  type="button"
                  onClick={acceptAll}
                  className="border border-[#1E5053] bg-white text-[#1E5053] px-4 py-2.5 text-xs font-ui uppercase tracking-[0.2em] hover:bg-[#F0F5F4] transition text-center"
                >
                  Accept All
                </button>
                <button
                  type="button"
                  onClick={declineOptional}
                  className="border border-[#1E5053] bg-white text-[#1E5053] px-4 py-2.5 text-xs font-ui uppercase tracking-[0.2em] hover:bg-[#F0F5F4] transition text-center"
                >
                  Decline Optional
                </button>
              </div>

              {hasValidConsent && (
                <button
                  type="button"
                  onClick={resetConsent}
                  className="underline underline-offset-4 text-xs font-ui uppercase tracking-[0.18em] text-[#1E5053] hover:opacity-80 transition text-center sm:text-right"
                >
                  Reset Saved Preference
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
