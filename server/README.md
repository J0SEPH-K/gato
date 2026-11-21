# GATO license server (Cloudflare Worker + D1)

Live: https://gato-license.gigan.workers.dev

A copy cannot start unless the key is known, unrevoked, unexpired, inside its
PC slot count, and at or above the forced-update floor. Zero running cost on
the Workers free tier (100k requests/day; a 60 s heartbeat per client puts that
at ~70 concurrent users before the $5/mo plan).

## Layout

- `src/index.js` — the Worker. `/auth` and `/heartbeat` for clients, `/admin/*` for me.
- `schema.sql` — `licenses`, `binds` (one row per licensed PC), `config`.
- `devtest.py` — end-to-end assertions against a local `wrangler dev`.
- `../dev/test_license_client.py` — same, through the real client (`net.AuthClient`).

## Admin commands

`$K` is the `ADMIN_KEY` secret. All admin calls are `POST` with
`authorization: Bearer $K` and a JSON body.

```sh
# sell: mint a key (id is generated), 1 PC, lifetime
docker() { :; }
curl -s -X POST $URL/admin/issue -H "authorization: Bearer $K" \
     -d '{"pcs":1,"days":0,"note":"buyer handle"}'

# sell: 365 days, 2 PCs
curl -s -X POST $URL/admin/issue -H "authorization: Bearer $K" \
     -d '{"pcs":2,"days":365,"note":"buyer handle"}'

# list everything with how many PCs are bound
curl -s $URL/admin/list -H "authorization: Bearer $K"

# one license + its bound hardware ids
curl -s "$URL/admin/license?id=GATO-XXXX-XXXX" -H "authorization: Bearer $K"

# force every build below 1.0.20 to update before it may start
curl -s -X POST $URL/admin/minver -H "authorization: Bearer $K" -d '{"version":"1.0.20"}'

# in-app banner for everyone
curl -s -X POST $URL/admin/notice -H "authorization: Bearer $K" -d '{"text":"점검 안내"}'

# refund / ban, and free one PC slot
curl -s -X POST $URL/admin/revoke -H "authorization: Bearer $K" -d '{"id":"GATO-XXXX-XXXX"}'
curl -s -X POST $URL/admin/unbind -H "authorization: Bearer $K" -d '{"id":"GATO-XXXX-XXXX","hwid":"..."}'

# drop a live session (key stays valid)
curl -s -X POST $URL/admin/kick -H "authorization: Bearer $K" -d '{"id":"GATO-XXXX-XXXX"}'
```

`days: 0` = lifetime. Negative days is allowed, for testing expiry.

## Rebuild after a change

```sh
cd server && npx wrangler deploy
```

Secrets (`ADMIN_KEY`, `TOKEN_SECRET`) live in `.secrets.txt` locally and in the
Worker; they are not in git.
