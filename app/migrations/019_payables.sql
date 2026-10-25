-- مستخلصات مقاولي الباطن وفواتير الموردين ومحاضر الاستلام (الدستور، البند 4.7)، ومستخلصات الشركة للمالك (البند 4.8).
-- المبالغ بالهللة، والكميات بالألف، والنسب بأجزاء من عشرة آلاف.
CREATE TABLE goods_receipts (
    id             INTEGER PRIMARY KEY,
    project_id     INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code           TEXT NOT NULL UNIQUE,                  -- P-2026-001-GRN-0001
    commitment_id  INTEGER NOT NULL REFERENCES commitments(id),
    received_on    TEXT NOT NULL,
    qty_milli      BIGINT NOT NULL CHECK (qty_milli > 0),
    notes          TEXT,
    created_at     TEXT NOT NULL,
    created_by     INTEGER NOT NULL REFERENCES users(id)
);

CREATE TABLE payables (
    id              INTEGER PRIMARY KEY,
    project_id      INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code            TEXT NOT NULL UNIQUE,                 -- P-2026-001-SPC-001 أو P-2026-001-INV-0001
    commitment_id   INTEGER NOT NULL REFERENCES commitments(id),
    kind            TEXT NOT NULL CHECK (kind IN ('certificate','invoice')),
    period_from     TEXT,
    period_to       TEXT,
    vendor_ref      TEXT,
    qty_milli       BIGINT NOT NULL CHECK (qty_milli > 0),
    gross           BIGINT NOT NULL,
    retention_bp    INTEGER NOT NULL DEFAULT 0,
    retention       BIGINT NOT NULL DEFAULT 0,
    advance         BIGINT NOT NULL DEFAULT 0,
    deductions      BIGINT NOT NULL DEFAULT 0,
    deduction_note  TEXT,
    net             BIGINT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'review' CHECK (status IN ('review','cc_approved','approved','paid','returned')),
    needs_director  INTEGER NOT NULL DEFAULT 0,
    return_reason   TEXT,
    created_at      TEXT NOT NULL,
    created_by      INTEGER NOT NULL REFERENCES users(id),
    cc_at           TEXT,
    cc_by           INTEGER REFERENCES users(id),
    dir_at          TEXT,
    dir_by          INTEGER REFERENCES users(id),
    paid_on         TEXT,
    paid_ref        TEXT,
    paid_by         INTEGER REFERENCES users(id)
);

CREATE TABLE owner_certificates (
    id                 INTEGER PRIMARY KEY,
    project_id         INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code               TEXT NOT NULL UNIQUE,              -- P-2026-001-IPC-001
    milestone_id       INTEGER REFERENCES payment_milestones(id),
    period_to          TEXT NOT NULL,
    gross              BIGINT NOT NULL CHECK (gross > 0),
    retention          BIGINT NOT NULL DEFAULT 0,
    advance            BIGINT NOT NULL DEFAULT 0,
    vat                BIGINT NOT NULL DEFAULT 0,
    net                BIGINT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft','agreed','submitted','certified','collected')),
    notes              TEXT,
    created_at         TEXT NOT NULL,
    created_by         INTEGER NOT NULL REFERENCES users(id),
    agreed_at          TEXT,
    agreed_by          INTEGER REFERENCES users(id),
    submitted_on       TEXT,
    certified_on       TEXT,
    certified_amount   BIGINT,
    collected_on       TEXT,
    collected_by       INTEGER REFERENCES users(id)
);

INSERT INTO role_permissions(role, permission)
SELECT r.key, p.perm FROM roles r JOIN (
    SELECT 'admin' AS role, 'payables.raise' AS perm UNION ALL SELECT 'pm', 'payables.raise'
    UNION ALL SELECT 'admin', 'payables.approve' UNION ALL SELECT 'accountant', 'payables.pay'
    UNION ALL SELECT 'pm', 'billing.prepare'
) p ON p.role = r.key WHERE 1 = 1
ON CONFLICT DO NOTHING;
