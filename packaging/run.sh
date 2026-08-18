#!/usr/bin/env bash
# Thin wrapper so you don't have to activate the virtualenv.
#   ./run.sh check demo/orderflow
#   ./run.sh serve demo/orderflow
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec ./.venv/bin/specguard "$@"
