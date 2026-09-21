#!/bin/bash

set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REVIEW_FILE="$SCRIPT_DIR/processed_data/normalized/bank_transactions_full_review.html"

if [ ! -f "$REVIEW_FILE" ]; then
    printf 'Bank review HTML was not found:\n%s\n' "$REVIEW_FILE"
    printf 'Run transaction normalization first.\n'
    read -r -p "Press Return to close..." _unused
    exit 1
fi

open "$REVIEW_FILE"
