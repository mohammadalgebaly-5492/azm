-- العقد الرئيسي مع المالك (الدستور، البند 3.2): بياناته ومدته ودفعاته وغراماته، والضمانات البنكية، والتأمينات، وأوامر التغيير.
-- النسب تُخزن بأجزاء من عشرة آلاف (15.00% = 1500)، والمبالغ بالهللة.
CREATE TABLE contracts (
    id                   INTEGER PRIMARY KEY,
    project_id           INTEGER NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    code                 TEXT NOT NULL UNIQUE,                      -- P-2026-001-CON-01
    contract_no          TEXT NOT NULL,
    signed_on            TEXT NOT NULL,
    kind                 TEXT NOT NULL CHECK (kind IN ('lump_sum','remeasure')),
    value_ex_vat         BIGINT NOT NULL CHECK (value_ex_vat > 0),
    vat_bp               INTEGER NOT NULL CHECK (vat_bp BETWEEN 0 AND 10000),
    scope                TEXT NOT NULL,
    site_handover_on     TEXT NOT NULL,
    start_on             TEXT NOT NULL,
    duration_days        INTEGER NOT NULL CHECK (duration_days > 0),
    warranty_months      INTEGER NOT NULL CHECK (warranty_months >= 0),
    advance_bp           INTEGER CHECK (advance_bp IS NULL OR advance_bp BETWEEN 0 AND 10000),
    advance_recovery_bp  INTEGER CHECK (advance_recovery_bp IS NULL OR advance_recovery_bp BETWEEN 0 AND 10000),
    retention_bp         INTEGER NOT NULL CHECK (retention_bp BETWEEN 0 AND 10000),
    retention_cap_bp     INTEGER CHECK (retention_cap_bp IS NULL OR retention_cap_bp BETWEEN 0 AND 10000),
    payment_days         INTEGER CHECK (payment_days IS NULL OR payment_days >= 0),
    penalty_method       TEXT CHECK (penalty_method IS NULL OR penalty_method IN ('daily_pct','daily_amount')),
    penalty_value        BIGINT CHECK (penalty_value IS NULL OR penalty_value >= 0),
    penalty_cap_bp       INTEGER CHECK (penalty_cap_bp IS NULL OR penalty_cap_bp BETWEEN 0 AND 10000),
    created_at           TEXT NOT NULL,
    created_by           INTEGER NOT NULL REFERENCES users(id),
    updated_at           TEXT
);

CREATE TABLE contract_guarantees (
    id           INTEGER PRIMARY KEY,
    contract_id  INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL CHECK (kind IN ('bid','performance','advance')),
    bank         TEXT NOT NULL,
    number       TEXT NOT NULL,
    amount       BIGINT NOT NULL CHECK (amount > 0),
    issued_on    TEXT NOT NULL,
    expires_on   TEXT NOT NULL,
    released_on  TEXT,
    created_at   TEXT NOT NULL,
    created_by   INTEGER NOT NULL REFERENCES users(id),
    CHECK (expires_on > issued_on)
);
CREATE INDEX contract_guarantees_contract ON contract_guarantees(contract_id);

CREATE TABLE contract_insurances (
    id            INTEGER PRIMARY KEY,
    contract_id   INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('car','third_party','workers')),
    insurer       TEXT NOT NULL,
    policy_no     TEXT NOT NULL,
    cover_amount  BIGINT NOT NULL CHECK (cover_amount > 0),
    expires_on    TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    created_by    INTEGER NOT NULL REFERENCES users(id)
);
CREATE INDEX contract_insurances_contract ON contract_insurances(contract_id);

-- أوامر التغيير: كل زيادة أو نقص في القيمة أو المدة أمرٌ مستقل، ولا تُعدَّل قيمة العقد الأصلية
CREATE TABLE variation_orders (
    id             INTEGER PRIMARY KEY,
    contract_id    INTEGER NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    code           TEXT NOT NULL UNIQUE,                    -- P-2026-001-VO-001
    issued_on      TEXT NOT NULL,
    description    TEXT NOT NULL,
    value_delta    BIGINT NOT NULL,
    days_delta     INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'study' CHECK (status IN ('study','approved','rejected')),
    decided_at     TEXT,
    decided_by     INTEGER REFERENCES users(id),
    decision_note  TEXT,
    created_at     TEXT NOT NULL,
    created_by     INTEGER NOT NULL REFERENCES users(id)
);
CREATE INDEX variation_orders_contract ON variation_orders(contract_id);

CREATE TABLE variation_order_items (
    vo_id        INTEGER NOT NULL REFERENCES variation_orders(id) ON DELETE CASCADE,
    boq_item_id  INTEGER NOT NULL REFERENCES boq_items(id),
    PRIMARY KEY (vo_id, boq_item_id)
);

-- اعتماد أوامر التغيير للمدير التنفيذي (الدستور: التغيير التعاقدي يعتمده المدير التنفيذي دائمًا)
INSERT INTO role_permissions(role, permission)
SELECT key, 'changes.approve' FROM roles WHERE key = 'director'
ON CONFLICT DO NOTHING;
