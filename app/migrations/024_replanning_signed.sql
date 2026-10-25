-- إعادة التخطيط بمراجعات محفوظة لخط الأساس (الدستور، البند 4.5)، والمصاريف غير المباشرة اليومية للمشروع،
-- والنسخ الورقية الموقّعة لأوامر الشراء وعقود الباطن والمستخلصات والفواتير (قرار م. محمد 2026-10-25).
ALTER TABLE projects ADD COLUMN daily_overhead INTEGER NOT NULL DEFAULT 0;
ALTER TABLE projects ADD COLUMN replan_reason TEXT;
ALTER TABLE projects ADD COLUMN replan_cr_id INTEGER REFERENCES change_requests(id);

CREATE TABLE baselines (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rev          INTEGER NOT NULL,
    code         TEXT NOT NULL UNIQUE,                    -- P-2026-001-BL-R00 (الأصل)، ثم R01، R02
    reason       TEXT,
    cr_id        INTEGER REFERENCES change_requests(id),
    finish       TEXT,
    budget       INTEGER NOT NULL DEFAULT 0,
    data         TEXT NOT NULL,                           -- JSON: الأنشطة بتواريخها المخططة، والبنود بميزانياتها
    approved_at  TEXT NOT NULL,
    approved_by  INTEGER NOT NULL REFERENCES users(id),
    UNIQUE (project_id, rev)
);

CREATE TABLE signed_copies (
    id              INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    doc_kind        TEXT NOT NULL CHECK (doc_kind IN ('commitment','payable')),
    doc_id          INTEGER NOT NULL,
    rev             INTEGER NOT NULL,
    file_name       TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    storage_key     TEXT NOT NULL,
    needs_director  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'review' CHECK (status IN ('review','cc_ok','accepted','returned')),
    uploaded_at     TEXT NOT NULL,
    uploaded_by     INTEGER NOT NULL REFERENCES users(id),
    cc_at           TEXT,
    cc_by           INTEGER REFERENCES users(id),
    dir_at          TEXT,
    dir_by          INTEGER REFERENCES users(id),
    return_reason   TEXT,
    UNIQUE (doc_kind, doc_id, rev)
);
CREATE INDEX signed_copies_doc ON signed_copies(doc_kind, doc_id);
