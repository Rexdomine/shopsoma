# SOMA-16 — Designer UI handoff

Prepared for Kayode. Rex confirmed client approval of `shopsoma-soma16-ui-design-v2.pdf` on 27 October 2026.

## Start here

This is an integration into the existing SHOPSOMA React/TypeScript/Vite app. It is not a separate storefront or a new commerce implementation. Start with the task branch/PR targeting `develop`. The ZIP also contains a full frontend source snapshot, changed backend files, and a Git patch.

Base: `331d85b3207dcafe83122f37dbcdf842c307b2d2` (develop).
Task branch: `feature/soma-16-designer-ui-handoff`.

1. Read `SCREENS.md` beside this file alongside the approved PDF.
2. Review the PR diff, including the small public designer response schema addition.
3. Run the frontend against your local backend. Populate actual approved vendor campaign images/descriptions using existing vendor/admin tools.
4. Complete `QA.md` locally, then on staging after reviewer-approved merge.

## Run locally

From the repository root:

```sh
git fetch origin
git switch feature/soma-16-designer-ui-handoff
cd shopsoma-frontend
npm ci
cp .env.example .env.local
# Set VITE_API_BASE_URL to your local backend, usually http://localhost:8050/api/v1
npm run dev
```

Use the repository's existing backend setup/environment and database instructions. No new npm dependency, environment variable, migration, or database table is required by this change. Do not put real credentials in the handoff folder.

Open `/designers`, then follow a designer card. Use an existing approved, active vendor with a campaign image or logo and public products for populated-state QA.

### Applying the download instead of the branch

The ZIP's `frontend/` is a complete source snapshot of `shopsoma-frontend/` with dependencies/build outputs/secrets excluded. Run `npm ci` there to install dependencies. It still needs the existing SHOPSOMA API.

For an existing checkout, prefer reviewing/applying the patch rather than overwriting the entire frontend:

```sh
# From a clean branch based on the base commit above:
git apply --check /path/to/soma16-handoff/changes.patch
git apply /path/to/soma16-handoff/changes.patch
```

If the check reports conflicts, use the PR/three-way Git workflow; do not force-copy over newer work. The `changed-files/` folder mirrors repository paths for manual inspection. Do not both apply the patch and copy replacements.

## Backend contract

Existing public `GET /api/v1/designers` remains authoritative for eligibility: approved vendor, onboarding completed, active non-deleted store, active user. It now serializes three existing model fields:

- `business_description`: optional brand introduction.
- `featured_storefront_image_url`: optional campaign artwork URL.
- `is_featured_storefront`: existing editorial featured flag.

Deploy the schema addition before/with the frontend. Older responses remain usable with optional-field defaults, but cannot display campaign imagery/descriptions. No private vendor endpoint is called. Public products still come from the existing `/products` API with `vendor_id`; existing backend moderation rules remain authoritative.

## Assets and editorial setup

The approved PDF is the visual reference; the example brand imagery/names in it are not seeded into production. The implementation uses the real logo, fonts, custom bag icon, header, footer, cards and commerce controls already in the repository.

Directory hero currently uses the existing site asset `public/images/hero/shop-edits-2088.jpg`. Replace that reference in `DesignerVisuals.tsx` with the final approved full-resolution directory campaign asset when supplied. Do not crop text out of the PDF and ship it as UI.

Each designer uses `featured_storefront_image_url`, falling back to `logo_url`. For the approved photographic appearance, supply campaign images with the subject clear of bottom name/arrow overlays; logos are a compatibility fallback. Cards use cover cropping. Test each crop on desktop and phone. Brand introductions come from `business_description`; no hardcoded fictional biography is shipped.

The four featured positions prefer eligible vendors with `is_featured_storefront=true`. If none are flagged, up to four eligible designers in alphabetical order appear. Fewer than four eligible brands means fewer cards, never duplicated fake brands. The directory's visual-readiness check requires a name and nonblank image URL; backend eligibility is not duplicated or weakened in the UI.

## Review notes

The storefront deliberately reuses existing ProductList category taxonomy, live refine controls, sort, prices, pagination, wishlist and product navigation. Category labels reflect actual products (for example Dresses/Accessories), rather than inventing a Clothing database category. Mobile Clothing expands the existing category hierarchy.

Directory search/A–Z live in the URL and restore with browser Back. ProductList retains its existing filter state semantics: page/search URL behavior is inherited; all refine/sort selections are not persisted across a full unmount. Filter selections apply live, not through a new staged Apply button. These integration choices should be checked against the PDF during staging review.

This delivery is developer handoff-ready, not a production deployment. Database-backed end-to-end moderation, authenticated mobile menu, wishlist/cart and staging verification remain in QA.md.
