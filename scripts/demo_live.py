"""ينقل المثال التجريبي الكامل إلى قاعدة البيانات التي يقرؤها wsgi.py (الحقيقية إذا وُجد .env.local) بأمر واحد:

  .venv/Scripts/python scripts/demo_live.py

1. ينشئ حسابات طاقم المشروع إن لم تكن موجودة، بكلمة مرور مؤقتة عشوائية يُطلب تغييرها عند أول دخول، ولا ينشئ أي حساب بكلمة
   مرور معروفة.
2. يشغّل scripts/demo_full.py بهذه الحسابات: مشروع جديد بكل تفاصيل نسخة التجربة، يضيف فقط ولا يحذف ولا يعدّل شيئًا موجودًا.
3. يطبع أسماء المستخدمين وكلمات المرور المؤقتة للحسابات الجديدة فقط.

ملفات PDF لا تُرفع إلا إذا كان مكان حفظ الملفات (Supabase Storage) مضبوطًا؛ وإلا تُضاف تقارير المهندس نصًا وتُؤجَّل النسخ الموقّعة.
وافق م. محمد على نقل المثال للمنصة (2026-10-26: «انقلي كل ... محتوى اللوكال على المنصة الاونلاين»)."""
import os
import runpy
import sys

os.environ.setdefault("VERCEL", "1")  # لا تُحفظ ملفات على هذا الجهاز بدل مكان الحفظ الحقيقي
sys.path.insert(0, ".")
from wsgi import app  # noqa: E402
from app.auth import create_user  # noqa: E402
from app.db import connect  # noqa: E402

TEAM = [  # (الدور في المثال، اسم المستخدم، الاسم، الدور في المنصة)
    ("cost", "a.sami", "م. أحمد خالد سامي", "admin"),
    ("director", "a.alsubaie", "م. عبدالله السبيعي", "director"),
    ("pm", "m.almajed", "م. محمد الماجد", "pm"),
    ("engineer", "a.asem", "م. أمجد عاصم", "pm"),
    ("accountant", "a.almohammadi", "أحمد المحمدي", "accountant"),
    ("procurement", "f.almaliki", "فهد المالكي", "procurement"),
]

db = connect(app.config["DATABASE"])
live = str(app.config["DATABASE"]).startswith("postgres")
print("database:", "LIVE POSTGRES" if live else app.config["DATABASE"])
if db.execute("SELECT 1 FROM projects WHERE contract_no = 'DEMO-2026-014'").fetchone():
    sys.exit("the demo project already exists: nothing to do")
created = []
with app.app_context():
    for _role, username, name, role in TEAM:
        row = db.execute("SELECT status FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            _uid, _code, temp = create_user(db, username=username, email=f"{username}@enma-azm.example", full_name=name,
                                            role=role)
            created.append((username, name, temp))
        elif row["status"] != "active":
            sys.exit(f"account {username!r} exists but is not active")
db.close()
sys.argv = ["scripts/demo_full.py"] + [f"{r}={u}" for r, u, _n, _x in TEAM]
runpy.run_path("scripts/demo_full.py", run_name="__main__")
print("\nnew accounts (temporary passwords, changed at first sign-in):")
for username, name, temp in created:
    print(f"  {username:16} {temp:20} {name}")
