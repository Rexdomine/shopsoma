export const normalizeColorValue = (value?: string | null) => value?.trim().toLowerCase() ?? '';

export const hasSolidColorHex = (hex?: string | null) =>
  Boolean(hex && /^#[0-9A-Fa-f]{6}$/.test(hex));
