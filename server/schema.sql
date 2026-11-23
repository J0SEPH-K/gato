-- GATO license D1 schema. Apply once:  wrangler d1 execute gato --remote --file schema.sql

CREATE TABLE IF NOT EXISTS licenses (
  id      TEXT PRIMARY KEY,          -- the licence key the buyer types into the app
  pcs     INTEGER NOT NULL DEFAULT 1, -- how many machines the key may bind
  expiry  INTEGER,                    -- epoch DAYS, NULL = never expires
  revoked INTEGER NOT NULL DEFAULT 0,
  note    TEXT NOT NULL DEFAULT '',
  gen     INTEGER NOT NULL DEFAULT 1, -- bumped on kick, invalidates old tokens
  token   TEXT,                       -- legacy; live tokens now live on binds
  created INTEGER NOT NULL DEFAULT 0,
  seen    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS binds (
  id    TEXT NOT NULL,
  hwid  TEXT NOT NULL,
  seen  INTEGER NOT NULL DEFAULT 0,
  token TEXT,                         -- live session token for this (key, PC)
  PRIMARY KEY (id, hwid)
);

CREATE INDEX IF NOT EXISTS idx_binds_id ON binds (id);

CREATE TABLE IF NOT EXISTS config (
  k      INTEGER PRIMARY KEY,
  min_ver TEXT NOT NULL DEFAULT '0.0.0',
  notice TEXT NOT NULL DEFAULT ''
);

INSERT OR IGNORE INTO config (k, min_ver, notice) VALUES (1, '0.0.0', '');

-- Real-world accuracy telemetry. The client fires POST /appear on EVERY 조철/자방문 round
-- (not just failures - debug/jochul_fail only ever captures failures, which is a worst-case
-- sample with no denominator). One row per (license, day, kind); day_counts bumps appeared/wrong
-- on every call so SELECT SUM(wrong)*1.0/SUM(appeared) gives a real accuracy number across all
-- customers instead of guessing from a handful of manually-sent failure zips.
CREATE TABLE IF NOT EXISTS day_counts (
  id       TEXT NOT NULL,              -- license id
  day      INTEGER NOT NULL,           -- epoch day (UTC)
  kind     TEXT NOT NULL,              -- 'jochul' | 'jamun'
  appeared INTEGER NOT NULL DEFAULT 0,
  wrong    INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (id, day, kind)
);


-- ---- Relay: lets the owner see every client PC and pull debug files WITHOUT any tunnel.
-- The PC only makes OUTBOUND https calls to this Worker (poll every 30 s), so NAT, a shared home IP,
-- Cloudflare quick-tunnel 429s and the ngrok 3-agent cap cannot cut it off.
CREATE TABLE IF NOT EXISTS agents (
  machine TEXT PRIMARY KEY,           -- MachineGuid of the PC
  pc      TEXT NOT NULL DEFAULT '',
  ver     TEXT NOT NULL DEFAULT '',
  lic     TEXT NOT NULL DEFAULT '',
  seen    INTEGER NOT NULL DEFAULT 0,
  status  TEXT NOT NULL DEFAULT ''    -- JSON: running, battles, scene, monster, last log lines...
);

CREATE TABLE IF NOT EXISTS jobs (
  id      TEXT PRIMARY KEY,
  machine TEXT NOT NULL,              -- target PC, or 'lic:<key>' for automatic failure uploads
  cmd     TEXT NOT NULL,              -- log | shot | ls | pull | stop | autodebug
  arg     TEXT NOT NULL DEFAULT '',
  state   TEXT NOT NULL DEFAULT 'queued', -- queued | sent | done | error
  created INTEGER NOT NULL DEFAULT 0,
  done    INTEGER NOT NULL DEFAULT 0,
  result  TEXT NOT NULL DEFAULT '',
  chunks  INTEGER NOT NULL DEFAULT 0,
  total   INTEGER NOT NULL DEFAULT 0,
  bytes   INTEGER NOT NULL DEFAULT 0,
  name    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_machine ON jobs (machine, state);

CREATE TABLE IF NOT EXISTS blobs (
  job  TEXT NOT NULL,
  seq  INTEGER NOT NULL,
  data BLOB NOT NULL,
  PRIMARY KEY (job, seq)
);
