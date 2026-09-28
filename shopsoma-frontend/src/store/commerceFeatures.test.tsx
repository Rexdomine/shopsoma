import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { useCurrencyStore } from './currencyStore';
import { usePreferenceStore } from './preferenceStore';
import CurrencySwitcher from '../components/common/CurrencySwitcher';
import { getCommerceFeatures } from '../services/settingsService';
vi.mock('../services/settingsService', () => ({ getCommerceFeatures: vi.fn(), getExchangeRate: vi.fn() }));
beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  useCurrencyStore.getState().applyCommerceFeatures({ stripe_enabled: false, usd_switching_enabled: false });
});
describe('commerce feature gates', () => {
  it.each([[false, false], [false, true], [true, false], [true, true]])('keeps Stripe=%s and USD=%s independent', (stripe, usd) => {
    useCurrencyStore.getState().applyCommerceFeatures({ stripe_enabled: stripe, usd_switching_enabled: usd });
    useCurrencyStore.getState().setCurrency('USD');
    usePreferenceStore.getState().setCurrency('USD');
    expect(useCurrencyStore.getState().commerceFeatures.stripe_enabled).toBe(stripe);
    expect(useCurrencyStore.getState().currentCurrency).toBe(usd ? 'USD' : 'NGN');
    expect(usePreferenceStore.getState().currency).toBe(usd ? 'USD' : 'NGN');
    render(<CurrencySwitcher value="NGN" onChange={vi.fn()} />);
    expect(Boolean(screen.queryByRole('button', { name: 'USD' }))).toBe(usd);
  });
  it('ignores persisted USD and untrusted persisted flags before settings load', async () => {
    localStorage.setItem('shopsoma-currency', JSON.stringify({ state: { currentCurrency: 'USD', commerceFeatures: { usd_switching_enabled: true, stripe_enabled: true } }, version: 0 }));
    await useCurrencyStore.persist.rehydrate();
    expect(useCurrencyStore.getState().currentCurrency).toBe('NGN');
    expect(useCurrencyStore.getState().commerceFeatures.usd_switching_enabled).toBe(false);
    useCurrencyStore.getState().toggleCurrency();
    expect(useCurrencyStore.getState().currentCurrency).toBe('NGN');
  });
  it('holds a returning USD preference until settings permit it', () => {
    useCurrencyStore.setState({ commerceFeaturesLoaded: false });
    usePreferenceStore.getState().setCurrency('USD');
    expect(usePreferenceStore.getState().currency).toBe('NGN');
    useCurrencyStore.getState().applyCommerceFeatures({ stripe_enabled: false, usd_switching_enabled: true });
    expect(usePreferenceStore.getState().currency).toBe('USD');
    expect(useCurrencyStore.getState().currentCurrency).toBe('USD');
  });
  it('fails closed after a refresh failure, updates both stores and converts source USD', async () => {
    useCurrencyStore.getState().applyCommerceFeatures({ stripe_enabled: true, usd_switching_enabled: true });
    useCurrencyStore.getState().setCurrency('USD');
    vi.mocked(getCommerceFeatures).mockRejectedValueOnce(new Error('offline'));
    await useCurrencyStore.getState().fetchCommerceFeatures();
    expect(useCurrencyStore.getState().currentCurrency).toBe('NGN');
    expect(usePreferenceStore.getState().currency).toBe('NGN');
    expect(localStorage.getItem('shopsoma_pref_currency')).toBe('NGN');
    expect(useCurrencyStore.getState().convertPrice(10, 'USD', 'NGN')).toBe(8330);
    expect(useCurrencyStore.getState().formatPrice(10, 'USD')).toBe('$10.00');
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

const enabled = { stripe_enabled: true, usd_switching_enabled: true };
const disabled = { stripe_enabled: false, usd_switching_enabled: false };

function expectNormalizedNGN() {
  expect(useCurrencyStore.getState().currentCurrency).toBe('NGN');
  expect(usePreferenceStore.getState().currency).toBe('NGN');
  expect(usePreferenceStore.getState().pendingCurrency).toBeNull();
  expect(localStorage.getItem('shopsoma_pref_currency')).toBe('NGN');
  expect(JSON.parse(localStorage.getItem('shopsoma-currency')!).state.currentCurrency).toBe('NGN');
}

describe('commerce refresh ordering', () => {
  it.each(['success', 'error'] as const)('ignores an older enabled response after the latest refresh %s', async outcome => {
    useCurrencyStore.setState({ commerceFeaturesLoaded: false });
    usePreferenceStore.getState().setCurrency('USD');
    const older = deferred<typeof enabled>();
    const newer = deferred<typeof enabled>();
    vi.mocked(getCommerceFeatures).mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    const first = useCurrencyStore.getState().fetchCommerceFeatures();
    const second = useCurrencyStore.getState().fetchCommerceFeatures();
    if (outcome === 'success') newer.resolve(disabled);
    else newer.reject(new Error('offline'));
    await second;
    older.resolve(enabled);
    await first;
    expect(useCurrencyStore.getState().commerceFeatures).toEqual(disabled);
    expectNormalizedNGN();
  });

  it('ignores an older error after a newer successful refresh', async () => {
    const older = deferred<typeof enabled>();
    vi.mocked(getCommerceFeatures).mockReturnValueOnce(older.promise).mockResolvedValueOnce(enabled);
    const first = useCurrencyStore.getState().fetchCommerceFeatures();
    await useCurrencyStore.getState().fetchCommerceFeatures();
    useCurrencyStore.getState().setCurrency('USD');
    older.reject(new Error('late failure'));
    await first;
    expect(useCurrencyStore.getState().commerceFeatures).toEqual(enabled);
    expect(useCurrencyStore.getState().currentCurrency).toBe('USD');
  });

  it.each(['success', 'error'] as const)('ignores stale read %s after an admin save and allows a later refresh', async outcome => {
    useCurrencyStore.getState().applyCommerceFeatures(enabled);
    useCurrencyStore.getState().setCurrency('USD');
    const older = deferred<typeof enabled>();
    vi.mocked(getCommerceFeatures).mockReturnValueOnce(older.promise);
    const read = useCurrencyStore.getState().fetchCommerceFeatures();
    const saved = { stripe_enabled: true, usd_switching_enabled: false };
    useCurrencyStore.getState().applyCommerceFeatures(saved);
    if (outcome === 'success') older.resolve(enabled);
    else older.reject(new Error('late failure'));
    await read;
    expect(useCurrencyStore.getState().commerceFeatures).toEqual(saved);
    expectNormalizedNGN();
    vi.mocked(getCommerceFeatures).mockResolvedValueOnce(enabled);
    await useCurrencyStore.getState().fetchCommerceFeatures();
    expect(useCurrencyStore.getState().commerceFeatures).toEqual(enabled);
    expectNormalizedNGN();
  });
});
