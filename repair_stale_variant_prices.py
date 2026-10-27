#!/usr/bin/env python3
"""
Wrapper script for normalize_single_product_prices.py in shopsoma-backend.

Usage:
    python repair_stale_variant_prices.py
    python repair_stale_variant_prices.py --dry-run
    python repair_stale_variant_prices.py --apply
"""
import os
import sys

BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shopsoma-backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from normalize_single_product_prices import main  # noqa: E402


if __name__ == "__main__":
    main()
