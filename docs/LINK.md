# Always-on link from every installed GATO to the Mac

Purpose: no more RustDesk and no more tunnel windows opened by hand. Every install, on every launch,
opens a small HTTP API on localhost, exposes it with a downloaded cloudflared quick tunnel, and
announces itself to a fixed ntfy topic. The Mac polls that topic and can talk to every PC at once.

## On the PC (automatic, in the app)
`agent_link.install(api)` is called at the end of `Api.__init__`; `api.link.close()` on close.
- binds 127.0.0.1:8787 (next free port if taken, so two instances on one PC both work)
- downloads cloudflared once into `%LOCALAPPDATA%\GATO\bin`, runs `tunnel --url`, reads the
  `trycloudflare.com` URL from its output, restarts it if it dies
- ngrok is only the fallback: the free account allows 3 simultaneous agents (ERR_NGROK_108)
- announces `{pc, machine, url, ver, ts}` to ntfy every 25 s (and immediately on a new URL)
- API (all need header `x-gato-token`): GET /status, /log?since=<bytes>, /shot, /ping; POST /cmd
- settings: `link_enabled`, `link_topic`, `link_token`, `ngrok_authtoken` (defaults are baked in)

## On the Mac
    python3 tools/hub.py list          # every PC that announced in the last 150 s, with live status
    python3 tools/hub.py watch         # keep polling, print UP/DOWN as PCs appear and drop
    python3 tools/hub.py log   <pc> -n 100
    python3 tools/hub.py shot  <pc> /tmp/x.jpg
    python3 tools/hub.py cmd   <pc> stop|start
`<pc>` is the hostname, the machine id, or any unique prefix of the hostname.

## Tests
`python3 dev/mock/run_link_test.py` - token gate, all endpoints, log offset fallback, hub
bookkeeping (two PCs at once, staleness drop, picking by id/prefix).
End-to-end on this Mac with two fake instances: both got their own port and their own tunnel,
both appeared in the hub, status/shot/cmd worked on each.
