#!/usr/bin/env bash
# Switch the demo fixture between its clean and drifted commits.
#   ./demo.sh clean    the code matches the spec
#   ./demo.sh drift    a normal week of development happened
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
REPO="demo/orderflow"

case "${1:-}" in
  clean) TAG=clean ;;
  drift|drifted) TAG=drifted ;;
  *) echo "usage: ./demo.sh clean|drift" >&2; exit 2 ;;
esac

git -C "$REPO" checkout --quiet "$TAG"
echo "orderflow is now at tag '$TAG' ($(git -C "$REPO" rev-parse --short HEAD))"
git -C "$REPO" --no-pager log -1 --format='  %s'
