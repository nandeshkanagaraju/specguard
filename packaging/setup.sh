#!/usr/bin/env bash
# One-time setup. Creates a virtualenv, installs SpecGuard, and builds the
# demo fixture's two commits.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "SpecGuard setup"
echo "==============="

# --- find a usable Python -------------------------------------------------
PY=""
for c in python3.13 python3.12 python3.11 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo
  echo "  Python 3.11 or newer is required and was not found."
  echo "  macOS:   brew install python@3.11"
  echo "  Ubuntu:  sudo apt install python3.11 python3.11-venv"
  echo "  Windows: install from python.org, then run setup.ps1 instead"
  exit 1
fi
echo "  python: $($PY --version) at $(command -v $PY)"

# --- install --------------------------------------------------------------
echo "  creating .venv…"
"$PY" -m venv .venv
./.venv/bin/python -m pip install --quiet --upgrade pip
echo "  installing SpecGuard…"
./.venv/bin/python -m pip install --quiet ./specguard-0.1.0-py3-none-any.whl
# pytest is not a SpecGuard dependency; the demo needs it to make the point that
# the fixture's own tests stay green on both commits.
./.venv/bin/python -m pip install --quiet pytest
echo "  installed: $(./.venv/bin/specguard --help >/dev/null 2>&1 && echo ok || echo FAILED)"

# --- build the demo fixture's git history ---------------------------------
if [ -d demo/orderflow ]; then
  echo "  building the demo fixture…"
  rm -rf demo/orderflow/.git demo/orderflow/.specguard
  cp demo/_variants/clean/orderflow/*.py demo/orderflow/orderflow/
  git -C demo/orderflow init -q -b main
  git -C demo/orderflow config user.email "team@orderflow.example"
  git -C demo/orderflow config user.name "OrderFlow Team"
  git -C demo/orderflow add -A
  git -C demo/orderflow commit -q -m "OrderFlow: pricing, shipping, inventory and checkout per SPEC.md"
  git -C demo/orderflow tag clean

  cp demo/_variants/drifted/orderflow/*.py demo/orderflow/orderflow/
  git -C demo/orderflow add -A
  git -C demo/orderflow commit -q -m "Tidy checkout, simplify validation, adjust free-shipping check"
  git -C demo/orderflow tag drifted
  git -C demo/orderflow checkout -q clean
  echo "  fixture ready: tags 'clean' and 'drifted'"
fi

cat <<'DONE'

Done. Try this:

  ./demo.sh drift                       # a week of development happened
  cd demo/orderflow && ../../.venv/bin/python -m pytest -q && cd ../..
                                        # 15 passed — the tests are still green
  ./run.sh check demo/orderflow         # …and 3 rules have drifted anyway

  ./run.sh serve demo/orderflow         # the dashboard, at http://127.0.0.1:8000

To use it on your own project, see INSTALL.md.
DONE
