#!/usr/bin/env bash
set -euo pipefail

check_fixed_pattern() {
  local pattern="$1"
  local message="$2"

  if rg -n --glob '*.tsx' -F "$pattern" shopsoma-frontend/src; then
    echo "ERROR: $message"
    exit 1
  fi
}

check_fixed_pattern 'bg-[#F9FAFB]' 'Replace bg-[#F9FAFB] with bg-[var(--color-page-bg)].'
check_fixed_pattern 'bg-[#FAFAF8]' 'Replace bg-[#FAFAF8] with bg-[var(--color-page-bg)].'
check_fixed_pattern 'bg-[#F6F6F3]' 'Replace bg-[#F6F6F3] with bg-[var(--color-page-bg)].'
check_fixed_pattern 'bg-gradient-to-br from-[#F6F6F3] to-[#E8E8E3]' 'Replace the off-white gradient with bg-[var(--color-page-bg)].'

if rg -n --glob '*.tsx' 'min-h-screen.*bg-gray-50|bg-gray-50.*min-h-screen' shopsoma-frontend/src; then
  echo 'ERROR: Replace min-h-screen bg-gray-50 with bg-[var(--color-page-bg)].'
  exit 1
fi

echo 'OK: no off-white page backgrounds detected.'
