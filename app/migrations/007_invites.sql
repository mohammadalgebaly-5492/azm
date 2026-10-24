-- روابط التسجيل: يصدرها مدير النظام (أو من يملك صلاحية admin.invites)، ولكل رابط دور ومدة وعدد استخدامات
CREATE TABLE invites (
    id          INTEGER PRIMARY KEY,
    token       TEXT NOT NULL UNIQUE,
    role        TEXT NOT NULL REFERENCES roles(key) ON DELETE CASCADE,
    max_uses    INTEGER NOT NULL DEFAULT 1 CHECK (max_uses BETWEEN 1 AND 100),
    uses        INTEGER NOT NULL DEFAULT 0 CHECK (uses >= 0),
    note        TEXT,
    expires_at  TEXT NOT NULL,
    revoked_at  TEXT,
    created_at  TEXT NOT NULL,
    created_by  INTEGER NOT NULL REFERENCES users(id)
);
