#!/usr/bin/env bash
set -euo pipefail

home_file="shopsoma-frontend/src/pages/Home.tsx"

if ! rg -n "formatPriceWithConversion" "$home_file" >/dev/null; then
  echo "ERROR: Home page is not using formatPriceWithConversion for prices."
  exit 1
fi

if rg -n "formatBasePrice" "$home_file" >/dev/null; then
  echo "ERROR: Home page still uses formatBasePrice; remove it for currency-aware conversion."
  exit 1
fi

echo "OK: Home page uses currency-aware price conversion."
