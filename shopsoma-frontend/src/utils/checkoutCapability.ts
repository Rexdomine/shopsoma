const CHECKOUT_CAPABILITY_PREFIX = 'shopsoma_checkout_capability:';

const capabilityKey = (orderId: string) => `${CHECKOUT_CAPABILITY_PREFIX}${orderId}`;

export const saveCheckoutCapability = (orderId: string, capability?: string | null) => {
  if (!orderId || !capability) return;
  try {
    sessionStorage.setItem(capabilityKey(orderId), capability);
  } catch {
    // Session storage is a convenience bridge for same-tab guest redirects only.
  }
};

export const loadCheckoutCapability = (orderId?: string | null): string | undefined => {
  if (!orderId) return undefined;
  try {
    return sessionStorage.getItem(capabilityKey(orderId)) || undefined;
  } catch {
    return undefined;
  }
};

export const clearStoredCheckoutCapability = (orderId?: string | null) => {
  if (!orderId) return;
  try {
    sessionStorage.removeItem(capabilityKey(orderId));
  } catch {
    // Ignore storage failures; server authorization remains authoritative.
  }
};
