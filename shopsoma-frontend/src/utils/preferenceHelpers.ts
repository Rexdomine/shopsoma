import type { Product } from '../types';
import type { PreferenceData } from '../services/preferenceService';

const normalize = (value?: string | null) => value?.toLowerCase().trim() ?? '';

const filterByDesigners = (items: Product[], designers: string[]) => {
  const normalized = designers.map(normalize).filter(Boolean);
  if (!normalized.length) return [];
  return items.filter((product) => {
    const vendor = normalize(product.vendor_name);
    return normalized.some((name) => vendor === name);
  });
};

const filterByCategories = (items: Product[], categories: string[]) => {
  const normalized = categories.map(normalize).filter(Boolean);
  if (!normalized.length) return [];
  return items.filter((product) => {
    const category = normalize(product.category);
    const description = normalize(product.description);
    return normalized.some((prefCategory) =>
      category.includes(prefCategory) || description.includes(prefCategory)
    );
  });
};

const filterByInterest = (items: Product[], interest?: string | null) => {
  if (!interest) return [];
  const target = interest === 'menswear' ? 'men' : interest === 'womenswear' ? 'women' : '';
  if (!target) return [];
  return items.filter((product) => {
    const category = normalize(product.category);
    const description = normalize(product.description);
    return category.startsWith(target) || description.startsWith(`${target} -`);
  });
};

export const personalizeProducts = (products: Product[], preference?: PreferenceData | null): Product[] => {
  if (!preference) return products;

  const favoriteDesigners = preference.favoriteDesigners ?? [];
  if (favoriteDesigners.length) {
    return filterByDesigners(products, favoriteDesigners);
  }

  const favoriteCategories = preference.favoriteCategories ?? [];
  if (favoriteCategories.length) {
    const categoryResult = filterByCategories(products, favoriteCategories);
    if (categoryResult.length) {
      return categoryResult;
    }
  }

  const interestResult = filterByInterest(products, preference.interest);
  if (interestResult.length) return interestResult;

  return products;
};
