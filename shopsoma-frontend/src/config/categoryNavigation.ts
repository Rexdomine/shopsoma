import type { Category } from '../types';

/**
 * Helper to build static Category objects with valid UUID format IDs.
 */
function makeCategory(
  id: string,
  name: string,
  slug: string,
  display_order: number,
  parent_id: string | null = null,
  description?: string
): Category {
  return {
    id,
    name,
    slug,
    description: description || name,
    parent_id,
    image_url: null,
    display_order,
    is_active: true,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
  };
}

// Well-known primary IDs (matching local database seeds/migrations)
export const WOMEN_CATEGORY_ID = '27b5a940-610d-4243-a796-7e4c63b04060';
export const MEN_CATEGORY_ID = 'b5be5460-0d0d-4302-a2ca-f4cfcd518135';

/**
 * Default subcategories for the Women Storefront.
 * Displayed in the subcategory navigation bar under the hero banner.
 */
export const DEFAULT_WOMEN_SUBCATEGORIES: Category[] = [
  makeCategory('b3bcadf9-1878-40eb-9d53-2c2258b3a11b', "Women's Tops", 'women-tops', 1, WOMEN_CATEGORY_ID),
  makeCategory('f876f16a-5faf-4ed8-986d-29aae4a954bb', "Women's Dresses", 'women-dresses', 2, WOMEN_CATEGORY_ID),
  makeCategory('3c0a63b2-31d2-4c30-af12-e0a735153bf0', "Women's Bottoms", 'women-bottoms', 3, WOMEN_CATEGORY_ID),
  makeCategory('33f58709-41f2-439f-a896-c67205fa5545', "Women's Accessories", 'women-accessories', 4, WOMEN_CATEGORY_ID),
  makeCategory('afbb0091-941c-4957-b279-6be4ba78019e', "Women's Shoes", 'women-shoes', 5, WOMEN_CATEGORY_ID),
  makeCategory('8c066c29-0f8c-4428-965c-50a5e60d4801', "Women's Activewear", 'women-activewear', 6, WOMEN_CATEGORY_ID),
  makeCategory('c484f266-dde6-48c8-a765-8b52c8c9a168', "Women's Outerwear", 'women-outerwear', 7, WOMEN_CATEGORY_ID),
  makeCategory('dccb7e3d-7f6a-4365-8796-c1279fb6004a', "Women's Swimwear", 'women-swimwear', 8, WOMEN_CATEGORY_ID),
  makeCategory('d9c26cfb-7081-4816-8a32-6a09346f8df4', "Women's Lingerie/Pyjamas", 'women-lingerie-pyjamas', 9, WOMEN_CATEGORY_ID),
  makeCategory('97a29754-0eb4-4b7f-9d11-aabfd18ce25c', "Women's Sets", 'women-sets', 10, WOMEN_CATEGORY_ID),
];

/**
 * Default subcategories for the Men Storefront.
 * Displayed in the subcategory navigation bar under the hero banner.
 */
export const DEFAULT_MEN_SUBCATEGORIES: Category[] = [
  makeCategory('5da6b1c1-d254-4a8c-bbc4-aaa0fe4e88e9', 'Tops', 'men-tops', 1, MEN_CATEGORY_ID),
  makeCategory('35d415ef-1a2c-40d1-928b-6802a7af51f0', 'Bottoms', 'men-bottoms', 2, MEN_CATEGORY_ID),
  makeCategory('7031c4c5-487e-4c97-bac2-1897201e7653', 'Activewear', 'men-activewear', 3, MEN_CATEGORY_ID),
  makeCategory('19b773ce-c2ae-4f21-9657-b87743199e69', "Men's Sets", 'men-sets', 4, MEN_CATEGORY_ID),
  makeCategory('e276d883-7fbb-4dfd-bbd2-ea1196024bfe', 'Shoes', 'men-shoes', 5, MEN_CATEGORY_ID),
  makeCategory('ecbb7abb-cb62-4158-9e94-793087056dc4', 'Accessories', 'men-accessories', 6, MEN_CATEGORY_ID),
  makeCategory('de14555d-789e-4278-9548-1bc2b6e7584c', 'Outerwear', 'men-outerwear', 7, MEN_CATEGORY_ID),
];

/**
 * Child categories for Women storefront subcategories.
 * Keyed by slug, name, and database ID to ensure matches work across environments.
 */
const rawWomenChildCategories: Record<string, Category[]> = {
  // Women's Lingerie/Pyjamas
  'women-lingerie-pyjamas': [
    makeCategory('7e120d20-1b20-4df2-a39c-851f50a8d011', 'Shapewear', 'women-lingerie-shapewear', 1, 'd9c26cfb-7081-4816-8a32-6a09346f8df4'),
    makeCategory('edcc6d13-fe39-46b4-8395-a1a7a1fbec0c', 'Bras & Bralettes', 'women-lingerie-bras-bralettes', 2, 'd9c26cfb-7081-4816-8a32-6a09346f8df4'),
    makeCategory('61d8acda-1068-4410-af5c-15238638d232', 'Panties & Briefs', 'women-lingerie-panties-briefs', 3, 'd9c26cfb-7081-4816-8a32-6a09346f8df4'),
    makeCategory('7978b8d3-00c5-4df8-872d-0ec33fe07f4b', 'Pyjamas & Sleepwear', 'women-lingerie-pyjamas-sleepwear', 4, 'd9c26cfb-7081-4816-8a32-6a09346f8df4'),
    makeCategory('0e40d900-945d-44d5-b0c4-c67f1680e60e', 'Robes & Loungewear', 'women-lingerie-robes-loungewear', 5, 'd9c26cfb-7081-4816-8a32-6a09346f8df4'),
    makeCategory('97c93ea3-d96f-42bb-a8a4-daf9b87c3519', 'Lingerie Sets', 'women-lingerie-sets', 6, 'd9c26cfb-7081-4816-8a32-6a09346f8df4'),
  ],

  // Women's Sets
  'women-sets': [
    makeCategory('a10e7b41-2c10-4fa3-b41d-9e51c8a2b012', 'Trouser Sets', 'women-sets-trouser-sets', 1, '97a29754-0eb4-4b7f-9d11-aabfd18ce25c'),
    makeCategory('dc0899a8-4d1c-4b49-a6fa-ccb40e771bf8', 'Skirt Sets', 'women-sets-skirt-sets', 2, '97a29754-0eb4-4b7f-9d11-aabfd18ce25c'),
    makeCategory('316c0593-c568-4d5c-b0c9-9352d9738fa7', 'Shorts Sets', 'women-sets-shorts-sets', 3, '97a29754-0eb4-4b7f-9d11-aabfd18ce25c'),
  ],

  // Women's Tops
  'women-tops': [
    makeCategory('b3bcadf9-0001-40eb-9d53-2c2258b3a11b', "Women's T-Shirts", 'women-tops-t-shirts', 1, 'b3bcadf9-1878-40eb-9d53-2c2258b3a11b'),
    makeCategory('03742502-86c9-40d2-896c-76c59d5817ca', "Women's Shirts", 'women-tops-shirts', 2, 'b3bcadf9-1878-40eb-9d53-2c2258b3a11b'),
    makeCategory('85e89419-fd9b-4cf7-8170-ad008e84430e', "Women's Blouses", 'women-tops-blouses', 3, 'b3bcadf9-1878-40eb-9d53-2c2258b3a11b'),
    makeCategory('178d56cc-e0a6-45da-bc8e-38179c3b9abf', 'Bodysuit', 'women-tops-bodysuit', 4, 'b3bcadf9-1878-40eb-9d53-2c2258b3a11b'),
    makeCategory('090b0b8f-31af-40e7-8640-98af969cd80a', 'Tank Tops', 'women-tops-tank-tops', 5, 'b3bcadf9-1878-40eb-9d53-2c2258b3a11b'),
  ],

  // Women's Dresses
  'women-dresses': [
    makeCategory('f876f16a-0001-4ed8-986d-29aae4a954bb', 'Casual Dresses', 'women-dresses-casual', 1, 'f876f16a-5faf-4ed8-986d-29aae4a954bb'),
    makeCategory('a5b3e223-869e-4bfe-a996-4877265a8349', 'Party Dresses', 'women-dresses-party', 2, 'f876f16a-5faf-4ed8-986d-29aae4a954bb'),
    makeCategory('4589287b-8448-4ba9-a9e0-8100ca1933f1', 'Formal Dresses', 'women-dresses-formal', 3, 'f876f16a-5faf-4ed8-986d-29aae4a954bb'),
    makeCategory('a7da3ee3-1d34-4502-9568-cb211a697dd7', 'Beach Dresses', 'women-dresses-beach-dresses', 4, 'f876f16a-5faf-4ed8-986d-29aae4a954bb'),
  ],

  // Women's Bottoms
  'women-bottoms': [
    makeCategory('3c0a63b2-0001-4c30-af12-e0a735153bf0', "Women's Jeans", 'women-bottoms-jeans', 1, '3c0a63b2-31d2-4c30-af12-e0a735153bf0'),
    makeCategory('bebc1c31-496e-4b3a-8829-06e923f66ebf', "Women's Skirts", 'women-bottoms-skirts', 2, '3c0a63b2-31d2-4c30-af12-e0a735153bf0'),
    makeCategory('05943b0b-0715-41f7-bdb5-69b73be84504', "Women's Trousers", 'women-bottoms-trousers', 3, '3c0a63b2-31d2-4c30-af12-e0a735153bf0'),
    makeCategory('7c57e631-9f22-4f04-a608-359bbb2ce568', 'Shorts', 'women-bottoms-shorts', 4, '3c0a63b2-31d2-4c30-af12-e0a735153bf0'),
  ],

  // Women's Accessories
  'women-accessories': [
    makeCategory('33f58709-0001-439f-a896-c67205fa5545', "Women's Jewellery", 'women-accessories-jewellery', 1, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('d564e2ba-0f62-419b-a32a-27d28b506874', "Women's Bracelets", 'women-accessories-bracelets', 2, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('6ee76a28-45bf-419d-b5b3-0b5067f54613', "Women's Earrings", 'women-accessories-earrings', 3, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('92c27ab4-934f-421d-8380-1c4d42e56655', "Women's Necklace", 'women-accessories-necklace', 4, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('5bc3b7c0-847d-4660-876b-49889f1df584', "Women's Rings", 'women-accessories-rings', 5, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('9e3dbaa3-0107-46db-a890-c6b93332bd2c', "Women's Watches", 'women-accessories-watches', 6, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('3cad246a-a535-4151-8d4d-01f02fe51573', "Women's Anklets", 'women-accessories-anklets', 7, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('ac3208b8-5edb-4b7e-8643-d667427cd757', "Women's Body Jewellery", 'women-accessories-body-jewellery', 8, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('da500ff2-b7b5-4cd6-90ab-a1747a651898', "Women's Brooches", 'women-accessories-brooches', 9, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('dcc9bd0f-8087-4808-90ad-eec2bdc3e9a4', "Women's Bags", 'women-accessories-bags', 10, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('d49dea09-8bfd-4879-ad0e-1ea39c7b4857', "Women's Belts", 'women-accessories-belts', 11, '33f58709-41f2-439f-a896-c67205fa5545'),
    makeCategory('3445dd70-c9e6-4c1c-8c10-aef19f905a2f', "Women's Sunglasses", 'women-accessories-sunglasses', 12, '33f58709-41f2-439f-a896-c67205fa5545'),
  ],

  // Women's Shoes
  'women-shoes': [
    makeCategory('afbb0091-0001-4957-b279-6be4ba78019e', "Women's Flats", 'women-shoes-flats', 1, 'afbb0091-941c-4957-b279-6be4ba78019e'),
    makeCategory('38a48653-fab0-4e4d-b6ca-393f4e015483', "Women's Heels", 'women-shoes-heels', 2, 'afbb0091-941c-4957-b279-6be4ba78019e'),
  ],

  // Women's Activewear
  'women-activewear': [
    makeCategory('8c066c29-0001-4428-965c-50a5e60d4801', "Women's Activewear Tops", 'women-activewear-tops', 1, '8c066c29-0f8c-4428-965c-50a5e60d4801'),
    makeCategory('0f85533f-a543-4f39-bb20-794084d08677', "Women's Activewear Bottoms", 'women-activewear-bottoms', 2, '8c066c29-0f8c-4428-965c-50a5e60d4801'),
    makeCategory('0557f2ba-094e-4b45-a6bb-ccc50ab50d60', 'Activewear Accessories', 'women-activewear-accessories', 3, '8c066c29-0f8c-4428-965c-50a5e60d4801'),
  ],

  // Women's Outerwear
  'women-outerwear': [
    makeCategory('c484f266-0001-48c8-a765-8b52c8c9a168', "Women's Jackets", 'women-outerwear-jackets', 1, 'c484f266-dde6-48c8-a765-8b52c8c9a168'),
    makeCategory('95b4270f-7f75-41e7-9057-ec10f89c5ed2', "Women's Kaftan", 'women-outerwear-kaftan', 2, 'c484f266-dde6-48c8-a765-8b52c8c9a168'),
    makeCategory('b72256e0-54d2-47df-970e-3054b906e80c', "Women's Kimonos", 'women-outerwear-kimonos', 3, 'c484f266-dde6-48c8-a765-8b52c8c9a168'),
    makeCategory('8a73aa47-178c-4697-860f-8c161cbf5f57', "Women's Ponchos", 'women-outerwear-ponchos', 4, 'c484f266-dde6-48c8-a765-8b52c8c9a168'),
    makeCategory('6c7f281c-c76f-4e9a-9c32-92a2dfb6ce81', "Women's Hoodies/Sweatshirts", 'women-outerwear-hoodies-sweatshirts', 5, 'c484f266-dde6-48c8-a765-8b52c8c9a168'),
  ],
};

/**
 * Child categories for Men storefront subcategories.
 */
const rawMenChildCategories: Record<string, Category[]> = {
  // Tops
  'men-tops': [
    makeCategory('5da6b1c1-0001-4a8c-bbc4-aaa0fe4e88e9', 'T-Shirts', 'men-tops-t-shirts', 1, '5da6b1c1-d254-4a8c-bbc4-aaa0fe4e88e9'),
    makeCategory('d455953e-07e0-41a3-8b56-b0be70003973', 'Shirts', 'men-tops-shirts', 2, '5da6b1c1-d254-4a8c-bbc4-aaa0fe4e88e9'),
  ],

  // Bottoms
  'men-bottoms': [
    makeCategory('35d415ef-0001-40d1-928b-6802a7af51f0', 'Jeans', 'men-bottoms-jeans', 1, '35d415ef-1a2c-40d1-928b-6802a7af51f0'),
    makeCategory('dac785ff-a176-4dfc-8b47-4ab19c304e41', 'Trousers', 'men-bottoms-trousers', 2, '35d415ef-1a2c-40d1-928b-6802a7af51f0'),
    makeCategory('ddafd36f-270e-4f83-b8c1-c8c77108c6e3', 'Shorts', 'men-bottoms-shorts', 3, '35d415ef-1a2c-40d1-928b-6802a7af51f0'),
  ],

  // Activewear
  'men-activewear': [
    makeCategory('7031c4c5-0001-4c97-bac2-1897201e7653', 'Activewear Tops', 'men-activewear-tops', 1, '7031c4c5-487e-4c97-bac2-1897201e7653'),
    makeCategory('8e61e3a1-e1b0-489e-82d4-3d8be39ef498', 'Activewear Bottoms', 'men-activewear-bottoms', 2, '7031c4c5-487e-4c97-bac2-1897201e7653'),
    makeCategory('0c8fc679-03ed-45fe-b8ac-8fea268448c0', 'Activewear Accessories', 'men-activewear-accessories', 3, '7031c4c5-487e-4c97-bac2-1897201e7653'),
  ],

  // Men's Sets
  'men-sets': [
    makeCategory('19b773ce-0001-4f21-9657-b87743199e69', 'Trouser Sets', 'men-sets-trouser-sets', 1, '19b773ce-c2ae-4f21-9657-b87743199e69'),
    makeCategory('41f471ea-a301-4328-b26f-94c9326059c1', 'Shorts Sets', 'men-sets-shorts-sets', 2, '19b773ce-c2ae-4f21-9657-b87743199e69'),
  ],

  // Shoes
  'men-shoes': [
    makeCategory('e276d883-0001-4dfd-bbd2-ea1196024bfe', 'Casual Shoes', 'men-shoes-casual', 1, 'e276d883-7fbb-4dfd-bbd2-ea1196024bfe'),
    makeCategory('2b85366c-d5ff-4e82-94b8-538c6b824da6', 'Formal Shoes', 'men-shoes-formal', 2, 'e276d883-7fbb-4dfd-bbd2-ea1196024bfe'),
  ],

  // Accessories
  'men-accessories': [
    makeCategory('ecbb7abb-0001-4158-9e94-793087056dc4', 'Watches/Jewellery', 'men-accessories-watches-jewellery', 1, 'ecbb7abb-cb62-4158-9e94-793087056dc4'),
    makeCategory('38c93465-3023-4042-9a60-9dc6a1c18613', 'Wallets', 'men-accessories-wallets', 2, 'ecbb7abb-cb62-4158-9e94-793087056dc4'),
    makeCategory('308c3de7-9d86-4110-8d2e-0f218d3925eb', 'Belts', 'men-accessories-belts', 3, 'ecbb7abb-cb62-4158-9e94-793087056dc4'),
    makeCategory('e535a202-53da-472a-aadb-78437f451387', 'Sunglasses', 'men-accessories-sunglasses', 4, 'ecbb7abb-cb62-4158-9e94-793087056dc4'),
    makeCategory('bb4ed5d4-1acd-4d73-b0f2-a6cbe69afd53', 'Caps/Hats', 'men-accessories-caps-hats', 5, 'ecbb7abb-cb62-4158-9e94-793087056dc4'),
  ],

  // Outerwear
  'men-outerwear': [
    makeCategory('de14555d-0001-4278-9548-1bc2b6e7584c', 'Hoodies', 'men-outerwear-hoodies', 1, 'de14555d-789e-4278-9548-1bc2b6e7584c'),
    makeCategory('534333ee-98ad-4d19-81ed-7adcce68e7de', 'Jackets', 'men-outerwear-jackets', 2, 'de14555d-789e-4278-9548-1bc2b6e7584c'),
  ],
};

/**
 * Builds a multi-key lookup dictionary for child categories
 * so lookups succeed whether queried by ID, slug, or category name.
 */
function buildLookupMap(
  defaults: Category[],
  rawChildren: Record<string, Category[]>
): Record<string, Category[]> {
  const result: Record<string, Category[]> = {};

  defaults.forEach((parent) => {
    const children = rawChildren[parent.slug] || rawChildren[parent.name] || rawChildren[parent.id];
    if (children && children.length > 0) {
      // Register under ID
      result[parent.id] = children;
      // Register under slug
      result[parent.slug] = children;
      // Register under name
      result[parent.name] = children;
      // Register under lowercase name
      result[parent.name.toLowerCase()] = children;
    }
  });

  // Also include any raw keys not matched above
  Object.entries(rawChildren).forEach(([key, children]) => {
    if (!result[key]) {
      result[key] = children;
    }
  });

  return result;
}

export const WOMEN_CHILD_CATEGORIES = buildLookupMap(
  DEFAULT_WOMEN_SUBCATEGORIES,
  rawWomenChildCategories
);

export const MEN_CHILD_CATEGORIES = buildLookupMap(
  DEFAULT_MEN_SUBCATEGORIES,
  rawMenChildCategories
);

/**
 * Merge an API or cached subcategory array with defaults.
 * Any default category missing from `fetched` (matched by slug or lowercase name)
 * is appended, and the list is sorted by `display_order`.
 */
export function mergeSubcategoriesWithDefaults(
  fetched: Category[] = [],
  defaults: Category[] = []
): Category[] {
  const seenSlugs = new Set<string>();
  const seenNames = new Set<string>();

  const merged: Category[] = [];

  fetched.forEach((category) => {
    if (!category || !category.name) return;
    const slug = (category.slug || '').trim().toLowerCase();
    const name = category.name.trim().toLowerCase();
    if (slug) seenSlugs.add(slug);
    seenNames.add(name);
    merged.push(category);
  });

  defaults.forEach((defaultCategory) => {
    const slug = (defaultCategory.slug || '').trim().toLowerCase();
    const name = defaultCategory.name.trim().toLowerCase();
    const alreadyPresent = (slug && seenSlugs.has(slug)) || seenNames.has(name);
    if (!alreadyPresent) {
      merged.push(defaultCategory);
      if (slug) seenSlugs.add(slug);
      seenNames.add(name);
    }
  });

  return merged.sort((a, b) => (a.display_order ?? 0) - (b.display_order ?? 0));
}
