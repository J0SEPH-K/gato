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
