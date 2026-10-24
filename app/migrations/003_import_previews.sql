-- معاينات استيراد جدول الكميات: تُحفظ في قاعدة البيانات بدل القرص، وتُحذف بعد ساعة
CREATE TABLE import_previews (
    token        TEXT PRIMARY KEY,
    project_id   INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    root_wbs_id  INTEGER,
    payload      TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX import_previews_created ON import_previews(created_at);
