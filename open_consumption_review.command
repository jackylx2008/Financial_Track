#!/bin/bash

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ORDER_REVIEW="$SCRIPT_DIR/processed_data/normalized/orders_full_review.html"
TAOBAO_REVIEW="$SCRIPT_DIR/processed_data/normalized/payment_transactions_full_review.html"
MISSING=0

if [ -f "$ORDER_REVIEW" ]; then
    open "$ORDER_REVIEW"
else
    printf 'Order review HTML was not found:\n%s\n' "$ORDER_REVIEW"
    MISSING=1
fi

if [ -f "$TAOBAO_REVIEW" ]; then
    open "$TAOBAO_REVIEW"
else
    printf 'Taobao payment review HTML was not found:\n%s\n' "$TAOBAO_REVIEW"
    MISSING=1
fi

if [ "$MISSING" -eq 1 ]; then
    printf 'Run transaction normalization first.\n'
    read -r -p "Press Return to close..." _unused
    exit 1
fi
