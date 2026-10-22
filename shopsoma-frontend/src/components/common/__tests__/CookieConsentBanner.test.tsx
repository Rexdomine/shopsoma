import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import CookieConsentBanner from '../CookieConsentBanner';
import Footer from '../../layout/Footer';
import PublicDocument from '../../../pages/public/PublicDocument';
import {
  canUseCookieCategory,
  COOKIE_CONSENT_CONFIG_VERSION,
  COOKIE_CONSENT_COOKIE_NAME,
  COOKIE_CONSENT_STORAGE_KEY,
  isConsentRecordValid,
  readStoredCookieConsent,
  runWhenCookieCategoryAllowed,
  useCookieConsentStore,
} from '../../../store/cookieConsentStore';
import { usePreferenceStore } from '../../../store/preferenceStore';

vi.mock('../../../services/newsletterService', () => ({
  subscribeToNewsletter: vi.fn(),
}));
vi.mock('../../layout/Layout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

function LocationDisplay() {
  return <output data-testid="location">{useLocation().pathname}</output>;
}

function renderBanner(initialEntry = '/') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <CookieConsentBanner />
      <LocationDisplay />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  document.cookie = `${COOKIE_CONSENT_COOKIE_NAME}=; Path=/; Max-Age=0`;
  document.cookie = '_ga=; Path=/; Max-Age=0';
  document.cookie = '_fbp=; Path=/; Max-Age=0';
  useCookieConsentStore.getState().resetConsent();
});

describe('CookieConsentBanner & cookieConsentStore', () => {
  it('shows the cookie banner to a new visitor and links to the approved Cookie Policy', () => {
    renderBanner('/');

    const banner = screen.getByRole('region', { name: 'Cookie consent' });
    expect(banner).toBeInTheDocument();
    expect(screen.getByText(/We use essential cookies to keep ShopSoma working properly/i)).toBeInTheDocument();

    const policyLink = within(banner).getByRole('link', { name: 'Cookie Policy' });
    expect(policyLink).toHaveAttribute('href', '/cookies');

    fireEvent.click(policyLink);
    expect(screen.getByTestId('location')).toHaveTextContent('/cookies');
  });

  it('keeps optional cookies and callbacks disabled before the visitor provides consent', () => {
    const analyticsSpy = vi.fn();
    const marketingSpy = vi.fn();

    const unsubscribeAnalytics = runWhenCookieCategoryAllowed('analytics', analyticsSpy);
    const unsubscribeMarketing = runWhenCookieCategoryAllowed('marketing', marketingSpy);

    expect(canUseCookieCategory('essential')).toBe(true);
    expect(canUseCookieCategory('preferences')).toBe(false);
    expect(canUseCookieCategory('analytics')).toBe(false);
    expect(canUseCookieCategory('marketing')).toBe(false);
    expect(analyticsSpy).not.toHaveBeenCalled();
    expect(marketingSpy).not.toHaveBeenCalled();

    // Optional browsing preferences are not written to localStorage before consent
    usePreferenceStore.getState().setInterest('womenswear');
    usePreferenceStore.getState().setDesigners(['SOMA Studio']);
    expect(window.localStorage.getItem('shopsoma_pref_interest')).toBeNull();
    expect(window.localStorage.getItem('shopsoma_pref_designers')).toBeNull();

    unsubscribeAnalytics();
    unsubscribeMarketing();
  });

  it('persists Accept All, hides the banner for returning visits, and enables optional cookies', () => {
    const analyticsSpy = vi.fn();
    const unsubscribe = runWhenCookieCategoryAllowed('analytics', analyticsSpy);

    const { unmount } = renderBanner('/');
    fireEvent.click(screen.getByRole('button', { name: 'Accept All' }));

    expect(screen.queryByRole('region', { name: 'Cookie consent' })).not.toBeInTheDocument();
    expect(canUseCookieCategory('preferences')).toBe(true);
    expect(canUseCookieCategory('analytics')).toBe(true);
    expect(canUseCookieCategory('marketing')).toBe(true);
    expect(analyticsSpy).toHaveBeenCalledTimes(1);

    const stored = readStoredCookieConsent();
    expect(stored).not.toBeNull();
    expect(stored?.status).toBe('accepted_all');
    expect(stored?.version).toBe(COOKIE_CONSENT_CONFIG_VERSION);
    expect(Object.keys(stored!).sort()).toEqual(['categories', 'expiresAt', 'status', 'updatedAt', 'version']);

    // Preference store can now persist optional preferences to localStorage
    usePreferenceStore.getState().setInterest('womenswear');
    expect(window.localStorage.getItem('shopsoma_pref_interest')).toBe('womenswear');

    // Returning visitor does not see the banner again while valid preference exists
    unmount();
    renderBanner('/');
    expect(screen.queryByRole('region', { name: 'Cookie consent' })).not.toBeInTheDocument();

    unsubscribe();
  });

  it('persists Decline Optional, clears non-essential storage/cookies, and hides the banner', () => {
    window.localStorage.setItem('shopsoma_pref_interest', 'menswear');
    window.localStorage.setItem('shopsoma_pref_designers', JSON.stringify(['Designer A']));
    window.localStorage.setItem('shopsoma_access_token', 'essential-jwt-token');
    document.cookie = '_ga=GA1.1.12345; Path=/';
    document.cookie = '_fbp=fb.1.12345; Path=/';

    renderBanner('/');
    fireEvent.click(screen.getByRole('button', { name: 'Decline Optional' }));

    expect(screen.queryByRole('region', { name: 'Cookie consent' })).not.toBeInTheDocument();
    expect(canUseCookieCategory('essential')).toBe(true);
    expect(canUseCookieCategory('preferences')).toBe(false);
    expect(canUseCookieCategory('analytics')).toBe(false);
    expect(canUseCookieCategory('marketing')).toBe(false);

    // Non-essential preference storage and analytics/marketing cookies are cleared
    expect(window.localStorage.getItem('shopsoma_pref_interest')).toBeNull();
    expect(window.localStorage.getItem('shopsoma_pref_designers')).toBeNull();
    // Essential storage remains untouched
    expect(window.localStorage.getItem('shopsoma_access_token')).toBe('essential-jwt-token');

    const stored = readStoredCookieConsent();
    expect(stored?.status).toBe('declined_optional');
    expect(stored?.categories).toEqual({
      essential: true,
      preferences: false,
      analytics: false,
      marketing: false,
    });
  });

  it('allows granular category selection via Manage Preferences', () => {
    const analyticsSpy = vi.fn();
    const marketingSpy = vi.fn();
    const unsubAnalytics = runWhenCookieCategoryAllowed('analytics', analyticsSpy);
    const unsubMarketing = runWhenCookieCategoryAllowed('marketing', marketingSpy);

    renderBanner('/');
    fireEvent.click(screen.getByRole('button', { name: 'Manage Preferences' }));

    const dialog = screen.getByRole('dialog', { name: /Manage Cookie Preferences/i });
    expect(dialog).toBeInTheDocument();

    const essentialCheckbox = screen.getByRole('checkbox', { name: 'Essential Cookies' });
    expect(essentialCheckbox).toBeChecked();
    expect(essentialCheckbox).toBeDisabled();

    const preferencesCheckbox = screen.getByRole('checkbox', { name: 'Preference Cookies' });
    const analyticsCheckbox = screen.getByRole('checkbox', { name: 'Analytics Cookies' });
    const marketingCheckbox = screen.getByRole('checkbox', { name: 'Marketing Cookies' });

    expect(preferencesCheckbox).not.toBeChecked();
    expect(analyticsCheckbox).not.toBeChecked();
    expect(marketingCheckbox).not.toBeChecked();

    fireEvent.click(preferencesCheckbox);
    fireEvent.click(analyticsCheckbox);
    fireEvent.click(screen.getByRole('button', { name: 'Save Preferences' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(canUseCookieCategory('preferences')).toBe(true);
    expect(canUseCookieCategory('analytics')).toBe(true);
    expect(canUseCookieCategory('marketing')).toBe(false);
    expect(analyticsSpy).toHaveBeenCalledTimes(1);
    expect(marketingSpy).not.toHaveBeenCalled();

    const stored = readStoredCookieConsent();
    expect(stored?.status).toBe('custom');
    expect(stored?.categories).toEqual({
      essential: true,
      preferences: true,
      analytics: true,
      marketing: false,
    });

    unsubAnalytics();
    unsubMarketing();
  });

  it('re-shows the banner when the saved preference expires or the cookie configuration version changes', () => {
    const now = Date.now();
    const expiredRecord = {
      version: COOKIE_CONSENT_CONFIG_VERSION,
      status: 'accepted_all',
      categories: { essential: true, preferences: true, analytics: true, marketing: true },
      updatedAt: new Date(now - 200 * 86_400_000).toISOString(),
      expiresAt: new Date(now - 1_000).toISOString(),
    };
    window.localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(expiredRecord));

    const { unmount } = renderBanner('/');
    expect(screen.getByRole('region', { name: 'Cookie consent' })).toBeInTheDocument();
    expect(window.localStorage.getItem(COOKIE_CONSENT_STORAGE_KEY)).toBeNull();
    unmount();

    const outdatedVersionRecord = {
      version: '0.9-legacy',
      status: 'accepted_all',
      categories: { essential: true, preferences: true, analytics: true, marketing: true },
      updatedAt: new Date(now).toISOString(),
      expiresAt: new Date(now + 30 * 86_400_000).toISOString(),
    };
    window.localStorage.setItem(COOKIE_CONSENT_STORAGE_KEY, JSON.stringify(outdatedVersionRecord));

    renderBanner('/');
    expect(screen.getByRole('region', { name: 'Cookie consent' })).toBeInTheDocument();
  });

  it('rejects consent records that contain unexpected personal data fields', () => {
    const now = Date.now();
    const recordWithPersonalData = {
      version: COOKIE_CONSENT_CONFIG_VERSION,
      status: 'accepted_all',
      categories: { essential: true, preferences: true, analytics: true, marketing: true },
      updatedAt: new Date(now).toISOString(),
      expiresAt: new Date(now + 10_000).toISOString(),
      email: 'visitor@example.com',
    };

    expect(isConsentRecordValid(recordWithPersonalData, now)).toBe(false);
  });

  it('supports reopening, changing, and resetting saved preferences from Footer and the Cookie Policy page', () => {
    render(
      <MemoryRouter initialEntries={['/cookies']}>
        <PublicDocument documentKey="cookies" />
        <Footer />
        <CookieConsentBanner />
      </MemoryRouter>,
    );

    // Accept all initially
    fireEvent.click(screen.getByRole('button', { name: 'Accept All' }));
    expect(screen.queryByRole('region', { name: 'Cookie consent' })).not.toBeInTheDocument();
    expect(canUseCookieCategory('marketing')).toBe(true);

    // Reopen from Footer "Cookie Settings" button and change to Decline Optional
    const footerCookieButtons = screen.getAllByRole('button', { name: 'Cookie Settings' });
    fireEvent.click(footerCookieButtons[0]);
    expect(screen.getByRole('dialog', { name: /Manage Cookie Preferences/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Decline Optional' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(canUseCookieCategory('marketing')).toBe(false);

    // Reset saved preference from the Cookie Policy page
    fireEvent.click(screen.getByRole('button', { name: 'Reset Saved Preference' }));
    expect(screen.getByRole('region', { name: 'Cookie consent' })).toBeInTheDocument();
    expect(readStoredCookieConsent()).toBeNull();
  });
});
