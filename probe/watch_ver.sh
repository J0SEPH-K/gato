#!/bin/sh
# Poll the relay until the client leaves 1.0.28, then stop. Used while the
# updater's own 6-hour timer counts down to the 1.0.30 release.
cd "$(dirname "$0")/.." || exit 1
for i in $(seq 1 90); do
  line=$(python3 tools/relay_cli.py agents 2>/dev/null | grep -E '^qwer ' || true)
  echo "$(date '+%T') $line"
  case "$line" in
    *v1.0.28*) sleep 40 ;;
    *v1.0.29*|*v1.0.30*|*v1.0.31*) echo "UPDATED: $line"; exit 0 ;;
    *) echo "qwer missing from relay"; sleep 40 ;;
  esac
done
echo TIMEOUT
