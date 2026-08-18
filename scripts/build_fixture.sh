#!/usr/bin/env bash
# Build the demo fixture's git history: two commits, tagged `clean` and `drifted`.
#
# The fixture is a git repo in its own right, so it cannot be committed inside
# the SpecGuard repo. Run this once after cloning.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$HERE/samples/orderflow"
SRC="$HERE/samples/_variants"

rm -rf "$REPO/.git" "$REPO/.specguard"

cp "$SRC/clean/orderflow/"*.py "$REPO/orderflow/"
git -C "$REPO" init -q -b main
git -C "$REPO" config user.email "team@orderflow.example"
git -C "$REPO" config user.name "OrderFlow Team"
git -C "$REPO" add -A
git -C "$REPO" commit -q -m "OrderFlow: pricing, shipping, inventory and checkout per SPEC.md"
git -C "$REPO" tag clean

cp "$SRC/drifted/orderflow/"*.py "$REPO/orderflow/"
git -C "$REPO" add -A
git -C "$REPO" commit -q -m "Tidy checkout, simplify validation, adjust free-shipping check

Nothing here is meant to change behaviour. The receipt builder is a
comprehension now, validate_order got shorter, and the payment handler
catches the gateway's errors in one place."
git -C "$REPO" tag drifted
git -C "$REPO" checkout -q clean

echo "fixture ready — tags 'clean' and 'drifted', currently on 'clean'"
