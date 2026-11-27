#!/bin/bash
cd "$(dirname "$0")"
# The token MUST equal the PC agent's link token (agent_link.DEFAULT_TOKEN), else every
# PC poll answers {"error":"bad token"} and the queue starves forever.
T=$(cat .tok)
while true; do
  if ! curl -s -m 2 "http://127.0.0.1:8791/health?t=$T" >/dev/null 2>&1; then
    pkill -f 'server.py .* 8791' 2>/dev/null
    python3 server.py "$T" 8791 >> srv.log 2>&1 &
    sleep 3
  fi
  if ! pgrep -f 'ngrok http 8791' >/dev/null; then
    rm -f ng.log
    /opt/homebrew/bin/ngrok http 8791 --log stdout > ng.log 2>&1 &
    sleep 12
  fi
  sleep 20
done
