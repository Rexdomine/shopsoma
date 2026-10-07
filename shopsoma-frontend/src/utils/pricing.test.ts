import { describe, expect, it } from 'vitest';
import { cleanNumberString, formatWithCommas } from './pricing';

describe('cleanNumberString', () => {
  it('handles empty or null values', () => {
    expect(cleanNumberString('')).toBe('');
    expect(cleanNumberString(null)).toBe('');
    expect(cleanNumberString(undefined)).toBe('');
  });

  it('strips commas from numbers', () => {
    expect(cleanNumberString('50,000')).toBe('50000');
    expect(cleanNumberString('1,234,567')).toBe('1234567');
  });

  it('strips currency symbols and spaces', () => {
    expect(cleanNumberString('₦50,000')).toBe('50000');
    expect(cleanNumberString('$ 1,200.50')).toBe('1200.50');
  });

  it('preserves decimals up to maxDecimals', () => {
    expect(cleanNumberString('5000.')).toBe('5000.');
    expect(cleanNumberString('5000.5')).toBe('5000.5');
    expect(cleanNumberString('5000.50')).toBe('5000.50');
    expect(cleanNumberString('5000.555', 2)).toBe('5000.55');
  });

  it('removes subsequent decimal points if multiple are entered', () => {
    expect(cleanNumberString('50.0.0')).toBe('50.00');
  });
});

describe('formatWithCommas', () => {
  it('returns empty string for empty input', () => {
    expect(formatWithCommas('')).toBe('');
    expect(formatWithCommas(null)).toBe('');
    expect(formatWithCommas(undefined)).toBe('');
  });

  it('formats whole numbers with thousands separators', () => {
    expect(formatWithCommas('5')).toBe('5');
    expect(formatWithCommas('50')).toBe('50');
    expect(formatWithCommas('500')).toBe('500');
    expect(formatWithCommas('5000')).toBe('5,000');
    expect(formatWithCommas('50000')).toBe('50,000');
    expect(formatWithCommas('500000')).toBe('500,000');
    expect(formatWithCommas('5000000')).toBe('5,000,000');
  });

  it('handles decimals gracefully while typing', () => {
    expect(formatWithCommas('5000.')).toBe('5,000.');
    expect(formatWithCommas('5000.5')).toBe('5,000.5');
    expect(formatWithCommas('5000.50')).toBe('5,000.50');
    expect(formatWithCommas('.5')).toBe('.5');
    expect(formatWithCommas('0.5')).toBe('0.5');
  });

  it('formats numbers already formatted or with currency symbols', () => {
    expect(formatWithCommas('5,000')).toBe('5,000');
    expect(formatWithCommas('₦50000')).toBe('50,000');
  });
});
