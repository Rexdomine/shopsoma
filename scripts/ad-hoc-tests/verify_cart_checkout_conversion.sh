#!/usr/bin/env bash
set -euo pipefail

files=(
  "shopsoma-frontend/src/components/modals/AddToBagModal.tsx"
  "shopsoma-frontend/src/pages/cart/Cart.tsx"
  "shopsoma-frontend/src/pages/checkout/Checkout.tsx"
)

for file in "${files[@]}"; do
  if ! rg -n "formatPriceWithConversion" "$file" >/dev/null; then
    echo "ERROR: $file is missing formatPriceWithConversion."
    exit 1
  fi
done

if ! rg -n "useCurrencyStore" shopsoma-frontend/src/pages/cart/Cart.tsx shopsoma-frontend/src/pages/checkout/Checkout.tsx >/dev/null; then
  echo "ERROR: Cart/Checkout are missing useCurrencyStore for exchange rates."
  exit 1
fi

echo "OK: cart/checkout/add-to-bag use exchange-rate conversion."
