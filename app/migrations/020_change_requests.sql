-- طلبات التغيير (الدستور، البند 4.9): داخلي على خطة الشركة، أو تعاقدي يصبح أمر تغيير في العقد بعد موافقة المالك.
-- التغيير الداخلي المعتمد يعدّل ميزانية البنود المتأثرة. المبالغ بالهللة (موجبة للزيادة وسالبة للنقص).
CREATE TABLE change_requests (
    id               INTEGER PRIMARY KEY,
    project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    code             TEXT NOT NULL UNIQUE,                -- P-2026-001-CR-001
    kind             TEXT NOT NULL CHECK (kind IN ('internal','contractual')),
    source           TEXT NOT NULL CHECK (source IN ('company','owner','consultant')),
    description      TEXT NOT NULL,
    cost_impact      BIGINT NOT NULL DEFAULT 0,
    days_impact      INTEGER NOT NULL DEFAULT 0,
    resource_impact  TEXT,
    status           TEXT NOT NULL DEFAULT 'pm_review'
                     CHECK (status IN ('pm_review','cc_review','dir_review','approved','returned')),
    return_reason    TEXT,
    vo_id            INTEGER REFERENCES variation_orders(id),
    created_at       TEXT NOT NULL,
    created_by       INTEGER NOT NULL REFERENCES users(id),
    pm_at            TEXT,
    pm_by            INTEGER REFERENCES users(id),
    cc_at            TEXT,
    cc_by            INTEGER REFERENCES users(id),
    dir_at           TEXT,
    dir_by           INTEGER REFERENCES users(id)
);

CREATE TABLE cr_items (
    cr_id        INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
    boq_item_id  INTEGER NOT NULL REFERENCES boq_items(id),
    amount       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (cr_id, boq_item_id)
);

CREATE TABLE cr_activities (
    cr_id        INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
    activity_id  INTEGER NOT NULL REFERENCES activities(id),
    PRIMARY KEY (cr_id, activity_id)
);

CREATE TABLE budget_adjustments (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    boq_item_id  INTEGER NOT NULL REFERENCES boq_items(id),
    cr_id        INTEGER NOT NULL REFERENCES change_requests(id),
    amount       BIGINT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX budget_adjustments_item ON budget_adjustments(boq_item_id);

INSERT INTO role_permissions(role, permission)
SELECT key, 'changes.request' FROM roles WHERE key IN ('admin', 'pm')
ON CONFLICT DO NOTHING;
