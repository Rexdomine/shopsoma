# SOMA-16 QA and release handoff

## Local setup / commands

Follow README.md. Frontend checks, from `shopsoma-frontend/`:

```sh
npm ci
npm run build
npm run lint
npm test -- src/pages/designers/Designers.test.tsx src/pages/products/__tests__/ProductList.test.tsx src/pages/products/__tests__/MenStorefront.test.tsx src/pages/products/__tests__/WomenStorefront.test.tsx src/components/layout/Header.test.tsx
```

Backend, with the normal backend requirements installed, from `shopsoma-backend/`:

```sh
python -m unittest discover -s tests -p test_designer_public_schema.py
```

## Local test steps

1. Open `/designers` at desktop width and 390px phone width. Check centered logo, custom bag icon, cover hero, featured image cards and A–Z layout.
2. Search a partial name, including an accented name typed without its accent. Choose a letter, clear/reset, and test a missing name. Refresh and browser Back should restore directory URL selections.
3. Open a featured/directory card. Verify its banner and description. Test All Items/category tabs, refine, sort and pagination using an approved vendor with several public products. Inspect requests: every product query must retain the same `vendor_id`.
4. Open a product and follow its brand link. Confirm it returns to the same designer.
5. Open phone menu. Expand Clothing, follow a real category, then reopen and follow Accessories. Repeat while already on Men/Women. Confirm the correct category is selected and menu closes.
6. Check request failure/retry, no designers, no matches, invalid/disabled vendor deep link, zero products and broken campaign images.

## Expected local result / executed evidence

- Production TypeScript/Vite build: passed.
- Targeted frontend suite: 46 tests passed across five files. Includes six new directory/storefront tests, vendor-scope/category-tab regression, mobile category-link/disclosure tests and real category-ID resolution on repeated navigation.
- Lint: completed with 0 errors and 437 warnings across the repository; warning count is not presented as a clean lint baseline comparison.
- Public schema unit tests: 3 passed (compatible defaults, allowed public fields/no extra private fields, invalid ID rejection).
- `git diff --check`: passed.
- Browser verified locally using a read-only fixture API: desktop directory/hero/cards, accent-insensitive search, card → storefront, zero-product state, browser Back restoring directory query, and 390px phone header/menu/Clothing disclosure. Screenshots in the handoff are fixture-based implementation evidence, not production content or a replacement for the approved PDF. One broken campaign URL also exercised the name-preserving fallback.
- NightWing independently reviewed the implementation and corrected a mobile category-link issue. No further vendor-scope/security blocker was reported in that review.

The backend schema checks ran without a database. Full API/database integration, populated commerce browsing in the browser, authenticated account state, real-device Safari/Chrome and staging were not executed. Automated ProductList tests cover populated products/vendor scope separately from the browser fixture.

## Staging test steps — Kayode / reviewer

1. After reviewed merge to develop and normal staging promotion, deploy the additive response schema before/with the frontend.
2. Set actual campaign artwork/brand descriptions using existing admin/vendor tooling. Verify featured flags and editorial order expectations with the client.
3. Repeat the local steps with real active/approved vendor and published approved product data; include at least two vendors with overlapping categories and one vendor with no public products.
4. Verify disabled/deleted/unapproved/onboarding vendors and pending/rejected products never surface, including direct URLs and stale cached navigation.
5. Test signed-out and signed-in mobile menus, keyboard navigation/focus, screen reader names, 320/390/768/1280/1440 widths, Safari and Chrome.
6. Compare each screen with the approved PDF. Confirm existing live refine behavior, actual product category labels and the artwork choices described in README.md before release.

## Expected staging result

Approved UI hierarchy and site identity are consistent; logo centered at all widths; featured cards remain; no clipped brand text or horizontal page overflow; category controls stay within the chosen vendor; errors recover without exposing private data; real image crops and mobile account controls are acceptable.

## Regression checks

- Men/Women collection category navigation, including repeated mobile links.
- Existing Shop Edits hero and navigation.
- Product detail gallery/options, stock and price display in NGN and USD.
- Wishlist behavior and authentication redirects.
- Add-to-bag quantity and existing cart/checkout behavior using staging test data only.
- Guest footer/cookie consent and authenticated orders/profile navigation.

No merge, staging deployment, production deployment or live purchase was performed by this handoff task.
