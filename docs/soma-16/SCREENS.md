# Screen-by-screen implementation guide

Use the approved v2 PDF for layout review. All paths below are relative to `shopsoma-frontend/src/`.

## 1. Global navigation — desktop and phone

Files: `components/layout/Header.tsx`, `MobileClothingMenu.tsx`.

The existing SHOPSOMA logo remains absolutely centered, independent of left search/menu and right account/bag controls. Desktop retains the live site's two-row arrangement. Designers is added after Shop Edits. The original custom shopping bag SVG and quantity remain unchanged.

Phone: menu toggles between menu/close; search remains beside it. Men and Women have Clothing disclosures and Accessories links. Clothing expands existing active clothing subcategories; selecting one closes the menu and routes to its collection. Accessories resolves the matching category slug to its API ID. Shop Edits and Designers follow. Existing authenticated account/orders/wishlist/sign-out and guest sign-in/create-account sections are reused.

Check: 390px screen, centered logo, correct bag shape, long account names, all links, menu close, keyboard access. Signed-in reference uses real account state, not a hardcoded administrator identity.

## 2. Designers landing — `/designers`

Files: `pages/designers/Designers.tsx`, `DesignerVisuals.tsx`, `designers.css`, `designerUtils.ts`.

A full-width editorial hero introduces Shop by Designer. The featured section stays in the page, with four cover-image cards on wide screens and white brand-name/arrow overlays. There are no detached green caption panels. Entire cards are links with keyboard focus styles. Desktop uses four columns; tablet two; phone featured cards stack and the main directory uses two columns.

A–Z follows the featured section. All, A–Z and # are buttons; # groups names that do not start with Latin letters. Brand names sort alphabetically. `?q=` searches names case/accent-insensitively; `?letter=` stores the chosen letter. Selecting a letter clears search; typing clears letter selection. Search results do not remove the featured section.

States: initial loading skeleton, network error/retry that keeps the URL query, empty catalog, no search results with reset, broken image with readable name/arrow fallback. No blank screen or fake designer is used on failure.

## 3. Designer storefront — `/designers/:designerId`

Files: `pages/designers/DesignerStorefront.tsx`, shared visuals, `pages/products/ProductList.tsx`.

Resolve the stable vendor ID against the public eligible designer list before rendering products. Render campaign banner, brand name, introductory description and All designers link. The shared ProductList receives `initialParams={{vendor_id: designerId}}`, so product fetches and subsequent controls retain that vendor scope.

Use All Items and category tabs derived from the vendor's products. When a real category navigation list is supplied elsewhere, API UUIDs are used; a derived category label is never sent as a UUID. Reuse existing responsive product cards, prices/currency, wishlist, search/refine, sort and pagination.

States: loading, public-list error/retry, unavailable or invalid designer, empty products and existing product API error handling. An unpublished/unapproved/disabled designer must not expose a storefront through a deep link. The public server still enforces product visibility.

## 4. Refine, sort and category selection

File: `pages/products/ProductList.tsx`.

Use the existing site's controls. Refinements apply live. Reset/All Items returns to the current designer catalog, not a different vendor. No general shopping-interest prompt is injected on a designer storefront. Category selection, product search and pagination must preserve the vendor ID.

Existing price handling, availability, sizes, colors, currency and wishlist behavior is intentionally reused. Test with the real catalog; product metadata determines which controls/options exist. Verify no-results and clearing refinements. The inherited price range behavior normalizes reversed bounds.

## 5. Product detail and return path

File: `pages/products/ProductDetail.tsx`.

The brand label above the product title is now a link to `/designers/{product.vendor_id}`. Use the stable ID, never the display name as identity. Existing gallery, variation selection, stock, pricing, add-to-bag and cart flow remain owned by the existing product screen/stores.

From a designer card: open product → verify brand link → return to that designer. Browser Back to the directory restores its URL search/letter. Test missing vendor labels and unavailable designers gracefully.

## File map

| Concern | Source |
|---|---|
| Public designer DTO/client | `services/designerService.ts` |
| Eligibility display/readiness, search, featured ordering | `pages/designers/designerUtils.ts` |
| Designer route registration | `router/index.tsx` |
| Responsive hero/cards/empty states | `pages/designers/DesignerVisuals.tsx`, `designers.css` |
| Public API schema additions | `shopsoma-backend/app/schemas/vendor.py` |
| Regression tests | `Designers.test.tsx`, `ProductList.test.tsx`, `Header.test.tsx`, backend `test_designer_public_schema.py` |
