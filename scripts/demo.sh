#!/usr/bin/env bash
# Switch the demo fixture between its clean and drifted commits.
#
#   ./scripts/demo.sh clean    the code matches the spec
#   ./scripts/demo.sh drift    a normal week of development happened
#
# The presenter never types a git command on stage.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$HERE/samples/orderflow"

case "${1:-}" in
  clean) TAG=clean ;;
  drift|drifted) TAG=drifted ;;
  *) echo "usage: demo.sh clean|drift" >&2; exit 2 ;;
esac

git -C "$REPO" checkout --quiet "$TAG"
echo "orderflow is now at tag '$TAG' ($(git -C "$REPO" rev-parse --short HEAD))"
git -C "$REPO" --no-pager log -1 --format='  %s'
