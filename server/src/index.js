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

async function handleAppear(req, env) {
  const body = await readJson(req);
  if (!body) return json({ ok: false }, 400);

  const id = String(body.id || '').trim().slice(0, 64);
  const token = String(body.token || '').trim().slice(0, 128);
  const kind = String(body.kind || '').trim().slice(0, 16);
  const wrong = body.wrong ? 1 : 0;
  if (!id || !token || (kind !== 'jochul' && kind !== 'jamun')) return json({ ok: false }, 400);

  // Same trust boundary as /heartbeat: a live bind token proves this is a real, authed client,
  // not a quota-abuse source. One indexed read, then one upsert (both cheap, D1 free tier).
  const bind = await env.DB.prepare('SELECT 1 FROM binds WHERE id = ? AND token = ?').bind(id, token).first();
  if (!bind) return json({ ok: false }, 403);

  const d = day(now());
  await env.DB.prepare(
    `INSERT INTO day_counts (id, day, kind, appeared, wrong) VALUES (?, ?, ?, 1, ?)
     ON CONFLICT (id, day, kind) DO UPDATE SET appeared = appeared + 1, wrong = wrong + excluded.wrong`
  ).bind(id, d, kind, wrong).run();
  return json({ ok: true });
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

  // Real accuracy across ALL customers (every round, not just the failures someone remembered to
  // zip up) - see day_counts in schema.sql. ?days=N limits the window (default 30).
  if (p === '/admin/accuracy' && req.method === 'GET') {
    const days = Math.max(1, Math.min(365, parseInt(url.searchParams.get('days') || '30', 10)));
    const since = day(now()) - days + 1;
    const overall = await env.DB.prepare(
      'SELECT kind, SUM(appeared) AS appeared, SUM(wrong) AS wrong FROM day_counts WHERE day >= ? GROUP BY kind'
    ).bind(since).all();
    const byId = await env.DB.prepare(
      'SELECT id, kind, SUM(appeared) AS appeared, SUM(wrong) AS wrong FROM day_counts WHERE day >= ? GROUP BY id, kind ORDER BY appeared DESC LIMIT 200'
    ).bind(since).all();
    return json({ ok: true, days, overall: overall.results || [], by_license: byId.results || [] });
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


// ---------------------------------------------------------------- relay (no tunnel needed)
// The client PC only makes OUTBOUND calls: POST /agent/poll every ~30 s (reports status, receives jobs) and
// POST /agent/up (uploads the file a job asked for, in <=700 KB chunks). Jobs are created by the owner only
// (/admin/job). A PC can only upload to a job id that was issued to it, and the id is an unguessable secret.

const CHUNK_MAX = 900 * 1024;            // one upload request
const JOB_MAX_BYTES = 160 * 1024 * 1024; // refuse silly sizes
const KEEP_SEC = 7 * 86400;

function rid(n = 12) {
  const b = crypto.getRandomValues(new Uint8Array(n));
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}

function safeEq(a, b) {
  if (!a || !b || a.length !== b.length) return false;
  let d = 0;
  for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}

// A PC proves itself either with a live licence bind token or with the shared relay key (so an
// unlicensed / not-yet-logged-in PC can still be seen and debugged).
async function relayAuth(env, o) {
  const k = String(o.k || '');
  if (env.RELAY_KEY && safeEq(k, env.RELAY_KEY)) return true;
  const id = String(o.id || ''), token = String(o.token || '');
  if (id && token) {
    const b = await env.DB.prepare('SELECT 1 FROM binds WHERE id = ? AND token = ?').bind(id, token).first();
    if (b) return true;
  }
  return false;
}

async function readBody(req, max) {
  try {
    const t = await req.text();
    if (!t || t.length > max) return null;
    const o = JSON.parse(t);
    return o && typeof o === 'object' ? o : null;
  } catch {
    return null;
  }
}

async function handlePoll(req, env) {
  const o = await readBody(req, 65536);
  if (!o) return json({ ok: false, reason: 'bad_request' }, 400);
  const machine = String(o.machine || '').trim().slice(0, 80);
  if (!machine) return json({ ok: false, reason: 'bad_request' }, 400);
  if (!(await relayAuth(env, o))) return json({ ok: false, reason: 'forbidden' }, 403);
  const t = now();
  const status = JSON.stringify(o.status || {}).slice(0, 12000);
  await env.DB.prepare(
    `INSERT INTO agents (machine, pc, ver, lic, seen, status) VALUES (?, ?, ?, ?, ?, ?)
     ON CONFLICT(machine) DO UPDATE SET
       pc = CASE WHEN excluded.pc != '' THEN excluded.pc ELSE agents.pc END,
       ver = CASE WHEN excluded.ver != '' THEN excluded.ver ELSE agents.ver END,
       lic = CASE WHEN excluded.lic != '' THEN excluded.lic ELSE agents.lic END,
       seen = excluded.seen, status = excluded.status`
  ).bind(machine, String(o.pc || '').slice(0, 60), String(o.ver || '').slice(0, 20), String(o.id || '').slice(0, 64), t, status).run();
  const rows = await env.DB.prepare(`SELECT id, cmd, arg FROM jobs WHERE machine = ? AND state = 'queued' ORDER BY created LIMIT 5`).bind(machine).all();
  const jobs = rows.results || [];
  for (const j of jobs) {
    await env.DB.prepare(`UPDATE jobs SET state = 'sent' WHERE id = ?`).bind(j.id).run();
  }
  if (Math.random() < 0.01) await purge(env);
  return json({ ok: true, jobs, t });
}

async function handleUp(req, env, url) {
  const job = url.searchParams.get('job') || '';
  const seq = parseInt(url.searchParams.get('seq') || '0', 10);
  const total = parseInt(url.searchParams.get('total') || '1', 10);
  const name = (url.searchParams.get('name') || '').slice(0, 120);
  if (!/^[0-9a-f]{16,40}$/.test(job) || !(seq >= 0) || !(total >= 1) || seq >= total) return json({ ok: false, reason: 'bad_request' }, 400);
  const row = await env.DB.prepare('SELECT machine, state, bytes FROM jobs WHERE id = ?').bind(job).first();
  if (!row || row.state === 'done' || row.state === 'queued') return json({ ok: false, reason: 'no_job' }, 404);
  const data = await req.arrayBuffer();
  if (!data.byteLength || data.byteLength > CHUNK_MAX) return json({ ok: false, reason: 'size' }, 413);
  if (row.bytes + data.byteLength > JOB_MAX_BYTES) return json({ ok: false, reason: 'too_big' }, 413);
  await env.DB.prepare('INSERT OR REPLACE INTO blobs (job, seq, data) VALUES (?, ?, ?)').bind(job, seq, data).run();
  const c = await env.DB.prepare('SELECT COUNT(*) AS n, COALESCE(SUM(LENGTH(data)), 0) AS b FROM blobs WHERE job = ?').bind(job).first();
  const complete = c.n >= total;
  await env.DB.prepare(
    `UPDATE jobs SET chunks = ?, total = ?, bytes = ?, name = CASE WHEN ? != '' THEN ? ELSE name END,
       state = CASE WHEN ? THEN 'done' ELSE state END, done = CASE WHEN ? THEN ? ELSE done END WHERE id = ?`
  ).bind(c.n, total, c.b, name, name, complete ? 1 : 0, complete ? 1 : 0, now(), job).run();
  return json({ ok: true, chunks: c.n, total, complete });
}

async function handleDone(req, env) {
  const o = await readBody(req, 16384);
  if (!o) return json({ ok: false, reason: 'bad_request' }, 400);
  const job = String(o.job || '');
  if (!/^[0-9a-f]{16,40}$/.test(job)) return json({ ok: false, reason: 'bad_request' }, 400);
  const row = await env.DB.prepare('SELECT state FROM jobs WHERE id = ?').bind(job).first();
  if (!row || row.state === 'queued') return json({ ok: false, reason: 'no_job' }, 404);
  await env.DB.prepare('UPDATE jobs SET state = ?, done = ?, result = ? WHERE id = ?')
    .bind(o.ok === false ? 'error' : 'done', now(), String(o.result || '').slice(0, 4000), job).run();
  return json({ ok: true });
}

// Failure zips the app already tries to post on its own (jochul rounds that went wrong).
async function handleDebugUpload(req, env, url) {
  const id = (url.searchParams.get('id') || '').slice(0, 64);
  const token = (url.searchParams.get('token') || '').slice(0, 128);
  const reason = (url.searchParams.get('reason') || '').slice(0, 80);
  if (!(await relayAuth(env, { id, token }))) return json({ ok: false, reason: 'forbidden' }, 403);
  const data = new Uint8Array(await req.arrayBuffer());
  if (!data.byteLength || data.byteLength > JOB_MAX_BYTES) return json({ ok: false, reason: 'size' }, 413);
  const job = rid(10);
  const n = Math.ceil(data.byteLength / CHUNK_MAX);
  const t = now();
  await env.DB.prepare(`INSERT INTO jobs (id, machine, cmd, arg, state, created, done, chunks, total, bytes, name) VALUES (?, ?, 'autodebug', ?, 'sent', ?, 0, 0, ?, ?, ?)`)
    .bind(job, 'lic:' + id, reason, t, n, data.byteLength, 'jochul_' + job + '.zip').run();
  for (let i = 0; i < n; i++) {
    await env.DB.prepare('INSERT INTO blobs (job, seq, data) VALUES (?, ?, ?)').bind(job, i, data.slice(i * CHUNK_MAX, (i + 1) * CHUNK_MAX).buffer).run();
  }
  await env.DB.prepare(`UPDATE jobs SET state = 'done', chunks = ?, done = ? WHERE id = ?`).bind(n, now(), job).run();
  return json({ ok: true, job });
}

async function purge(env) {
  const cut = now() - KEEP_SEC;
  await env.DB.prepare('DELETE FROM blobs WHERE job IN (SELECT id FROM jobs WHERE created < ?)').bind(cut).run();
  await env.DB.prepare('DELETE FROM jobs WHERE created < ?').bind(cut).run();
}

async function relayAdmin(req, env, url) {
  const p = url.pathname;
  if (p === '/admin/agents' && req.method === 'GET') {
    const r = await env.DB.prepare('SELECT machine, pc, ver, lic, seen, status FROM agents ORDER BY pc').all();
    const t = now();
    const rows = (r.results || []).map((a) => {
      let st = {};
      try { st = JSON.parse(a.status || '{}'); } catch { /* keep {} */ }
      return { machine: a.machine, pc: a.pc, ver: a.ver, lic: a.lic, age: t - a.seen, status: st };
    });
    return json({ ok: true, rows });
  }
  if (p === '/admin/job' && req.method === 'POST') {
    const o = await readBody(req, 8192);
    if (!o) return json({ ok: false, reason: 'bad_request' }, 400);
    const cmd = String(o.cmd || '');
    if (!['log', 'shot', 'ls', 'pull', 'stop', 'dump', 'start', 'update', 'relaunch', 'restart'].includes(cmd)) return json({ ok: false, reason: 'bad_cmd' }, 400);
    let machine = String(o.machine || '');
    if (!machine && o.pc) {
      const a = await env.DB.prepare('SELECT machine FROM agents WHERE pc = ? ORDER BY seen DESC LIMIT 1').bind(String(o.pc)).first();
      machine = a ? a.machine : '';
    }
    if (!machine) return json({ ok: false, reason: 'unknown_pc' }, 404);
    const id = rid(10);
    await env.DB.prepare(`INSERT INTO jobs (id, machine, cmd, arg, state, created) VALUES (?, ?, ?, ?, 'queued', ?)`)
      .bind(id, machine, cmd, String(o.arg || '').slice(0, 300), now()).run();
    return json({ ok: true, job: id, machine });
  }
  if (p === '/admin/job' && req.method === 'GET') {
    const row = await env.DB.prepare('SELECT * FROM jobs WHERE id = ?').bind(url.searchParams.get('id') || '').first();
    return row ? json({ ok: true, job: row }) : json({ ok: false, reason: 'no_job' }, 404);
  }
  if (p === '/admin/jobs' && req.method === 'GET') {
    const r = await env.DB.prepare('SELECT id, machine, cmd, arg, state, created, bytes, name, result FROM jobs ORDER BY created DESC LIMIT 30').all();
    return json({ ok: true, rows: r.results || [] });
  }
  if (p === '/admin/blob' && req.method === 'GET') {
    const id = url.searchParams.get('job') || '';
    const row = await env.DB.prepare('SELECT state, total, name FROM jobs WHERE id = ?').bind(id).first();
    if (!row) return json({ ok: false, reason: 'no_job' }, 404);
    let i = 0;
    const stream = new ReadableStream({
      async pull(ctrl) {
        if (i >= row.total) { ctrl.close(); return; }
        const c = await env.DB.prepare('SELECT data FROM blobs WHERE job = ? AND seq = ?').bind(id, i).first();
        if (!c) { ctrl.error(new Error('missing chunk ' + i)); return; }
        ctrl.enqueue(new Uint8Array(c.data));
        i++;
      },
    });
    return new Response(stream, { headers: { 'content-type': 'application/octet-stream', 'x-job-state': row.state, 'x-name': encodeURIComponent(row.name || id) } });
  }
  if (p === '/admin/purge' && req.method === 'POST') {
    await purge(env);
    return json({ ok: true });
  }
  return null;
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
        const ra = await relayAdmin(req, env, url);
        if (ra) return ra;
        return await admin(req, env, url);
      }
      if (p === '/auth' && req.method === 'POST') return await handleAuth(req, env);
      if (p === '/heartbeat' && req.method === 'POST') return await handleHeartbeat(req, env);
      if (p === '/appear' && req.method === 'POST') return await handleAppear(req, env);
      if (p === '/agent/poll' && req.method === 'POST') return await handlePoll(req, env);
      if (p === '/agent/up' && req.method === 'POST') return await handleUp(req, env, url);
      if (p === '/agent/done' && req.method === 'POST') return await handleDone(req, env);
      if (p === '/debug/jochul' && req.method === 'POST') return await handleDebugUpload(req, env, url);
      if (p === '/health') return json({ ok: true, t: now() });
      return json({ ok: false, reason: 'not_found' }, 404);
    } catch (e) {
      return json({ ok: false, reason: 'server', detail: String(e).slice(0, 200) }, 500);
    }
  },
};
