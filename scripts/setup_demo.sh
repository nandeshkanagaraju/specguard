#!/usr/bin/env bash
# Put the demo into its correct starting state and start the dashboard.
#
# Leaves you with:
#   - the fixture on its `clean` commit
#   - one prior clean run, so the dashboard opens all-green at drift score 0.00
#   - the clean verdicts cached, the drifted ones NOT — so `Run check` visibly
#     animates during the demo instead of finishing instantly
#   - the dashboard serving on :8000
#
# Safe to re-run between rehearsals.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

PORT="${1:-8000}"
SG=".venv/bin/specguard"
FIXTURE="samples/orderflow"

[ -x "$SG" ] || { echo "No venv — run 'make install' first." >&2; exit 1; }
[ -d "$FIXTURE/.git" ] || { echo "No fixture history — run 'scripts/build_fixture.sh'." >&2; exit 1; }

echo "SpecGuard demo setup"
echo "===================="

echo "  stopping any running dashboard…"
pkill -f "specguard serve" 2>/dev/null || true
sleep 1

echo "  resetting the fixture to 'clean'…"
git -C "$FIXTURE" checkout --quiet clean
rm -rf "$FIXTURE/.specguard"

echo "  running the clean baseline…"
"$SG" check "$FIXTURE" --quiet >/dev/null 2>&1 || true
SUMMARY="$(.venv/bin/python - <<'PY'
import json
s = json.load(open("samples/orderflow/.specguard/report.json"))["summary"]
print(f"{s['aligned']} aligned, {s['drifted']} drifted, drift score {s['drift_score']:.2f}")
PY
)"
echo "    -> $SUMMARY"

echo "  starting the dashboard on :${PORT}..."
nohup "$SG" serve "$FIXTURE" --port "$PORT" > /tmp/specguard-demo.log 2>&1 &
for _ in $(seq 1 20); do
  curl -s --max-time 1 -o /dev/null "http://127.0.0.1:$PORT/" && break
  sleep 0.5
done

if curl -s --max-time 2 -o /dev/null "http://127.0.0.1:$PORT/"; then
  echo "    -> http://127.0.0.1:$PORT"
else
  echo "    -> FAILED to start; see /tmp/specguard-demo.log" >&2
  exit 1
fi

cat <<DONE

Ready. Open http://127.0.0.1:$PORT — every tick should be teal, drift score 0.00.

The run (full script in DEMO.md):
  1. show $FIXTURE/SPEC.md          "every project starts with a spec"
  2. show the dashboard, all green   "here's the code today"
  3. ./scripts/demo.sh drift         "now a normal week of development"
  4. cd $FIXTURE && pytest -q        "and the tests still pass"   <- pause
  5. click Run check                 ribbon repaints, 3 red + 1 violet
  6. click R-004                     the boundary, with cited lines
  7. click R-009                     the two passes disagreed
  8. click Run check again           identical verdicts, cached chips

Stop the dashboard with: pkill -f "specguard serve"
DONE
