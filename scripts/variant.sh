#!/usr/bin/env bash
# Copy one variant of the orderflow sources into the fixture working tree.
# Used to build the git history; the presenter uses scripts/demo.sh instead.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VARIANT="${1:?usage: variant.sh clean|drifted}"
SRC="$HERE/samples/_variants/$VARIANT/orderflow"
DST="$HERE/samples/orderflow/orderflow"
[ -d "$SRC" ] || { echo "no such variant: $VARIANT" >&2; exit 2; }
cp "$SRC"/*.py "$DST"/
echo "orderflow sources set to: $VARIANT"
