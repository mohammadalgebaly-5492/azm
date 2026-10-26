-- تقارير المهندس: نص و/أو ملف PDF على التقرير اليومي وطلب الشراء وطلب التغيير والمستخلص والفاتورة ومحضر الاستلام
-- (قرار م. محمد 2026-10-26). تُضاف ولا تُحذف.
CREATE TABLE attachments (
    id           INTEGER PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    doc_kind     TEXT NOT NULL CHECK (doc_kind IN ('dsr','pr','cr','payable','grn')),
    doc_id       INTEGER NOT NULL,
    body         TEXT,
    file_name    TEXT,
    size_bytes   INTEGER,
    storage_key  TEXT,
    created_at   TEXT NOT NULL,
    created_by   INTEGER NOT NULL REFERENCES users(id)
);
CREATE INDEX attachments_doc ON attachments(doc_kind, doc_id);
