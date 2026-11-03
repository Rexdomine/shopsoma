import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import {
  bindAnalyticsConsentListener,
  captureNavigationContext,
  deactivateGoogleAnalytics,
  initializeGoogleAnalytics,
  trackPageView,
} from '../../services/googleAnalytics';
import { useCookieConsentStore } from '../../store/cookieConsentStore';

export interface GoogleAnalyticsTrackerProps {
  measurementId?: string;
  debugMode?: boolean;
}

export default function GoogleAnalyticsTracker({
  measurementId,
  debugMode,
}: GoogleAnalyticsTrackerProps = {}) {
  const { pathname, search } = useLocation();
  const analyticsAllowed = useCookieConsentStore(
    (state) => Boolean(state.consent?.categories.analytics),
  );
  const marketingAllowed = useCookieConsentStore(
    (state) => Boolean(state.consent?.categories.marketing),
  );

  const latestRouteRef = useRef({ pathname, search, measurementId, debugMode });
  latestRouteRef.current = { pathname, search, measurementId, debugMode };

  useEffect(() => {
    return bindAnalyticsConsentListener(() => latestRouteRef.current);
  }, []);

  useEffect(() => {
    captureNavigationContext({ pathname, search });

    if (!analyticsAllowed) {
      deactivateGoogleAnalytics(measurementId);
      return;
    }

    initializeGoogleAnalytics({ measurementId, debugMode });
    trackPageView({ pathname, search, measurementId, debugMode });
  }, [pathname, search, analyticsAllowed, marketingAllowed, measurementId, debugMode]);

  return null;
}
