/**
 * GATO license server — Cloudflare Worker + D1.
 *
 * Free tier: 100k requests/day, 5M D1 row reads/day. A client heartbeat is one
 * indexed SELECT (60 s cadence), so ~70 concurrent users fit inside the quota.
 * A D1 write happens only on state change (first auth, kick, revoke), never on
 * a plain heartbeat.
 *
 * Endpoints used by the client (net.py):
 *   POST /auth      {id, hwid, ver, code_ver}  -> {ok, token, expiry, days_left, min_ver, notice}
 *   POST /heartbeat {id, token, hwid, ver}     -> {ok, reason?, min_ver?, notice?}
 *
 * Admin endpoints (Bearer ADMIN_KEY):
 *   POST /admin/issue   {id, days, pcs, note}   -> creates/extends a license
 *   POST /admin/revoke  {id, reason}
 *   POST /admin/kick    {id}                    -> forces re-auth on every PC
 *   POST /admin/unbind  {id, hwid}              -> frees a slot
 *   POST /admin/minver  {version}               -> raises the forced-update floor
 *   GET  /admin/list
 *   GET  /admin/license?id=..
 */

const enc = new TextEncoder();

// ---------------------------------------------------------------- helpers

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}

function now() {
  return Math.floor(Date.now() / 1000);
}

function day(ts) {
  return Math.floor(ts / 86400);
}

async function hmac(secret, msg) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(msg));
  return btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function b64u(buf) {
  return btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function cmpVer(a, b) {
  const key = (v) => {
    const p = String(v).replace(/^v/i, '').replace(/-/g, '.').split('.');
    while (p.length < 3) p.push('0');
    return p.slice(0, 3).map((x) => (parseInt(x, 10) || 0));
  };
  const ka = key(a), kb = key(b);
  for (let i = 0; i < 3; i++) {
    if (ka[i] !== kb[i]) return ka[i] < kb[i] ? -1 : 1;
  }
  return 0;
}

async function readJson(req) {
  try {
    const t = await req.text();
    if (!t || t.length > 8192) return null;
    const o = JSON.parse(t);
    return o && typeof o === 'object' ? o : null;
  } catch {
    return null;
  }
}

function bearer(req) {
  const h = req.headers.get('authorization') || '';
  return h.startsWith('Bearer ') ? h.slice(7) : '';
}

async function isAdmin(req, env) {
  const got = bearer(req);
  if (!got || !env.ADMIN_KEY) return false;
  // constant-time-ish compare
  if (got.length !== env.ADMIN_KEY.length) return false;
  let diff = 0;
  for (let i = 0; i < got.length; i++) diff |= got.charCodeAt(i) ^ env.ADMIN_KEY.charCodeAt(i);
  return diff === 0;
}

// ---------------------------------------------------------------- config row

async function config(env) {
  const row = await env.DB.prepare('SELECT min_ver, notice FROM config WHERE k = 1').first();
  return row || { min_ver: '0.0.0', notice: '' };
}

// ---------------------------------------------------------------- handlers

async function handleAuth(req, env) {
  const body = await readJson(req);
  if (!body) return json({ ok: false, reason: 'bad_request' }, 400);

  const id = String(body.id || '').trim().slice(0, 64);
  const hwid = String(body.hwid || '').trim().slice(0, 64);
  const ver = String(body.ver || '').trim().slice(0, 24);
  if (!id) return json({ ok: false, reason: 'denied' });

  const cfg = await config(env);
  if (ver && cmpVer(ver, cfg.min_ver) < 0) {
    return json({ ok: false, reason: 'outdated', min_ver: cfg.min_ver, notice: cfg.notice });
  }

  const lic = await env.DB.prepare('SELECT * FROM licenses WHERE id = ?').bind(id).first();
  if (!lic) return json({ ok: false, reason: 'unknown' });
  if (lic.revoked) return json({ ok: false, reason: 'revoked' });
  if (lic.expiry && lic.expiry < day(now())) return json({ ok: false, reason: 'expired' });

  const slots = await env.DB.prepare('SELECT hwid FROM binds WHERE id = ?').bind(id).all();
  const bound = (slots.results || []).map((r) => r.hwid);
  const known = bound.includes(hwid);

  if (!known) {
    if (bound.length >= (lic.pcs || 1)) {
      return json({ ok: false, reason: 'limit', pcs: lic.pcs, bound: bound.length });
    }
  }

  // Token is per (license, PC) so a 2-PC license can keep both machines online.
  const token = await hmac(env.TOKEN_SECRET, `${id}|${hwid}|${lic.gen}|${now()}`);
  await env.DB.prepare('INSERT OR REPLACE INTO binds (id, hwid, seen, token) VALUES (?, ?, ?, ?)')
    .bind(id, hwid, now(), token).run();
  await env.DB.prepare('UPDATE licenses SET seen = ? WHERE id = ?').bind(now(), id).run();

  const daysLeft = lic.expiry ? Math.max(0, lic.expiry - day(now())) : null;
  return json({
    ok: true,
    token,
    expiry: lic.expiry ? new Date(lic.expiry * 86400000).toISOString().slice(0, 10) : '',
    days_left: daysLeft,
    min_ver: cfg.min_ver,
    notice: cfg.notice,
    pcs: lic.pcs,
  });
}

async function handleHeartbeat(req, env) {
  const body = await readJson(req);
  if (!body) return json({ ok: false, reason: 'bad_request' }, 400);

  const id = String(body.id || '').trim().slice(0, 64);
  const token = String(body.token || '').trim().slice(0, 128);
  const hwid = String(body.hwid || '').trim().slice(0, 64);
  const ver = String(body.ver || '').trim().slice(0, 24);

  const cfg = await config(env);
  if (ver && cmpVer(ver, cfg.min_ver) < 0) {
    return json({ ok: false, reason: 'outdated', min_ver: cfg.min_ver, notice: cfg.notice });
  }

  const lic = await env.DB.prepare('SELECT revoked, expiry, gen, token, pcs FROM licenses WHERE id = ?').bind(id).first();
  if (!lic) return json({ ok: false, reason: 'denied' });
  if (lic.revoked) return json({ ok: false, reason: 'revoked' });
  if (lic.expiry && lic.expiry < day(now())) return json({ ok: false, reason: 'expired' });

  // Cheap: this is the whole steady-state cost. One indexed read, no write.
  const bind = await env.DB.prepare('SELECT hwid, token FROM binds WHERE id = ? AND hwid = ?').bind(id, hwid).first();
  if (!bind) return json({ ok: false, reason: 'limit' });
  if (!bind.token || bind.token !== token) return json({ ok: false, reason: 'kicked' });

  const daysLeft = lic.expiry ? Math.max(0, lic.expiry - day(now())) : null;
  return json({ ok: true, days_left: daysLeft, min_ver: cfg.min_ver, notice: cfg.notice });
}

// ---------------------------------------------------------------- admin

async function admin(req, env, url) {
  const p = url.pathname;

  if (p === '/admin/list' && req.method === 'GET') {
    const r = await env.DB.prepare(
      'SELECT l.id, l.pcs, l.expiry, l.revoked, l.note, l.seen, (SELECT COUNT(*) FROM binds b WHERE b.id = l.id) AS bound FROM licenses l ORDER BY l.seen DESC LIMIT 500'
    ).all();
    return json({ ok: true, rows: r.results || [] });
  }

  if (p === '/admin/license' && req.method === 'GET') {
    const id = url.searchParams.get('id') || '';
    const lic = await env.DB.prepare('SELECT * FROM licenses WHERE id = ?').bind(id).first();
    if (!lic) return json({ ok: false, reason: 'denied' }, 404);
    const b = await env.DB.prepare('SELECT hwid, seen FROM binds WHERE id = ?').bind(id).all();
    return json({ ok: true, license: lic, binds: b.results || [] });
  }

  const body = await readJson(req);
  if (!body) return json({ ok: false, reason: 'bad_request' }, 400);
  const id = String(body.id || '').trim().slice(0, 64);

  if (p === '/admin/issue') {
    // No id given -> mint one (GATO-XXXX-XXXX). Admin may also pass an id.
    let lid = id;
    if (!lid) {
      const ab = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
      const rnd = crypto.getRandomValues(new Uint8Array(8));
      const s = Array.from(rnd, (b) => ab[b % ab.length]).join('');
      lid = `GATO-${s.slice(0, 4)}-${s.slice(4, 8)}`;
    }
    const days = Math.max(-36500, Math.min(36500, parseInt(body.days, 10) || 0));
    const pcs = Math.max(1, Math.min(10, parseInt(body.pcs, 10) || 1));
    const expiry = days ? day(now()) + days : null;
    await env.DB.prepare(
      `INSERT INTO licenses (id, pcs, expiry, revoked, note, gen, created, seen) VALUES (?, ?, ?, 0, ?, 1, ?, 0)
       ON CONFLICT(id) DO UPDATE SET pcs = excluded.pcs, expiry = excluded.expiry, revoked = 0, note = excluded.note`
    ).bind(lid, pcs, expiry, String(body.note || '').slice(0, 200), now()).run();
    return json({ ok: true, id: lid, expiry });
  }

  const lic = await env.DB.prepare('SELECT gen FROM licenses WHERE id = ?').bind(id).first();
  if (!lic && p !== '/admin/minver' && p !== '/admin/notice') return json({ ok: false, reason: 'denied' }, 404);

  if (p === '/admin/revoke') {
    await env.DB.prepare('UPDATE licenses SET revoked = 1 WHERE id = ?').bind(id).run();
    await env.DB.prepare('UPDATE binds SET token = NULL WHERE id = ?').bind(id).run();
    return json({ ok: true });
  }

  if (p === '/admin/kick') {
    await env.DB.prepare('UPDATE licenses SET gen = gen + 1 WHERE id = ?').bind(id).run();
    await env.DB.prepare('UPDATE binds SET token = NULL WHERE id = ?').bind(id).run();
    return json({ ok: true });
  }

  if (p === '/admin/unbind') {
    const hwid = String(body.hwid || '').trim().slice(0, 64);
    await env.DB.prepare('DELETE FROM binds WHERE id = ? AND hwid = ?').bind(id, hwid).run();
    return json({ ok: true });
  }

  // Upserts, so they work even on a DB where the config row was never seeded.
  if (p === '/admin/minver') {
    const v = String(body.version || body.ver || '0.0.0').slice(0, 24);
    await env.DB.prepare(
      "INSERT INTO config (k, min_ver, notice) VALUES (1, ?, '') ON CONFLICT(k) DO UPDATE SET min_ver = excluded.min_ver"
    ).bind(v).run();
    return json({ ok: true, min_ver: v });
  }

  if (p === '/admin/notice') {
    const n = String(body.notice || body.text || '').slice(0, 400);
    await env.DB.prepare(
      "INSERT INTO config (k, min_ver, notice) VALUES (1, '0.0.0', ?) ON CONFLICT(k) DO UPDATE SET notice = excluded.notice"
    ).bind(n).run();
    return json({ ok: true, notice: n });
  }

  return json({ ok: false, reason: 'not_found' }, 404);
}

// ---------------------------------------------------------------- entry

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;

    if (req.method === 'OPTIONS') return new Response(null, { status: 204 });

    try {
      if (p.startsWith('/admin/')) {
        if (!(await isAdmin(req, env))) return json({ ok: false, reason: 'forbidden' }, 403);
        return await admin(req, env, url);
      }
      if (p === '/auth' && req.method === 'POST') return await handleAuth(req, env);
      if (p === '/heartbeat' && req.method === 'POST') return await handleHeartbeat(req, env);
      if (p === '/health') return json({ ok: true, t: now() });
      return json({ ok: false, reason: 'not_found' }, 404);
    } catch (e) {
      return json({ ok: false, reason: 'server', detail: String(e).slice(0, 200) }, 500);
    }
  },
};
