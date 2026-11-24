#!/bin/bash
cd "$(dirname "$0")"
while true; do
  if ! curl -s -m 2 "http://127.0.0.1:8791/health?t=$(cat .tok)" >/dev/null 2>&1; then
    pkill -f 'server.py dd6506' 2>/dev/null
    python3 server.py dd6506aa855f92131d8cf7b7 8791 >> srv.log 2>&1 &
    sleep 3
  fi
  if ! pgrep -f 'ngrok http 8791' >/dev/null; then
    rm -f ng.log
    /opt/homebrew/bin/ngrok http 8791 --log stdout > ng.log 2>&1 &
    sleep 12
  fi
  sleep 20
done
