const CHECKOUT_CAPABILITY_PREFIX = 'shopsoma_checkout_capability:';

const capabilityKey = (orderId: string) =>
  `${CHECKOUT_CAPABILITY_PREFIX}${orderId.trim().toLocaleUpperCase('en-US')}`;
const legacyCapabilityKey = (orderId: string) =>
  `${CHECKOUT_CAPABILITY_PREFIX}${orderId.trim()}`;

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
    const canonicalKey = capabilityKey(orderId);
    const canonicalValue = sessionStorage.getItem(canonicalKey);
    if (canonicalValue) return canonicalValue;

    const legacyKey = legacyCapabilityKey(orderId);
    if (legacyKey === canonicalKey) return undefined;
    const legacyValue = sessionStorage.getItem(legacyKey);
    if (!legacyValue) return undefined;

    // Migrate values written by the pre-normalization frontend without changing
    // the capability token itself.
    sessionStorage.setItem(canonicalKey, legacyValue);
    sessionStorage.removeItem(legacyKey);
    return legacyValue;
  } catch {
    return undefined;
  }
};

export const clearStoredCheckoutCapability = (orderId?: string | null) => {
  if (!orderId) return;
  try {
    sessionStorage.removeItem(capabilityKey(orderId));
    sessionStorage.removeItem(legacyCapabilityKey(orderId));
  } catch {
    // Ignore storage failures; server authorization remains authoritative.
  }
};
