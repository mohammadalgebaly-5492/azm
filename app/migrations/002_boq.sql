-- المرحلة الثانية: هيكل WBS وجدول الكميات وخط الأساس
-- الكميات تُخزن بالألف (qty_milli = الكمية × 1000) لتجنب أخطاء الكسور. المبالغ بالهللة.

CREATE TABLE wbs_nodes (
    id          INTEGER PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    parent_id   INTEGER REFERENCES wbs_nodes(id),
    code        TEXT NOT NULL,                 -- 01 أو 01.02 أو 01.02.03
    name        TEXT NOT NULL,
    level       INTEGER NOT NULL CHECK (level BETWEEN 1 AND 4),
    created_at  TEXT NOT NULL,
    created_by  INTEGER NOT NULL REFERENCES users(id),
    UNIQUE (project_id, code)
);
CREATE INDEX wbs_project ON wbs_nodes(project_id);

CREATE TABLE boq_items (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    wbs_id       INTEGER NOT NULL REFERENCES wbs_nodes(id),
    code         TEXT NOT NULL,                -- 01.02-SE-010
    ref_no       TEXT,                         -- رقم البند في جدول كميات المالك
    description  TEXT NOT NULL,
    item_type    TEXT NOT NULL CHECK (item_type IN ('supply','exec','both')),
    unit         TEXT NOT NULL,
    qty_milli    INTEGER NOT NULL CHECK (qty_milli > 0),
    unit_rate    INTEGER NOT NULL CHECK (unit_rate >= 0),
    amount       INTEGER NOT NULL CHECK (amount >= 0),
    notes        TEXT,
    created_at   TEXT NOT NULL,
    created_by   INTEGER NOT NULL REFERENCES users(id),
    updated_at   TEXT,
    UNIQUE (project_id, code),
    CHECK (amount = (qty_milli * unit_rate + 500) / 1000)
);
CREATE INDEX boq_project ON boq_items(project_id);
CREATE INDEX boq_wbs ON boq_items(wbs_id);

ALTER TABLE projects ADD COLUMN baseline_total INTEGER;
ALTER TABLE projects ADD COLUMN baseline_approved_at TEXT;
ALTER TABLE projects ADD COLUMN baseline_approved_by INTEGER REFERENCES users(id);

-- بعد اعتماد خط الأساس: جدول الكميات وهيكل WBS مجمّدان على مستوى قاعدة البيانات
CREATE TRIGGER boq_locked_insert BEFORE INSERT ON boq_items
WHEN (SELECT baseline_approved_at FROM projects WHERE id = NEW.project_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'baseline approved: BOQ is locked'); END;
CREATE TRIGGER boq_locked_update BEFORE UPDATE ON boq_items
WHEN (SELECT baseline_approved_at FROM projects WHERE id = OLD.project_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'baseline approved: BOQ is locked'); END;
CREATE TRIGGER boq_locked_delete BEFORE DELETE ON boq_items
WHEN (SELECT baseline_approved_at FROM projects WHERE id = OLD.project_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'baseline approved: BOQ is locked'); END;
CREATE TRIGGER wbs_locked_insert BEFORE INSERT ON wbs_nodes
WHEN (SELECT baseline_approved_at FROM projects WHERE id = NEW.project_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'baseline approved: WBS is locked'); END;
CREATE TRIGGER wbs_locked_delete BEFORE DELETE ON wbs_nodes
WHEN (SELECT baseline_approved_at FROM projects WHERE id = OLD.project_id) IS NOT NULL
BEGIN SELECT RAISE(ABORT, 'baseline approved: WBS is locked'); END;
