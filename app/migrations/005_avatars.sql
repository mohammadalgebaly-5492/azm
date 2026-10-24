-- صورة الحساب: NULL = الحرف الأول من الاسم، p:<مفتاح> = صورة جاهزة، u:<إصدار> = صورة مرفوعة
-- الصورة المرفوعة في جدول منفصل حتى لا تُحمَّل مع كل استعلام على users
ALTER TABLE users ADD COLUMN avatar TEXT;

CREATE TABLE user_avatars (
    user_id       INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    content_type  TEXT NOT NULL,
    data          BLOB NOT NULL,
    updated_at    TEXT NOT NULL
);
