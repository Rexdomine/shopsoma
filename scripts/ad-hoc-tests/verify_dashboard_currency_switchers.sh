#!/usr/bin/env bash
set -euo pipefail

files=(
  "shopsoma-frontend/src/pages/vendor/VendorProducts.tsx"
  "shopsoma-frontend/src/pages/vendor/VendorProductView.tsx"
  "shopsoma-frontend/src/pages/admin/AdminProducts.tsx"
  "shopsoma-frontend/src/pages/admin/AdminProductDetail.tsx"
)

for file in "${files[@]}"; do
  if ! rg -n "CurrencySwitcher" "$file" >/dev/null; then
    echo "ERROR: $file is missing CurrencySwitcher."
    exit 1
  fi

  if ! rg -n "formatPriceWithConversion" "$file" >/dev/null; then
    echo "ERROR: $file is missing formatPriceWithConversion."
    exit 1
  fi
done

echo "OK: dashboard product pages use currency switchers and conversion."
