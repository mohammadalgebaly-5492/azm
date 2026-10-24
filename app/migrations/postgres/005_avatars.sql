-- صورة الحساب: NULL = الحرف الأول من الاسم، p:<مفتاح> = صورة جاهزة، u:<إصدار> = صورة مرفوعة
-- الصورة المرفوعة في جدول منفصل حتى لا تُحمَّل مع كل استعلام على users
ALTER TABLE users ADD COLUMN avatar TEXT;

CREATE TABLE user_avatars (
    user_id       BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    content_type  TEXT NOT NULL,
    data          BYTEA NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL
);

DO $$
DECLARE t record;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t.tablename);
        END IF;
    END LOOP;
END $$;
