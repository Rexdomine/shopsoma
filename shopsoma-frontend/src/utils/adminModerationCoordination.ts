import type { Product } from '../types';

export const moderationLeaseMs = 2 * 60 * 1000;

export const moderationAmbiguityKey = (productId: string) => `admin-moderation-outcome-unknown:${productId}`;
export const moderationLockName = (productId: string) => `shopsoma-admin-moderation:${productId}`;

export type ModerationCycleProduct = Pick<Product, 'id' | 'title' | 'description'>;

export const hasCurrentModerationAmbiguity = (product: ModerationCycleProduct) => {
  try {
    const marker = localStorage.getItem(moderationAmbiguityKey(product.id));
    if (!marker) return false;
    const parsed = JSON.parse(marker) as { cycleSignature?: string; leaseUntil?: number };
    if (parsed.cycleSignature && typeof parsed.leaseUntil === 'number' && parsed.leaseUntil > Date.now()) return true;
  } catch {
    // Treat malformed persisted state as stale and clear it below.
  }
  localStorage.removeItem(moderationAmbiguityKey(product.id));
  return false;
};

export const saveModerationAmbiguity = (product: ModerationCycleProduct, owner: string) => {
  localStorage.setItem(moderationAmbiguityKey(product.id), JSON.stringify({
    // Admin edits do not expose an authoritative moderation-cycle boundary.
    // Keep the lock until the server reports a terminal outcome.
    cycleSignature: `${product.title}\\u0000${product.description ?? ''}`,
    owner,
    leaseUntil: Date.now() + moderationLeaseMs,
  }));
};

export const clearModerationAmbiguity = (productId: string) => {
  localStorage.removeItem(moderationAmbiguityKey(productId));
};
