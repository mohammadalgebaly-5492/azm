-- معاينات استيراد جدول الكميات: تُحفظ في قاعدة البيانات بدل القرص، وتُحذف بعد ساعة
CREATE TABLE import_previews (
    token        TEXT PRIMARY KEY,
    project_id   BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    root_wbs_id  BIGINT,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX import_previews_created ON import_previews(created_at);

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
