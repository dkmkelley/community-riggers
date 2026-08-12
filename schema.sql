CREATE TABLE IF NOT EXISTS riggers (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    phone           TEXT NOT NULL,
    affiliation     TEXT,
    city            TEXT,
    token           TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',
    sms_consent     INTEGER NOT NULL DEFAULT 0,
    last_toggled_at TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_riggers_token ON riggers(token);

CREATE TABLE IF NOT EXISTS availability (
    id          INTEGER PRIMARY KEY,
    rigger_id   INTEGER NOT NULL,
    date        TEXT NOT NULL,
    FOREIGN KEY (rigger_id) REFERENCES riggers(id) ON DELETE CASCADE,
    UNIQUE(rigger_id, date)
);