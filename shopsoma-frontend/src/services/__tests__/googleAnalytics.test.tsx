import { StrictMode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import CookieConsentBanner from '../../components/common/CookieConsentBanner';
import GoogleAnalyticsTracker from '../../components/common/GoogleAnalyticsTracker';
import {
  COOKIE_CONSENT_COOKIE_NAME,
  useCookieConsentStore,
} from '../../store/cookieConsentStore';
import {
  extractCampaignAttribution,
  GA_SCRIPT_ID,
  getConfiguredGaMeasurementId,
  isValidGaMeasurementId,
  resetGoogleAnalyticsForTests,
  sanitizeAnalyticsUrl,
  sanitizeEventParameters,
  trackAnalyticsEvent,
  trackPageView,
} from '../googleAnalytics';

const TEST_MEASUREMENT_ID = 'G-SHOPSOMA26';

function NavigationTestHarness({ measurementId = TEST_MEASUREMENT_ID }: { measurementId?: string }) {
  const navigate = useNavigate();
  return (
    <StrictMode>
      <GoogleAnalyticsTracker measurementId={measurementId} />
      <CookieConsentBanner />
      <div>
        <button type="button" onClick={() => navigate('/women')}>
          Go Women
        </button>
        <button type="button" onClick={() => navigate('/products/prod-101')}>
          Go Product
        </button>
        <button
          type="button"
          onClick={() =>
            navigate(
              '/women?utm_source=newsletter&utm_medium=email&utm_campaign=vip_preview&utm_content=hero_cta&utm_term=adire_silk',
            )
          }
        >
          Go Campaign 2
        </button>
        <button
          type="button"
          onClick={() =>
            navigate('/claim-account?token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sig&email=customer@example.com')
          }
        >
          Go Claim Account
        </button>
      </div>
      <Routes>
        <Route path="*" element={<div data-testid="route-view">Page Content</div>} />
      </Routes>
    </StrictMode>
  );
}

describe('Google Analytics 4 service & SOMA-19 consent integration', () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    document.cookie = `${COOKIE_CONSENT_COOKIE_NAME}=; Path=/; Max-Age=0`;
    document.cookie = '_ga=; Path=/; Max-Age=0';
    document.cookie = '_ga_SHOPSOMA26=; Path=/; Max-Age=0';
    useCookieConsentStore.getState().resetConsent();
    resetGoogleAnalyticsForTests();
    document.title = 'SHOP SOMA - African Luxury Fashion';
  });

  afterEach(() => {
    resetGoogleAnalyticsForTests();
  });

  describe('Measurement ID validation (no assumed property)', () => {
    it('accepts valid GA4 Measurement IDs and rejects missing or placeholder IDs', () => {
      expect(isValidGaMeasurementId('G-SHOPSOMA26')).toBe(true);
      expect(isValidGaMeasurementId(' g-1a2b3c4d5e ')).toBe(true);

      expect(isValidGaMeasurementId('')).toBe(false);
      expect(isValidGaMeasurementId(undefined)).toBe(false);
      expect(isValidGaMeasurementId('G-XXXXXXXXXX')).toBe(false);
      expect(isValidGaMeasurementId('G-PLACEHOLDER')).toBe(false);
      expect(isValidGaMeasurementId('your_ga_measurement_id')).toBe(false);
      expect(isValidGaMeasurementId('UA-123456-1')).toBe(false);

      expect(getConfiguredGaMeasurementId('')).toBe('');
      expect(getConfiguredGaMeasurementId('G-XXXXXXXXXX')).toBe('');
      expect(getConfiguredGaMeasurementId('G-SHOPSOMA26')).toBe('G-SHOPSOMA26');
    });

    it('does not load gtag.js or send events when no valid Measurement ID is configured', () => {
      useCookieConsentStore.getState().acceptAll();
      const gtagSpy = vi.fn();
      window.gtag = gtagSpy;

      const tracked = trackPageView({
        pathname: '/',
        search: '',
        measurementId: '',
      });

      expect(tracked).toBe(false);
      expect(document.getElementById(GA_SCRIPT_ID)).toBeNull();
      expect(gtagSpy).not.toHaveBeenCalled();
    });
  });

  describe('Cookie consent coordination (SOMA-19)', () => {
    it('does not load GA4 or send page_view before analytics consent is granted, then activates upon Accept All', () => {
      const gtagSpy = vi.fn();
      window.gtag = gtagSpy;

      render(
        <MemoryRouter
          initialEntries={[
            '/?utm_source=instagram&utm_medium=paid_social&utm_campaign=harmattan_edit&utm_content=reel_1&utm_term=boubou',
          ]}
        >
          <NavigationTestHarness />
        </MemoryRouter>,
      );

      // Before consent: no script tag, ga-disable flag is set, and no page_view is fired
      expect(document.getElementById(GA_SCRIPT_ID)).toBeNull();
      expect(window[`ga-disable-${TEST_MEASUREMENT_ID}`]).toBe(true);
      expect(gtagSpy).not.toHaveBeenCalledWith('event', 'page_view', expect.anything());

      // Visitor clicks "Accept All" on the SOMA-19 cookie banner
      fireEvent.click(screen.getByRole('button', { name: 'Accept All' }));

      const script = document.getElementById(GA_SCRIPT_ID) as HTMLScriptElement | null;
      expect(script).not.toBeNull();
      expect(script?.src).toBe(
        `https://www.googletagmanager.com/gtag/js?id=${TEST_MEASUREMENT_ID}`,
      );
      expect(window[`ga-disable-${TEST_MEASUREMENT_ID}`]).toBe(false);

      // Config is initialized with send_page_view: false to prevent duplicate automatic pageviews
      expect(gtagSpy).toHaveBeenCalledWith(
        'config',
        TEST_MEASUREMENT_ID,
        expect.objectContaining({
          send_page_view: false,
        }),
      );

      // Exactly one page_view is fired with the landing UTM campaign attribution
      const pageViewCalls = gtagSpy.mock.calls.filter(
        (call) => call[0] === 'event' && call[1] === 'page_view',
      );
      expect(pageViewCalls).toHaveLength(1);
      expect(pageViewCalls[0][2]).toMatchObject({
        send_to: TEST_MEASUREMENT_ID,
        page_path:
          '/?utm_source=instagram&utm_medium=paid_social&utm_campaign=harmattan_edit&utm_content=reel_1&utm_term=boubou',
        campaign_source: 'instagram',
        campaign_medium: 'paid_social',
        campaign_name: 'harmattan_edit',
        campaign_content: 'reel_1',
        campaign_term: 'boubou',
      });
    });

    it('preserves landing campaign attribution when a visitor navigates before accepting analytics cookies', () => {
      const gtagSpy = vi.fn();
      window.gtag = gtagSpy;

      render(
        <MemoryRouter
          initialEntries={[
            '/?utm_source=instagram&utm_medium=social&utm_campaign=eid_drop&utm_content=bio_link',
          ]}
        >
          <NavigationTestHarness />
        </MemoryRouter>,
      );

      // Navigate to /women BEFORE accepting cookies
      fireEvent.click(screen.getByRole('button', { name: 'Go Women' }));
      expect(gtagSpy).not.toHaveBeenCalledWith('event', 'page_view', expect.anything());

      // Now accept analytics cookies on /women
      fireEvent.click(screen.getByRole('button', { name: 'Accept All' }));

      const pageViewCalls = gtagSpy.mock.calls.filter(
        (call) => call[0] === 'event' && call[1] === 'page_view',
      );
      expect(pageViewCalls).toHaveLength(1);
      expect(pageViewCalls[0][2]).toMatchObject({
        page_path:
          '/women?utm_source=instagram&utm_medium=social&utm_campaign=eid_drop&utm_content=bio_link',
        campaign_source: 'instagram',
        campaign_medium: 'social',
        campaign_name: 'eid_drop',
        campaign_content: 'bio_link',
      });
    });

    it('stops tracking immediately when analytics consent is declined or reset', () => {
      const gtagSpy = vi.fn();
      window.gtag = gtagSpy;

      render(
        <MemoryRouter initialEntries={['/']}>
          <NavigationTestHarness />
        </MemoryRouter>,
      );

      fireEvent.click(screen.getByRole('button', { name: 'Accept All' }));
      expect(
        gtagSpy.mock.calls.filter((call) => call[0] === 'event' && call[1] === 'page_view'),
      ).toHaveLength(1);

      // Visitor revokes consent via store
      useCookieConsentStore.getState().declineOptional();

      expect(window[`ga-disable-${TEST_MEASUREMENT_ID}`]).toBe(true);
      expect(gtagSpy).toHaveBeenCalledWith(
        'consent',
        'update',
        expect.objectContaining({
          analytics_storage: 'denied',
          ad_storage: 'denied',
        }),
      );

      // Subsequent navigation does not emit any new page_view events
      fireEvent.click(screen.getByRole('button', { name: 'Go Women' }));
      expect(
        gtagSpy.mock.calls.filter((call) => call[0] === 'event' && call[1] === 'page_view'),
      ).toHaveLength(1);
    });
  });

  describe('SPA navigation & duplicate page_view prevention', () => {
    it('tracks each route navigation once and prevents duplicate page_view events on re-render or StrictMode', () => {
      useCookieConsentStore.getState().acceptAll();
      const gtagSpy = vi.fn();
      window.gtag = gtagSpy;

      const { rerender } = render(
        <MemoryRouter initialEntries={['/']}>
          <NavigationTestHarness />
        </MemoryRouter>,
      );

      const getPageViews = () =>
        gtagSpy.mock.calls.filter((call) => call[0] === 'event' && call[1] === 'page_view');

      // Initial load: exactly 1 page_view even inside React.StrictMode
      expect(getPageViews()).toHaveLength(1);
      expect(getPageViews()[0][2]).toMatchObject({
        page_path: '/',
      });

      // Re-rendering on the same route or calling trackPageView again with the same route does not duplicate
      rerender(
        <MemoryRouter initialEntries={['/']}>
          <NavigationTestHarness />
        </MemoryRouter>,
      );
      expect(
        trackPageView({ pathname: '/', search: '', measurementId: TEST_MEASUREMENT_ID }),
      ).toBe(false);
      expect(getPageViews()).toHaveLength(1);

      // Navigate to /women -> 2nd page_view with referrer set to previous page
      fireEvent.click(screen.getByRole('button', { name: 'Go Women' }));
      expect(getPageViews()).toHaveLength(2);
      expect(getPageViews()[1][2]).toMatchObject({
        page_path: '/women',
        page_referrer: `${window.location.origin}/`,
      });

      // Navigate to /products/prod-101 -> 3rd page_view with referrer set to /women
      fireEvent.click(screen.getByRole('button', { name: 'Go Product' }));
      expect(getPageViews()).toHaveLength(3);
      expect(getPageViews()[2][2]).toMatchObject({
        page_path: '/products/prod-101',
        page_referrer: `${window.location.origin}/women`,
      });
    });
  });

  describe('Campaign attribution for multiple tagged links & DebugView support', () => {
    it('distinguishes visits from at least two distinctly tagged campaign links by source, medium, campaign, content, and term', () => {
      useCookieConsentStore.getState().acceptAll();
      const gtagSpy = vi.fn();
      window.gtag = gtagSpy;

      // Campaign Link 1: Instagram paid social campaign with debug_mode enabled
      trackPageView({
        pathname: '/',
        search:
          '?utm_source=instagram&utm_medium=paid_social&utm_campaign=harmattan_2026&utm_content=carousel_1&utm_term=luxury_kaftan&ga_debug=1',
        referrer: 'https://l.instagram.com/',
        origin: 'https://shopsoma.com',
        measurementId: TEST_MEASUREMENT_ID,
      });

      // Campaign Link 2: Email newsletter campaign
      trackPageView({
        pathname: '/women',
        search:
          '?utm_source=newsletter&utm_medium=email&utm_campaign=vip_launch&utm_content=hero_button&utm_term=silk_adire',
        origin: 'https://shopsoma.com',
        measurementId: TEST_MEASUREMENT_ID,
      });

      const pageViews = gtagSpy.mock.calls.filter(
        (call) => call[0] === 'event' && call[1] === 'page_view',
      );
      expect(pageViews).toHaveLength(2);

      const firstVisitPayload = pageViews[0][2];
      const secondVisitPayload = pageViews[1][2];

      expect(firstVisitPayload).toMatchObject({
        send_to: TEST_MEASUREMENT_ID,
        page_location:
          'https://shopsoma.com/?utm_source=instagram&utm_medium=paid_social&utm_campaign=harmattan_2026&utm_content=carousel_1&utm_term=luxury_kaftan',
        page_path:
          '/?utm_source=instagram&utm_medium=paid_social&utm_campaign=harmattan_2026&utm_content=carousel_1&utm_term=luxury_kaftan',
        page_referrer: 'https://l.instagram.com/',
        campaign_source: 'instagram',
        campaign_medium: 'paid_social',
        campaign_name: 'harmattan_2026',
        campaign_content: 'carousel_1',
        campaign_term: 'luxury_kaftan',
        debug_mode: true,
      });

      expect(secondVisitPayload).toMatchObject({
        send_to: TEST_MEASUREMENT_ID,
        page_location:
          'https://shopsoma.com/women?utm_source=newsletter&utm_medium=email&utm_campaign=vip_launch&utm_content=hero_button&utm_term=silk_adire',
        page_path:
          '/women?utm_source=newsletter&utm_medium=email&utm_campaign=vip_launch&utm_content=hero_button&utm_term=silk_adire',
        campaign_source: 'newsletter',
        campaign_medium: 'email',
        campaign_name: 'vip_launch',
        campaign_content: 'hero_button',
        campaign_term: 'silk_adire',
        debug_mode: true,
      });

      expect(firstVisitPayload.campaign_source).not.toBe(secondVisitPayload.campaign_source);
      expect(firstVisitPayload.campaign_medium).not.toBe(secondVisitPayload.campaign_medium);
      expect(firstVisitPayload.campaign_name).not.toBe(secondVisitPayload.campaign_name);
    });
  });

  describe('Personal information (PII) protection in URLs and event parameters', () => {
    it('strips emails, tokens, OTPs, phones, and sensitive query parameters while keeping UTM and safe storefront filters', () => {
      const claimUrl = sanitizeAnalyticsUrl(
        'https://shopsoma.com/claim-account?token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig&email=customer%40example.com&utm_source=transactional&utm_medium=email&utm_campaign=order_claim#private-hash',
      );
      expect(claimUrl.pagePath).toBe(
        '/claim-account?utm_source=transactional&utm_medium=email&utm_campaign=order_claim',
      );
      expect(claimUrl.pageLocation).not.toContain('customer');
      expect(claimUrl.pageLocation).not.toContain('example.com');
      expect(claimUrl.pageLocation).not.toContain('eyJ');
      expect(claimUrl.pageLocation).not.toContain('#private-hash');

      const vendorOtpUrl = sanitizeAnalyticsUrl(
        'https://shopsoma.com/vendor/otp?email=designer@shopsoma.com&otp=123456',
      );
      expect(vendorOtpUrl.pagePath).toBe('/vendor/otp');

      const resetPasswordUrl = sanitizeAnalyticsUrl(
        'https://shopsoma.com/reset-password?token=reset-secret-999&role=vendor',
      );
      expect(resetPasswordUrl.pagePath).toBe('/reset-password?role=vendor');

      // Even if PII is accidentally placed inside a UTM parameter or path segment, it is stripped
      const piiInUtm = sanitizeAnalyticsUrl(
        'https://shopsoma.com/users/visitor@example.com?utm_source=newsletter&utm_term=visitor@example.com&phone=%2B2348012345678&category=dresses',
      );
      expect(piiInUtm.pagePath).toBe('/users/[redacted]?utm_source=newsletter&category=dresses');
      expect(extractCampaignAttribution('?utm_source=ig&utm_term=user@example.com')).toEqual({
        utm_source: 'ig',
      });
    });

    it('sanitizes custom event parameters and page titles before sending to GA4', () => {
      useCookieConsentStore.getState().acceptAll();
      const gtagSpy = vi.fn();
      window.gtag = gtagSpy;

      const sanitized = sanitizeEventParameters({
        category: 'womenswear',
        email: 'secret@example.com',
        customer_phone: '+2348012345678',
        reset_token: 'abc-123',
        note: 'Contact customer@example.com for fitting',
        item_count: 2,
      });

      expect(sanitized).toEqual({
        category: 'womenswear',
        note: 'Contact [redacted-email] for fitting',
        item_count: 2,
      });

      trackAnalyticsEvent(
        'filter_applied',
        {
          category: 'dresses',
          email: 'hidden@example.com',
        },
        { measurementId: TEST_MEASUREMENT_ID },
      );

      expect(gtagSpy).toHaveBeenCalledWith('event', 'filter_applied', {
        send_to: TEST_MEASUREMENT_ID,
        category: 'dresses',
      });
    });
  });
});
