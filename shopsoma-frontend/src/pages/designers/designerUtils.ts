import type { Designer } from '../../services/designerService';
import { normalizeProductImageUrl } from '../../utils/productImages';

export const designerPath = (id: string) => `/designers/${encodeURIComponent(id)}`;
export const normalizeName = (name: string) => name.normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLocaleLowerCase();
export const designerImage = (designer: Designer) =>
  normalizeProductImageUrl(
    designer.featured_storefront_image_url ||
      designer.campaign_image_url ||
      designer.image_url ||
      designer.logo_url
  );
/** Public API eligibility is authoritative; this only checks visual readiness. */
export const readyDesigners = (items: Designer[]) => items.filter(d => d.business_name.trim() && designerImage(d)).sort((a,b) => a.business_name.localeCompare(b.business_name));
export const filterDesigners = (items: Designer[], query: string, letter: string) => items.filter(d => {
  const name = normalizeName(d.business_name);
  return query.trim() ? name.includes(normalizeName(query)) : letter === 'All' || (letter === '#' ? !/^[a-z]/.test(name) : name.startsWith(letter.toLowerCase()));
});
export const FEATURED_DESIGNER_LIMIT = 4;
/**
 * Admin-curated designers lead. Remaining slots are filled alphabetically,
 * preferring designers with a published catalogue, so the row matches the
 * approved four-card layout without inventing or duplicating brands.
 */
export const featuredDesigners = (items: Designer[]) => {
  const curated = items.filter(d => d.is_featured_storefront);
  const rest = items.filter(d => !d.is_featured_storefront);
  const stocked = rest.filter(d => (d.published_products_count ?? 0) > 0);
  const unstocked = rest.filter(d => !((d.published_products_count ?? 0) > 0));
  return [...curated, ...stocked, ...unstocked].slice(0, FEATURED_DESIGNER_LIMIT);
};
