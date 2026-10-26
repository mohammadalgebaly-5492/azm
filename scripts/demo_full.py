"""يبني مثالًا كاملًا لمشروع في منتصف التنفيذ عبر دوال المنصة نفسها (بكل قواعدها): الجهات والأطراف، والعقد بضماناته وتأميناته
وأوامر تغييره، وجدول الكميات وتحليل الأسعار وخط أساس الميزانية، والمستندات، ونطاق العمل وخطواته، والجدول الزمني وجدول
الدفعات، والموارد والهيكل التنظيمي والتخصيصات، ومحضر بدء التنفيذ، والتقارير اليومية لكل أيام العمل حتى اليوم، والمشتريات
وأوامر الشراء وعقود الباطن، ومحاضر الاستلام والفواتير والمستخلصات والصرف، ومستخلصات المالك والتحصيل، وطلبات التغيير،
والتأخير وخطط التعافي، ومراجعة خط الأساس، والنسخ الموقّعة، وتقارير المهندس، ومستويات صلاحية المهندس.
قيمة العقد 4,000,000 ريال لمبنى من ثلاثة طوابق مساحة الطابق 400 م2: الهيكل 700 ريال للمتر المربع لكل سقف،
والتشطيب 2,500 ريال (بين 2,000 و4,000 حسب م. محمد 2026-10-26)، والأعمال التمهيدية 160,000 ريال.

الاستخدام (من مجلد المشروع):
  python scripts/demo_full.py cost=<مهندس تحكم تكلفة> director=<المدير التنفيذي> pm=<مدير المشروع>
                              engineer=<مهندس الموقع> accountant=<المحاسب> procurement=<المشتريات>
كل قيمة اسم مستخدم موجود ونشط، وكلها أشخاص مختلفون (من يُعِد لا يعتمد).
يعمل على قاعدة البيانات التي يقرؤها wsgi.py: الحقيقية إذا وُجد .env.local، وإلا يُضبط DATABASE_URL فارغًا مع CC_DATABASE.
يضيف مشروعًا جديدًا فقط ولا يحذف ولا يعدّل شيئًا موجودًا، ويرفض التشغيل إذا كان المشروع التجريبي موجودًا.
التواريخ نسبية: يبدأ المشروع قبل 25 أسبوعًا من يوم التشغيل، ومدته سنة. وافق م. محمد على المثال (2026-10-25 و2026-10-26)."""
import io
import sys
from datetime import date, timedelta

from werkzeug.datastructures import MultiDict

sys.path.insert(0, ".")
from wsgi import app  # noqa: E402
from app import (attachments as AT, authority as AU, billing as B, boq, changes as CH, contracts as C, daily as Y, documents as D,  # noqa: E402
                 files, governance as G, payables as X, pricing as PRC, procurement as Q, projects, registers as R,
                 resources as S, schedule as T, scope as W, signed as SG)
from app.db import connect, tx  # noqa: E402

TAG = "(بيانات تجريبية)"
CONTRACT_NO = "DEMO-2026-014"
ROLES = ("cost", "director", "pm", "engineer", "accountant", "procurement")
COST_SCALE = 1.55  # التكلفة اليومية للأطقم والمعدات والأفراد

db = connect(app.config["DATABASE"])
print("database:", "LIVE POSTGRES" if str(app.config["DATABASE"]).startswith("postgres") else app.config["DATABASE"])
args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
if set(args) != set(ROLES):
    sys.exit(__doc__)
U = {}
for role, name in args.items():
    row = db.execute("SELECT id FROM users WHERE username = ? AND status = 'active'", (name,)).fetchone()
    if row is None:
        sys.exit(f"no active user {name!r}")
    U[role] = row[0]
if len(set(U.values())) != len(U):
    sys.exit("every role needs a different person")
if db.execute("SELECT 1 FROM projects WHERE contract_no = ?", (CONTRACT_NO,)).fetchone():
    sys.exit("the demo project already exists")
cost, director, pm, eng, acc, buyer = (U[r] for r in ROLES)

TODAY = date.today()
START = TODAY - timedelta(days=175)
START -= timedelta(days=(START.weekday() + 1) % 7)  # الأحد
LAST = (TODAY - START).days - 1                       # آخر يوم له تقرير: أمس


def dd(n):
    return START + timedelta(days=n)


def d(n):
    return dd(n).isoformat()


def ts(n, hour=10):
    return f"{d(n)}T{hour:02d}:00:00+00:00"


def working(n):
    return dd(n).weekday() in (6, 0, 1, 2, 3)  # الأحد إلى الخميس


def stamp(table, rid, **cols):
    """تواريخ تاريخية للمثال فقط: المنصة تسجّل وقت الإدخال، والمثال يمثّل أعمالًا جرت على مدى أشهر."""
    with tx(db):
        db.execute(f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?", (*cols.values(), rid))


def one(sql, *a):
    return db.execute(sql, a).fetchone()[0]


def pdf(*lines):
    """ملف PDF صغير صالح بنص إنجليزي (نسخة موقّعة تجريبية)."""
    text = " ".join(f"({s}) Tj 0 -22 Td" for s in lines)
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    stream = f"BT /F1 16 Tf 60 760 Td {text} ET"
    objs[3] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + "".join(f"{o:010d} 00000 n \n" for o in offs).encode()
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


with app.test_request_context():
    # ---------- الجهات (المادة 2) ----------
    def entity(kind, name, form, people, city, details):
        eid, _ = R.create_entity(db, kind, MultiDict([("name", f"{name} {TAG}"), *form]), cost)
        R.add_address(db, eid, {"label": "main", "city": city, "details": details}, cost)
        return eid, [R.add_person(db, eid, {"full_name": n, "job_title": t, "phone": ph, "email": e}, cost)[0]
                     for n, t, ph, e in people]

    OWNER, o_people = entity("owner", "شركة النخبة للتطوير العقاري",
                             [("email", "info@nukhba.example"), ("phone", "0112345678"), ("cr_no", "1010000001")],
                             [("م. سلمان العتيبي", "مدير المشاريع", "0501111111", "salman@nukhba.example"),
                              ("م. نورة القحطاني", "مهندسة متابعة", "0502222222", "noura@nukhba.example")],
                             "الرياض", "طريق الملك فهد، برج النخبة")
    CONS, c_people = entity("consultant", "مكتب الرؤية للاستشارات الهندسية",
                            [("email", "office@ruya.example"), ("phone", "0119876543")],
                            [("م. خالد الدوسري", "المهندس المقيم", "0504444444", "khaled@ruya.example"),
                             ("م. ريم الحربي", "مهندسة إشراف", "0505555555", "reem@ruya.example")],
                            "الرياض", "حي العليا، شارع التحلية")

    def vendor(kind, name, email, phone, specs, person, city="الرياض", details="المنطقة الصناعية الثانية"):
        form = [("email", email), ("phone", phone), ("cr_no", f"10100{len(email):05d}"), ("vat_no", "300000000000003"),
                ("approval_status", "approved")] + [("specialties", s) for s in specs]
        if kind == "subcontractor":
            form.append(("classification", "الدرجة الثالثة"))
        return entity(kind, name, form, [(person, "مدير المبيعات" if kind == "supplier" else "مدير العمليات", phone,
                                          email.replace("info", "sales"))], city, details)[0]

    SUB_DIG = vendor("subcontractor", "مؤسسة الإتقان للحفريات", "info@itqan.example", "0506666666", ["CNC", "MAS"],
                     "أ. ماجد الزهراني")
    SUB_DIG2 = vendor("subcontractor", "مؤسسة الصخرة للمقاولات", "info@sakhra.example", "0506666777", ["CNC"], "أ. بدر الشمري")
    SUB_ELE = vendor("subcontractor", "شركة النور للأعمال الكهربائية", "info@noor-elec.example", "0507777000", ["ELE"],
                     "م. وليد السالم")
    SUB_ELE2 = vendor("subcontractor", "مؤسسة الطاقة الحديثة", "info@taqa.example", "0507777111", ["ELE"], "م. هاني يوسف")
    SUB_LAB = vendor("subcontractor", "مختبر الجودة للاختبارات الهندسية", "info@qlab.example", "0507777222", ["CNC"],
                     "م. أيمن فاروق")
    SUB_ELV = vendor("subcontractor", "شركة المصاعد العربية", "info@arab-lifts.example", "0507777333", ["MEC"], "م. طلال الحربي")
    SUP_RMX = vendor("supplier", "مصنع الخرسانة الجاهزة الأول", "info@rmx1.example", "0508000001", [], "أ. صالح العمري")
    SUP_RMX2 = vendor("supplier", "شركة الإسمنت والخرسانة المتحدة", "info@ucc.example", "0508000002", [], "أ. نايف المالكي")
    SUP_STL = vendor("supplier", "مؤسسة الحديد الوطني", "info@steel.example", "0508000003", [], "أ. عادل القحطاني")
    SUP_STL2 = vendor("supplier", "شركة صلب الخليج", "info@gulfsteel.example", "0508000004", [], "أ. راشد البقمي")
    SUP_BLK = vendor("supplier", "مصنع البلوك الحديث", "info@block.example", "0508000005", [], "أ. منصور الحربي")
    SUP_INS = vendor("supplier", "شركة العوازل المتقدمة", "info@insul.example", "0508000006", [], "أ. حمد الدوسري")
    SUP_SND = vendor("supplier", "مؤسسة الرمال والبحص", "info@sand.example", "0508000007", [], "أ. سعد العنزي")

    # ---------- المشروع والأطراف والعقد (3.2) ----------
    pid, pcode = projects.create_project(db, {"name": f"مبنى إداري من ثلاثة طوابق {TAG}", "location": "الرياض، حي الملقا",
                                              "contract_no": CONTRACT_NO, "contract_value": "4,000,000.00",
                                              "start_date": d(0), "end_date": d(364)}, cost)
    for uid in U.values():
        projects.add_member(db, pid, uid, cost)
    R.set_project_parties(db, pid, MultiDict([
        ("owner_entity_id", str(OWNER)), ("owner_reps", str(o_people[0])), ("owner_reps", str(o_people[1])),
        ("consultant_entity_id", str(CONS)), ("consultant_reps", str(c_people[0])), ("consultant_reps", str(c_people[1]))]), cost)
    C.save_contract(db, pid, {
        "contract_no": CONTRACT_NO, "signed_on": d(-14), "kind": "lump_sum", "value_ex_vat": "4,000,000.00", "vat_pct": "15",
        "scope": "إنشاء مبنى إداري من ثلاثة طوابق شامل الأعمال الإنشائية والكهروميكانيكية والتشطيبات",
        "site_handover_on": d(-5), "start_on": d(0), "duration_days": "365", "warranty_months": "12",
        "advance_pct": "10", "advance_recovery_pct": "10", "retention_pct": "10", "retention_cap_pct": "5",
        "payment_days": "30", "penalty_method": "daily_pct", "penalty_value": "0.1", "penalty_cap_pct": "10"}, cost)
    con = C.contract_of(db, pid)
    C.add_guarantee(db, con["id"], {"kind": "performance", "bank": "البنك الأهلي السعودي", "number": "LG-2026-0417",
                                    "amount": "200,000", "issued_on": d(-14),
                                    "expires_on": (TODAY + timedelta(days=21)).isoformat()}, cost)
    C.add_guarantee(db, con["id"], {"kind": "advance", "bank": "بنك الرياض", "number": "LG-2026-0418", "amount": "400,000",
                                    "issued_on": d(-14), "expires_on": d(380)}, cost)
    C.add_insurance(db, con["id"], {"kind": "car", "insurer": "التعاونية للتأمين", "policy_no": "CAR-55120",
                                    "cover_amount": "4,000,000", "expires_on": d(400)}, cost)
    C.add_insurance(db, con["id"], {"kind": "third_party", "insurer": "التعاونية للتأمين", "policy_no": "TPL-55121",
                                    "cover_amount": "1,000,000", "expires_on": d(400)}, cost)

    # ---------- جدول الكميات وتحليل الأسعار وخط أساس الميزانية (3.3، 3.5) ----------
    PHASES = [  # الهيكل 840,000 (700 × 1,200 م2)، والتشطيب 3,000,000 (2,500 × 1,200 م2)، والتمهيدية 160,000
        ("الأعمال التمهيدية والحفر", [
            ("تجهيز الموقع", [("A-01", "تسوير الموقع بسور مؤقت", "exec", "م.ط", "180", "70"),
                              ("A-02", "تسوية الموقع وتنظيفه", "exec", "م2", "1500", "9"),
                              ("A-03", "مكتب ومرافق الموقع المؤقتة", "both", "مقطوعية", "1", "22000"),
                              ("A-07", "اختبارات التربة والخرسانة في مختبر معتمد", "exec", "مقطوعية", "1", "22200")]),
            ("الحفر والردم", [("A-04", "حفر عام للأساسات", "exec", "م3", "1800", "30"),
                              ("A-05", "ردم بمواد مختارة ومدموكة", "both", "م3", "700", "41"),
                              ("A-06", "رش مبيد النمل الأبيض", "both", "م2", "500", "14")])]),
        ("الأعمال الإنشائية", [
            ("الأساسات", [("B-01", "خرسانة عادية للنظافة", "both", "م3", "70", "350"),
                          ("B-02", "خرسانة مسلحة للقواعد", "both", "م3", "160", "1300"),
                          ("B-06", "خزان مياه أرضي من الخرسانة المسلحة", "both", "م3", "60", "1400"),
                          ("B-07", "عزل بيتوميني للأساسات", "both", "م2", "600", "33")]),
            ("الهيكل الخرساني", [("B-03", "خرسانة مسلحة للأعمدة", "both", "م3", "85", "1600"),
                                 ("B-04", "خرسانة مسلحة للكمرات والبلاطات", "both", "م3", "220", "1500"),
                                 ("B-05", "خرسانة مسلحة للسلالم", "both", "م3", "26", "1450")])]),
        ("أعمال المباني والعزل", [
            ("أعمال البناء", [("C-01", "بناء بلوك أسمنتي 25 سم للجدران الخارجية", "both", "م2", "1100", "95"),
                              ("C-02", "بناء بلوك أسمنتي 10 سم للقواطع", "both", "م2", "650", "70"),
                              ("C-05", "لياسة داخلية", "both", "م2", "3400", "32"),
                              ("C-06", "لياسة خارجية", "both", "م2", "1300", "40")]),
            ("العزل", [("C-03", "عزل مائي للأسطح", "both", "م2", "480", "65"),
                       ("C-04", "عزل حراري للأسطح", "both", "م2", "480", "55")])]),
        ("الأعمال الكهروميكانيكية", [
            ("الأعمال الكهربائية", [("D-01", "لوحات توزيع رئيسية وفرعية", "both", "عدد", "6", "18000"),
                                    ("D-02", "تمديدات كهربائية للإنارة والقوى", "both", "م2", "1200", "120"),
                                    ("D-08", "مولد احتياطي 250 ك.ف.أ مع لوحة التحويل", "both", "عدد", "1", "145000"),
                                    ("D-09", "شبكات البيانات وكاميرات المراقبة", "both", "م2", "1200", "40")]),
            ("التكييف والسباكة", [("D-03", "وحدات تكييف منفصلة", "both", "عدد", "30", "9500"),
                                  ("D-04", "شبكة سباكة وتصريف", "both", "مقطوعية", "1", "220000")]),
            ("السلامة والمصاعد", [("D-05", "نظام إنذار الحريق", "both", "م2", "1200", "45"),
                                  ("D-06", "نظام إطفاء الحريق بالرشاشات", "both", "م2", "1200", "85"),
                                  ("D-07", "مصعد ركاب 8 أشخاص لثلاث وقفات", "both", "عدد", "1", "185000")])]),
        ("التشطيبات والتسليم", [
            ("التشطيبات الداخلية", [("E-01", "أرضيات بورسلان", "both", "م2", "1050", "240"),
                                    ("E-02", "دهانات داخلية وخارجية", "both", "م2", "4700", "42"),
                                    ("E-03", "أبواب خشبية ونوافذ ألمنيوم", "both", "عدد", "60", "3800"),
                                    ("E-05", "أسقف مستعارة من ألواح الجبس", "both", "م2", "1000", "120"),
                                    ("E-07", "سيراميك الحمامات والمطابخ", "both", "م2", "450", "150"),
                                    ("E-08", "درابزين ستانلس ستيل للسلالم", "both", "م.ط", "60", "650")]),
            ("الواجهات", [("E-06", "كسوة الواجهات بالحجر الطبيعي", "both", "م2", "900", "450")]),
            ("التسليم", [("E-04", "تنظيف نهائي وتسليم المشروع للمالك", "exec", "مقطوعية", "1", "31700")])]),
    ]
    I, QTY, WBS = {}, {}, {}
    for pname, secs in PHASES:
        p_id, _ = boq.add_wbs(db, pid, pname, None, cost)
        for sname, rows in secs:
            s_id, _ = boq.add_wbs(db, pid, sname, p_id, cost)
            WBS[sname] = s_id
            for ref, desc, typ, unit, qty, rate in rows:
                I[ref] = boq.add_item(db, pid, s_id, {"ref_no": ref, "description": desc, "item_type": typ, "unit": unit,
                                                      "qty": qty, "unit_rate": rate}, cost)[0]
                QTY[ref] = float(qty)
    CODE = {r["id"]: r["code"] for r in db.execute("SELECT id, code FROM boq_items WHERE project_id = ?", (pid,))}
    ANALYSIS = {  # (النوع، الوصف، الوحدة، الكمية لكل وحدة بند، السعر)
        "A-04": [("subcontract", "حفر بمعدات مقاول الباطن", "م3", "1", "22"), ("equipment", "لودر لتسوية القاع", "يوم", "0.002", "900")],
        "B-02": [("material", "خرسانة جاهزة C30", "م3", "1.02", "290"), ("material", "حديد تسليح", "م3", "1", "430"),
                 ("labour", "طاقم النجارة والحديد", "يوم", "0.15", "1500"), ("equipment", "خلاطة وهزاز", "يوم", "0.05", "600")],
        "B-03": [("material", "خرسانة جاهزة C35", "م3", "1.02", "300"), ("material", "حديد تسليح", "م3", "1", "450"),
                 ("labour", "طاقم النجارة والحديد", "يوم", "0.3", "1500")],
        "B-04": [("material", "خرسانة جاهزة C35", "م3", "1.02", "295"), ("material", "حديد تسليح", "م3", "1", "420"),
                 ("labour", "طاقم الشدات والحديد والصب", "يوم", "0.25", "1800"), ("equipment", "شدات معدنية مستأجرة", "م3", "1", "120")],
        "C-01": [("material", "بلوك أسمنتي 25 سم مع المونة", "م2", "1.03", "45"), ("labour", "طاقم المباني", "يوم", "0.04", "900")],
        "C-03": [("material", "لفائف عزل مائي 4 مم", "م2", "1.1", "32"), ("labour", "طاقم العزل", "يوم", "0.03", "500")],
        "D-02": [("subcontract", "تمديدات كهربائية بمقاول الباطن", "م2", "1", "90")],
        "D-07": [("subcontract", "توريد وتركيب المصعد بمقاول الباطن", "عدد", "1", "150000")],
        "E-06": [("material", "حجر طبيعي مع المثبتات", "م2", "1.05", "210"), ("labour", "طاقم التركيب", "يوم", "0.08", "1000")],
    }
    for ref, lines in ANALYSIS.items():
        for kind, desc, unit, q, price in lines:
            PRC.add_line(db, pid, I[ref], {"cost_type": kind, "description": desc, "unit": unit, "qty": q, "unit_price": price}, cost)
        PRC.set_rates(db, pid, I[ref], {"overhead_pct": "6", "profit_pct": "5"}, cost)
    boq.approve_baseline(db, pid, cost)
    stamp("projects", pid, baseline_approved_at=ts(-10))

    # ---------- المستندات (3.1) ----------
    DOC = {}

    def doc(key, title, kind, issuer, ref, on, status="review", rep=None, approved_on=None, notes=None, link=""):
        form = {"title": title, "doc_type": kind, "issuer": issuer, "issuer_ref": ref, "issued_on": d(on), "rev_no": "0",
                "status": status, "notes": notes, "link": link}
        if status != "review":
            ent = OWNER if issuer == "owner" else CONS
            people = o_people if issuer == "owner" else c_people
            form.update(approver_entity_id=str(ent), approver_person_id=str(people[rep or 0]), approved_on=d(approved_on))
        DOC[key] = D.create_document(db, pid, form, eng)[0]

    doc("site", "مخطط الموقع العام", "DRW", "consultant", "C-000", -20, "approved", 0, -16)
    doc("arch", "المخطط المعماري - المساقط الأفقية", "DRW", "consultant", "A-101", -20, "approved", 0, -15)
    doc("dig", "مخطط الحفر والمناسيب", "DRW", "consultant", "C-001", -20, "approved", 0, -15)
    doc("ftg", "المخطط الإنشائي - القواعد والرقاب", "DRW", "consultant", "S-201", -19, "approved_notes", 1, -12,
        "زيادة تسليح القاعدة ق3 حسب الملاحظة على المخطط.")
    doc("col", "المخطط الإنشائي - الأعمدة والكمرات والبلاطات", "DRW", "consultant", "S-202", -19, "approved", 1, -12)
    doc("blk", "مخطط المباني والقواطع", "DRW", "consultant", "A-201", -18, "approved", 0, -10)
    doc("ins", "تفاصيل عزل الأسطح", "DRW", "consultant", "A-401", -18, "approved", 0, -10)
    doc("ele", "مخطط الأعمال الكهربائية", "DRW", "consultant", "E-301", -17, "approved", 1, -8)
    doc("mep", "مخطط التكييف والسباكة", "DRW", "consultant", "M-401", -17, "approved", 1, -8)
    doc("fin", "مخطط التشطيبات والأرضيات", "DRW", "consultant", "A-301", -16, "approved", 0, -6)
    doc("fire", "مخطط إنذار وإطفاء الحريق", "DRW", "consultant", "F-501", -17, "approved", 1, -8)
    doc("elv", "مواصفات المصعد", "SPC", "consultant", "SPEC-07", -17, "approved", 1, -8)
    doc("fac", "مخطط الواجهات والحجر", "DRW", "consultant", "A-501", -16, "approved", 0, -6)
    doc("spc", "مواصفات الأعمال الخرسانية", "SPC", "consultant", "SPEC-03", -25, "approved", 0, -22)
    doc("spm", "مواصفات أعمال المباني والعزل", "SPC", "consultant", "SPEC-04", -25, "approved", 0, -22)
    doc("ctd", "عقد المقاولة الموقّع", "CTD", "owner", "CT-2026-14", -14, "approved", 0, -14)
    doc("ltr", "خطاب تسليم الموقع", "LTR", "owner", "OUT-2026-311", -5)
    doc("shd", "مخطط تنفيذي - تسليح القواعد", "SHD", "company", "SD-S-01", 30)
    doc("mom", "محضر اجتماع التنسيق الشهري", "MOM", "company", "MOM-05", 150)
    D.add_revision(db, pid, DOC["arch"], {"rev_no": "1", "rev_date": d(120), "status": "approved", "approver_entity_id": str(CONS),
                                          "approver_person_id": str(c_people[0]), "approved_on": d(126),
                                          "notes": "تعديل مداخل الطابق الأرضي"}, eng)
    D.add_revision(db, pid, DOC["ele"], {"rev_no": "1", "rev_date": d(168), "status": "review", "notes": None}, eng)
    for k in DOC:
        if k not in ("shd", "mom"):
            D.review_document(db, pid, DOC[k], cost)

    # ---------- الموارد (3.6): الأفراد والأطقم والمعدات ----------
    P = {}

    def person(key, name, prof, title, daily, **kw):
        P[key] = S.save_person(db, {"full_name": name, "profession_code": prof, "job_title_code": title,
                                    "id_no": f"2{len(P) + 1:09d}", "phone": f"05{len(P) + 31:08d}",
                                    "daily_cost": f"{daily * COST_SCALE:.2f}", "status": "active", **kw}, cost)

    person("pm", "م. محمد الماجد", "ENG", "PJM", 1200, nationality="سعودي", user_id=str(pm))
    person("site", "م. أمجد عاصم", "ENG", "CNM", 750, nationality="سعودي", user_id=str(eng))
    person("plan", "م. سارة العنزي", "ENG", "PLE", 700, nationality="سعودية")
    person("cce", "م. أحمد خالد سامي", "ENG", "CCE", 700, nationality="سعودي", user_id=str(cost))
    person("acc", "أحمد المحمدي", "ADM", "ACC", 550, nationality="سعودي", user_id=str(acc))
    person("prc", "فهد المالكي", "ADM", "PRM", 700, nationality="سعودي", user_id=str(buyer))
    person("srv", "عمر الزهراني", "TEC", "SRV", 400, nationality="سعودي")
    person("saf", "سعيد البلوشي", "SUP", "SAF", 400, nationality="سعودي")
    person("frm", "محمد عبدالرحيم", "SUP", "FRM", 300, nationality="مصري")
    person("opr", "زاهد إقبال", "OPR", "EQO", 280, nationality="باكستاني")
    person("drv", "مختار أحمد", "OPR", "DRV", 250, nationality="مصري")
    for i, n in enumerate(("أنور حسين", "رفيق الإسلام", "جمال الدين")):
        person(f"crp{i}", n, "TEC", "CRP", 220, nationality="بنغلاديشي")
    for i, n in enumerate(("نديم أحمد", "عرفان علي")):
        person(f"sfx{i}", n, "TEC", "SFX", 230, nationality="باكستاني")
    for i, n in enumerate(("كريم بخش", "منير أحمد", "شفيق الرحمن", "ذاكر حسين")):
        person(f"msn{i}", n, "TEC", "MSN", 210, nationality="باكستاني")
    for i, n in enumerate(("سليم أختر", "حسن محمود", "إقبال حسين", "طارق جميل", "ناصر علي", "عبدالقادر يوسف", "رحمت الله",
                           "جاويد إقبال")):
        person(f"lbr{i}", n, "LAB", "LBR", 150, nationality="هندي")
    person("plb", "ماهر سليمان", "TEC", "PLB", 240, nationality="مصري")
    person("plb2", "سامح عبدالعزيز", "TEC", "PLB", 220, nationality="مصري")

    def crew(name, spec, leader, members, daily=None):
        return S.save_crew(db, MultiDict([("name", name), ("specialty_code", spec), ("leader_id", str(P[leader])),
                                          ("daily_cost", f"{daily * COST_SCALE:.2f}" if daily else "")]
                                         + [("members", str(P[m])) for m in members]), cost)

    K = {"car": crew("طاقم النجارة", "CAR", "crp0", ["crp1", "crp2", "lbr0"]),
         "stl": crew("طاقم حديد التسليح", "STL", "sfx0", ["sfx1", "lbr1"]),
         "cnc": crew("طاقم صب الخرسانة", "CNC", "msn3", ["lbr2", "lbr3"]),
         "gen": crew("طاقم العمالة العامة", "CNC", "lbr4", ["lbr5", "lbr6"]),
         "mas": crew("طاقم المباني 1", "MAS", "msn0", ["msn1", "lbr7"], daily=800),
         "mas2": crew("طاقم المباني 2", "MAS", "msn2", [], daily=700),
         "ins": crew("طاقم العزل", "FIN", "plb2", [], daily=340),
         "mep": crew("طاقم السباكة والتكييف", "MEC", "plb", [], daily=400)}

    def eq(code, plate, daily, **kw):
        return S.save_equipment(db, {"catalog_code": code, "plate_serial": plate, "ownership": "owned",
                                     "daily_cost": f"{daily * COST_SCALE:.2f}", "status": "working", **kw}, cost)

    E = {"exc": eq("EXC", "أ ب ج 1234", 1200, label="رقم 1", make_model="CAT 320D"),
         "ldr": eq("LDR", "د هـ و 5678", 900, make_model="Komatsu WA320", ownership="rented", lessor="مؤسسة المعدات الثقيلة"),
         "dmp": eq("DMP", "ز ح ط 9012", 600, make_model="Mercedes Actros", ownership="rented", lessor="شركة النقل السريع"),
         "mix": eq("MIX", "MX-0901", 250, make_model="Imer Syntesi 350"),
         "vib": eq("VIB", "VB-2201", 60, label="رقم 1"),
         "vib2": eq("VIB", "VB-2202", 60, label="رقم 2", status="maintenance"),
         "pmp": eq("PMP", "PM-0410", 1000, make_model="Putzmeister 36m", ownership="rented", lessor="شركة الضخ الحديثة"),
         "gen": eq("GEN", "GN-0060", 400, label="60 ك.ف.أ", make_model="Perkins 60kVA"),
         "crn": eq("CRN", "CR-0025", 2500, label="25 طن", status="out")}

    O = {}

    def pos(key, title, who, boss=None, duties=None):
        O[key] = S.add_position(db, pid, {"job_title_code": title, "person_id": P[who], "from_date": d(-3),
                                          "reports_to": O[boss] if boss else "", "duties": duties}, cost)

    pos("pm", "PJM", "pm", duties="إدارة المشروع والتنسيق مع المالك والاستشاري")
    pos("site", "CNM", "site", "pm", "إدارة التنفيذ في الموقع ورفع التقارير اليومية")
    pos("plan", "PLE", "plan", "pm", "الجدول الزمني وتحديثاته الأسبوعية")
    pos("cce", "CCE", "cce", "pm", "متابعة التكلفة والمستخلصات")
    pos("acc", "ACC", "acc", "pm", "المستخلصات والصرف والتحصيل")
    pos("prc", "PRM", "prc", "pm", "طلبات الشراء وعروض الأسعار")
    pos("saf", "SAF", "saf", "pm")
    pos("srv", "SRV", "srv", "site")
    pos("frm", "FRM", "frm", "site", "توزيع الأطقم على الأعمال اليومية")
    pos("opr", "EQO", "opr", "frm")
    pos("drv", "DRV", "drv", "frm")

    # ---------- نطاق العمل وخطواته (3.7) ----------
    SCOPE = {  # البند: (الملخص، المستندات، [(الخطوة، الوزن، الجهة، المنفّذ، المعدة)])
        "A-01": ("سور مؤقت من ألواح الصاج بارتفاع 2.4 م حول الموقع.", ["site"],
                 [("تركيب القوائم", 60, "crew", "car", None), ("تركيب الألواح والبوابات", 40, "crew", "car", None)]),
        "A-02": ("تسوية الموقع وإزالة المخلفات.", ["site"],
                 [("التسوية بالمعدات", 70, "crew", "gen", "LDR"), ("التنظيف ونقل المخلفات", 30, "crew", "gen", None)]),
        "A-03": ("مكتب الموقع ودورات المياه والمستودع المؤقت.", ["site"],
                 [("توريد وتركيب الكرفانات", 60, "crew", "gen", None), ("توصيل الخدمات والتجهيز", 40, "crew", "gen", None)]),
        "A-04": ("الحفر العام حتى منسوب التأسيس حسب مخطط الحفر.", ["dig", "spc"],
                 [("الحفر حتى منسوب التأسيس", 80, "subcontractor", SUB_DIG, None),
                  ("تسوية القاع ونقل الناتج", 20, "crew", "gen", "EXC")]),
        "A-05": ("ردم بمواد مختارة على طبقات 25 سم مع الدمك.", ["dig", "spc"],
                 [("توريد مواد الردم", 30, "crew", "gen", None), ("الردم والدمك على طبقات", 70, "crew", "gen", "LDR")]),
        "B-01": ("خرسانة عادية بسماكة 10 سم تحت القواعد.", ["ftg", "spc"],
                 [("تجهيز القاع", 30, "crew", "cnc", None), ("صب خرسانة النظافة", 70, "crew", "cnc", "MIX")]),
        "B-02": ("خرسانة مسلحة للقواعد المنفصلة والرقاب.", ["ftg", "spc"],
                 [("نجارة الشدات", 20, "crew", "car", None), ("تركيب حديد التسليح", 30, "crew", "stl", None),
                  ("صب الخرسانة وهزها", 40, "crew", "cnc", "MIX"), ("المعالجة وفك الشدات", 10, "crew", "car", None)]),
        "B-03": ("خرسانة مسلحة لأعمدة الطوابق الثلاثة.", ["col", "spc"],
                 [("نجارة شدات الأعمدة", 30, "crew", "car", None), ("تركيب حديد الأعمدة", 35, "crew", "stl", None),
                  ("الصب والهز", 25, "crew", "cnc", "VIB"), ("فك الشدات والمعالجة", 10, "crew", "car", None)]),
        "B-04": ("خرسانة مسلحة للكمرات والبلاطات للطوابق الثلاثة.", ["col", "spc"],
                 [("شدات الكمرات والبلاطات", 30, "crew", "car", None), ("حديد التسليح", 30, "crew", "stl", None),
                  ("صب الخرسانة بالمضخة", 30, "crew", "cnc", "PMP"), ("فك الشدات والمعالجة", 10, "crew", "car", None)]),
        "C-01": ("بناء الجدران الخارجية ببلوك أسمنتي 25 سم.", ["blk", "spm"],
                 [("بناء الطابق الأرضي", 30, "crew", "mas", None), ("بناء الطابق الأول", 30, "crew", "mas", None),
                  ("بناء الطابق الثاني", 30, "crew", "mas", None), ("التكحيل والتنظيف", 10, "crew", "mas", None)]),
        "C-02": ("بناء القواطع الداخلية ببلوك أسمنتي 10 سم.", ["blk", "spm"],
                 [("قواطع الطابق الأرضي", 35, "crew", "mas2", None), ("قواطع الطابق الأول", 35, "crew", "mas2", None),
                  ("قواطع الطابق الثاني", 30, "crew", "mas2", None)]),
        "C-03": ("عزل مائي للأسطح بلفائف بيتومينية 4 مم.", ["ins", "spm"],
                 [("تحضير السطح والبرايمر", 30, "crew", "ins", None), ("فرد اللفائف", 50, "crew", "ins", None),
                  ("اختبار الغمر", 20, "crew", "ins", None)]),
        "C-04": ("عزل حراري للأسطح بألواح البوليسترين.", ["ins", "spm"],
                 [("تركيب ألواح العزل", 70, "crew", "ins", None), ("طبقة الحماية", 30, "crew", "ins", None)]),
        "D-01": ("توريد وتركيب لوحات التوزيع.", ["ele"],
                 [("توريد اللوحات", 50, "subcontractor", SUB_ELE, None), ("التركيب والتوصيل", 50, "subcontractor", SUB_ELE, None)]),
        "D-02": ("تمديدات الإنارة والقوى للطوابق الثلاثة.", ["ele"],
                 [("مواسير الأسقف", 30, "subcontractor", SUB_ELE, None), ("مواسير الجدران", 30, "subcontractor", SUB_ELE, None),
                  ("سحب الكابلات", 40, "subcontractor", SUB_ELE, None)]),
        "D-03": ("توريد وتركيب وحدات التكييف المنفصلة.", ["mep"],
                 [("توريد الوحدات", 50, "crew", "mep", None), ("التركيب والتشغيل", 50, "crew", "mep", None)]),
        "D-04": ("شبكة التغذية والصرف الصحي.", ["mep"],
                 [("تمديدات التغذية", 40, "crew", "mep", None), ("تمديدات الصرف", 40, "crew", "mep", None),
                  ("الاختبار", 20, "crew", "mep", None)]),
        "E-01": ("أرضيات بورسلان للطوابق الثلاثة.", ["fin"],
                 [("توريد البورسلان", 40, "crew", "mas2", None), ("التركيب والترويب", 60, "crew", "mas2", None)]),
        "E-02": ("دهانات داخلية وخارجية.", ["fin"],
                 [("المعجون والتجهيز", 40, "crew", "gen", None), ("الدهان", 60, "crew", "gen", None)]),
        "E-03": ("أبواب خشبية ونوافذ ألمنيوم.", ["fin", "arch"],
                 [("التوريد", 50, "crew", "car", None), ("التركيب", 50, "crew", "car", None)]),
        "A-06": ("رش مبيد النمل الأبيض تحت البلاطات وحول القواعد.", ["dig", "spc"],
                 [("رش التربة", 70, "crew", "ins", None), ("الفحص والتوثيق", 30, "crew", "ins", None)]),
        "A-07": ("اختبارات التربة والخرسانة طوال التنفيذ في مختبر معتمد.", ["site", "spc"],
                 [("اختبارات التربة", 30, "subcontractor", SUB_LAB, None),
                  ("اختبارات الخرسانة أثناء الصب", 50, "subcontractor", SUB_LAB, None),
                  ("الاختبارات النهائية", 20, "subcontractor", SUB_LAB, None)]),
        "B-05": ("خرسانة مسلحة لسلالم الطوابق الثلاثة.", ["col", "spc"],
                 [("الشدات", 35, "crew", "car", None), ("الحديد", 35, "crew", "stl", None), ("الصب", 30, "crew", "cnc", None)]),
        "B-06": ("خزان مياه أرضي من الخرسانة المسلحة سعة 100 م3.", ["ftg", "spc"],
                 [("الحفر والشدات", 30, "subcontractor", SUB_DIG2, None), ("الحديد والصب", 50, "subcontractor", SUB_DIG2, None),
                  ("العزل واختبار الامتلاء", 20, "subcontractor", SUB_DIG2, None)]),
        "B-07": ("عزل بيتوميني للقواعد والرقاب والميد.", ["ftg", "spm"],
                 [("الدهان الأول", 50, "crew", "ins", None), ("الدهان الثاني والحماية", 50, "crew", "ins", None)]),
        "C-05": ("لياسة داخلية للجدران والقواطع.", ["blk", "fin"],
                 [("الطرطشة والبؤج", 30, "crew", "mas2", None), ("اللياسة", 70, "crew", "mas2", None)]),
        "C-06": ("لياسة خارجية للواجهات غير المكسوة بالحجر.", ["blk", "fac"],
                 [("الشبك والطرطشة", 30, "crew", "mas", None), ("اللياسة", 70, "crew", "mas", None)]),
        "D-05": ("نظام إنذار الحريق المعنون.", ["fire"],
                 [("التمديدات", 50, "subcontractor", SUB_ELE, None), ("الأجهزة والتشغيل", 50, "subcontractor", SUB_ELE, None)]),
        "D-06": ("شبكة رشاشات الإطفاء وصناديق الحريق.", ["fire"],
                 [("التمديدات", 60, "crew", "mep", None), ("الرشاشات والاختبار", 40, "crew", "mep", None)]),
        "D-07": ("مصعد ركاب 8 أشخاص لثلاث وقفات.", ["arch", "elv"],
                 [("التوريد", 50, "subcontractor", SUB_ELV, None), ("التركيب والتشغيل", 50, "subcontractor", SUB_ELV, None)]),
        "D-08": ("مولد احتياطي 250 ك.ف.أ مع لوحة التحويل.", ["ele"],
                 [("التوريد", 60, "subcontractor", SUB_ELE, None), ("التركيب والتشغيل", 40, "subcontractor", SUB_ELE, None)]),
        "D-09": ("شبكات البيانات وكاميرات المراقبة.", ["ele"],
                 [("التمديدات", 50, "subcontractor", SUB_ELE, None), ("الأجهزة والبرمجة", 50, "subcontractor", SUB_ELE, None)]),
        "E-05": ("أسقف مستعارة من ألواح الجبس.", ["fin"],
                 [("الهيكل المعدني", 40, "crew", "car", None), ("الألواح والتشطيب", 60, "crew", "car", None)]),
        "E-06": ("كسوة الواجهات بالحجر الطبيعي.", ["fac"],
                 [("توريد الحجر", 40, "crew", "mas", None), ("التركيب", 60, "crew", "mas", None)]),
        "E-07": ("سيراميك جدران وأرضيات الحمامات والمطابخ.", ["fin"],
                 [("التوريد", 40, "crew", "mas2", None), ("التركيب", 60, "crew", "mas2", None)]),
        "E-08": ("درابزين ستانلس ستيل للسلالم.", ["arch"],
                 [("التوريد", 50, "crew", "car", None), ("التركيب", 50, "crew", "car", None)]),
        "E-04": ("التنظيف النهائي وتسليم المشروع للمالك.", ["arch"],
                 [("التنظيف النهائي", 50, "crew", "gen", None), ("الاستلام الابتدائي", 50, "crew", "gen", None)]),
    }
    EQ = {"LDR": E["ldr"], "EXC": E["exc"], "MIX": E["mix"], "VIB": E["vib"], "PMP": E["pmp"]}
    STEPS = {}
    for ref, (summary, docs, steps) in SCOPE.items():
        W.save_scope(db, pid, I[ref], MultiDict([("summary", summary), ("includes", summary), ("excludes", "")]
                                                + [("documents", str(DOC[x])) for x in docs]), eng)
        STEPS[ref] = []
        for name, w, party, who, eqp in steps:
            form = {"name": name, "weight_pct": str(w), "party": party, "equipment_id": str(EQ[eqp]) if eqp else ""}
            form["crew_id" if party == "crew" else "entity_id"] = str(K[who] if party == "crew" else who)
            STEPS[ref].append(W.add_step(db, pid, I[ref], form, eng)[0])
        W.review_scope(db, pid, I[ref], cost)

    # ---------- الجدول الزمني وجدول الدفعات (3.4، 3.2) ----------
    PLAN = [  # (البند، النشاط، البدء، الانتهاء، السابق)
        ("A-01", "تسوير الموقع", 0, 6, []), ("A-02", "تسوية الموقع وتنظيفه", 0, 6, []),
        ("A-03", "تجهيز مكتب الموقع ومرافقه", 2, 13, []), ("A-07", "اختبارات التربة والخرسانة", 5, 330, []),
        ("A-04", "الحفر العام للأساسات", 7, 27, ["A-02"]), ("A-05", "الردم بمواد مختارة", 28, 41, ["A-04"]),
        ("A-06", "رش مبيد النمل الأبيض", 40, 44, ["A-04"]), ("B-01", "خرسانة النظافة", 42, 46, ["A-04"]),
        ("B-02", "خرسانة القواعد المسلحة", 42, 69, ["A-04"]), ("B-06", "الخزان الأرضي", 50, 90, ["A-04"]),
        ("B-07", "عزل الأساسات", 70, 84, ["B-02"]), ("B-03", "خرسانة الأعمدة", 70, 97, ["B-02"]),
        ("B-04", "خرسانة الكمرات والبلاطات", 98, 150, ["B-03"]), ("B-05", "خرسانة السلالم", 105, 150, ["B-03"]),
        ("C-01", "بلوك الجدران الخارجية", 120, 195, ["B-03"]), ("C-02", "بلوك القواطع الداخلية", 151, 211, ["B-04"]),
        ("C-03", "العزل المائي للأسطح", 151, 170, ["B-04"]), ("C-04", "العزل الحراري للأسطح", 171, 190, ["C-03"]),
        ("D-02", "التمديدات الكهربائية", 151, 241, ["B-04"]), ("D-04", "شبكة السباكة والتصريف", 165, 256, ["B-04"]),
        ("C-06", "اللياسة الخارجية", 196, 240, ["C-01"]), ("D-06", "نظام إطفاء الحريق", 200, 280, ["B-04"]),
        ("D-01", "لوحات التوزيع", 212, 241, ["C-02"]), ("C-05", "اللياسة الداخلية", 212, 270, ["C-02"]),
        ("E-06", "كسوة الواجهات بالحجر", 241, 320, ["C-06"]), ("D-03", "وحدات التكييف", 242, 287, ["D-02"]),
        ("D-05", "نظام إنذار الحريق", 242, 290, ["D-02"]), ("D-07", "المصعد", 250, 320, ["B-04"]),
        ("D-09", "الشبكات وكاميرات المراقبة", 260, 310, ["D-02"]), ("E-01", "أرضيات البورسلان", 257, 303, ["C-02", "D-04"]),
        ("E-05", "الأسقف المستعارة", 271, 320, ["C-05"]), ("E-07", "سيراميك الحمامات والمطابخ", 271, 303, ["C-05"]),
        ("E-02", "الدهانات الداخلية والخارجية", 273, 333, ["C-05"]), ("E-03", "تركيب الأبواب والنوافذ", 287, 333, ["C-01"]),
        ("D-08", "المولد الاحتياطي", 290, 320, ["D-01"]), ("E-08", "درابزين السلالم", 300, 330, ["B-05"]),
        ("E-04", "التنظيف النهائي والتسليم", 334, 364,
         ["E-02", "E-01", "E-03", "D-03", "E-05", "E-06", "E-07", "E-08", "D-05", "D-06", "D-07", "D-08", "D-09", "A-07"]),
    ]
    A, PLANNED = {}, {}
    for ref, name, ps, pf, preds in PLAN:
        A[ref] = T.add_activity(db, pid, {"name": name, "link": f"item-{I[ref]}", "planned_start": d(ps), "planned_finish": d(pf),
                                          "predecessors": [str(A[x]) for x in preds]}, eng)[0]
        PLANNED[ref] = (ps, pf, preds, name)
    for desc, ref, share in (("دفعة الأعمال التمهيدية والحفر", "A-05", 5), ("دفعة الأساسات", "B-02", 7),
                             ("دفعة الهيكل الخرساني", "B-04", 13), ("دفعة المباني والعزل", "C-02", 15),
                             ("دفعة الأعمال الكهروميكانيكية", "D-03", 25), ("دفعة التشطيبات", "E-02", 30),
                             ("دفعة التسليم الابتدائي", "E-04", 5)):
        T.add_milestone(db, pid, {"description": desc, "activity_id": str(A[ref]), "share_pct": str(share)}, cost)
    T.review(db, pid, cost)
    T.approve(db, pid, director)
    stamp("projects", pid, schedule_reviewed_at=ts(-8), schedule_approved_at=ts(-7))
    with tx(db):
        db.execute("UPDATE baselines SET approved_at = ? WHERE project_id = ?", (ts(-7), pid))

    # ---------- التخصيصات (3.6) ----------
    ACTUAL = {  # البند: (البدء الفعلي، الانتهاء الفعلي أو None، نسبة الكمية المنفذة حتى أمس، أيام انتهاء الخطوات)
        "A-01": (0, 6, 1.0, None), "A-02": (0, 7, 1.0, None), "A-03": (2, 14, 1.0, None), "A-04": (8, 33, 1.0, None),
        "A-05": (34, 46, 1.0, None), "B-01": (44, 48, 1.0, None), "B-02": (46, 77, 1.0, None), "B-03": (78, 104, 1.0, None),
        "B-04": (105, 162, 1.0, None), "C-01": (128, None, 0.36, [160]), "A-06": (40, 44, 1.0, None),
        "A-07": (5, None, 0.8, [12, 160]), "B-05": (110, None, 0.75, [130, 150]), "B-06": (52, None, 0.85, [70, 95]), "B-07": (72, 88, 1.0, None), "C-02": (166, None, 0.08, []),
        "C-03": (160, None, 0.85, [165, 171]), "D-02": (160, None, 0.3, [172]), "D-04": (172, None, 0.05, []),
    }

    def snap(n, back=True):
        while not working(n):
            n += -1 if back else 1
        return n

    DONE = {}  # يوم انتهاء كل خطوة
    for ref, (a_s, a_f, _frac, fixed) in ACTUAL.items():
        a_s = snap(a_s, back=False)
        if fixed is None:
            n = len(STEPS[ref])
            fixed = [a_s + round((k + 1) * (a_f - a_s) / n) for k in range(n)]
        for sid, day in zip(STEPS[ref], fixed):
            day = max(a_s, snap(min(day, LAST)))
            DONE.setdefault(day, []).append(sid)
    ACT_DAYS = {}
    for ref, (a_s, a_f, _frac, _fx) in ACTUAL.items():
        ACT_DAYS[ref] = [n for n in range(a_s, min(a_f if a_f is not None else LAST, LAST) + 1) if working(n)]

    ALLOC = []  # (المعرّف، البند، الساعات، تعطل)

    def alloc(kind, rid, ref, step_no, start, end, prod, pct=100, hours=8, sup="site", **kw):
        form = {"resource_kind": kind, f"resource_id_{kind}": rid, "boq_item_id": I[ref], "step_id": STEPS[ref][step_no],
                "activity_id": A[ref], "supervisor_id": O[sup], "from_date": d(start), "to_date": d(end), "days_per_week": "5",
                "hours_per_day": "8", "allocation_pct": str(pct), "productivity": str(prod), **kw}
        aid = S.add_allocation(db, pid, form, cost)[0]
        ALLOC.append((aid, ref, hours, kind))
        return aid

    alloc("crew", K["car"], "A-01", 0, 0, 6, 40)
    alloc("crew", K["gen"], "A-02", 0, 0, 7, 300, pct=50, hours=4)
    alloc("equipment", E["ldr"], "A-02", 0, 0, 7, 300)
    alloc("person", P["srv"], "A-02", 0, 0, 7, 300, pct=50, hours=4, position_id=O["srv"])
    alloc("crew", K["gen"], "A-03", 0, 2, 14, 0.2, pct=50, hours=4)
    alloc("subcontractor", SUB_DIG, "A-04", 0, 8, 33, 100, unit_rate="15", notes="الحفر بمعدات المقاول وتشغيله")
    alloc("equipment", E["exc"], "A-04", 1, 8, 33, 100)
    alloc("equipment", E["dmp"], "A-04", 1, 8, 33, 100)
    alloc("person", P["opr"], "A-04", 1, 8, 33, 100, sup="frm", position_id=O["opr"])
    alloc("crew", K["gen"], "A-04", 1, 15, 33, 100, pct=50, hours=4)
    alloc("crew", K["gen"], "A-05", 1, 34, 46, 60)
    alloc("equipment", E["ldr"], "A-05", 1, 34, 46, 60)
    alloc("crew", K["cnc"], "B-01", 1, 44, 48, 20, pct=50, hours=4)
    alloc("equipment", E["mix"], "B-01", 1, 44, 48, 20, pct=50, hours=4)
    alloc("crew", K["car"], "B-02", 0, 46, 77, 6)
    alloc("crew", K["stl"], "B-02", 1, 46, 77, 6)
    alloc("crew", K["cnc"], "B-02", 2, 49, 77, 6, pct=50, hours=4)
    alloc("equipment", E["mix"], "B-02", 2, 49, 77, 6, pct=50, hours=4)
    alloc("equipment", E["vib"], "B-02", 2, 46, 77, 6)
    alloc("crew", K["car"], "B-03", 0, 78, 104, 4)
    alloc("crew", K["stl"], "B-03", 1, 78, 104, 4)
    alloc("crew", K["cnc"], "B-03", 2, 78, 104, 4, pct=50, hours=4)
    alloc("equipment", E["mix"], "B-03", 2, 78, 104, 4, pct=50, hours=4)
    alloc("equipment", E["vib"], "B-03", 2, 78, 104, 4)
    alloc("crew", K["car"], "B-04", 0, 105, 162, 5, pct=70, hours=6)
    alloc("crew", K["stl"], "B-04", 1, 105, 162, 5, pct=70, hours=6)
    alloc("crew", K["cnc"], "B-04", 2, 105, 162, 5, pct=70, hours=6)
    alloc("crew", K["car"], "B-05", 0, 110, 158, 1, pct=30, hours=2)
    alloc("crew", K["stl"], "B-05", 1, 110, 158, 1, pct=30, hours=2)
    alloc("crew", K["cnc"], "B-05", 2, 110, 158, 1, pct=30, hours=2)
    alloc("crew", K["ins"], "A-06", 0, 40, 44, 100)
    alloc("subcontractor", SUB_LAB, "A-07", 0, 5, 330, 0.01, unit_rate="15000", notes="المختبر يأخذ العينات ويرسل النتائج")
    alloc("subcontractor", SUB_DIG2, "B-06", 0, 52, 95, 2, unit_rate="900", notes="الخزان بالمواد والعمالة")
    alloc("crew", K["ins"], "B-07", 0, 72, 88, 40)
    alloc("equipment", E["mix"], "B-04", 2, 105, 162, 5)
    alloc("equipment", E["vib"], "B-04", 2, 105, 162, 5)
    alloc("equipment", E["pmp"], "B-04", 2, 105, 162, 5, hours=0)
    alloc("person", P["site"], "B-04", 2, 105, 162, 5, pct=50, hours=4, sup="pm", position_id=O["site"])
    alloc("crew", K["mas"], "C-01", 0, 128, 205, 15)
    alloc("person", P["frm"], "C-01", 0, 128, 205, 15, pct=50, hours=4, position_id=O["frm"])
    alloc("crew", K["mas2"], "C-02", 0, 166, 215, 11)
    alloc("crew", K["ins"], "C-03", 0, 160, 174, 45)
    alloc("subcontractor", SUB_ELE, "D-02", 0, 160, 241, 15, unit_rate="30", notes="التمديدات بعمالة المقاول وأدواته")
    alloc("crew", K["mep"], "D-04", 0, 172, 256, 0.02)
    planned_only = [alloc("crew", K["ins"], "C-04", 0, 176, 195, 25), alloc("equipment", E["gen"], "D-04", 0, 176, 256, 0.02)]
    for aid, *_rest in ALLOC:
        if aid not in planned_only:
            S.approve_allocation(db, pid, aid, director)

    # ---------- محضر بدء التنفيذ (4.1) ----------
    for el in G.ELEMENTS:
        G.review_element(db, pid, {"element": el, "decision": "approved"}, pm)
    G.start_execution(db, pid, pm)
    stamp("projects", pid, kickoff_at=ts(-2))
    with tx(db):
        db.execute("UPDATE kickoff_reviews SET decided_at = ? WHERE project_id = ?", (ts(-3), pid))

    # ---------- التقارير اليومية لكل أيام العمل حتى أمس (4.3، 4.4) ----------
    ISSUES = {9: "تعطل الحفار الرئيسي وانتظار قطعة الغيار.", 10: "الحفار متوقف لليوم الثاني.",
              11: "عاد الحفار للعمل ظهرًا.", 52: "انتظار اعتماد الاستشاري لمخطط تسليح القاعدة ق3 المعدّل.",
              53: "ما زال مخطط التسليح المعدّل عند الاستشاري.", 140: "نقص في عمالة المباني بسبب إجازات.",
              141: "نقص في عمالة المباني.", 170: "اختبار الغمر للعزل المائي جارٍ."}
    IDLE = {9: "breakdown", 10: "breakdown", 11: "breakdown"}
    RETURN = {30: "الكمية المنفذة للحفر أعلى من محضر القياس المعتمد.", 66: "ساعات طاقم الحديد غير مطابقة لكشف الحضور.",
              108: "لم تُسجَّل الخرسانة المصبوبة اليوم.", 147: "الخطوة المسجلة لم تنتهِ فعلًا حسب زيارة الموقع."}
    RID = {}
    days = [n for n in range(0, LAST + 1) if working(n)]
    for n in days:
        if n == 120:
            AU.set_level(db, eng, "restricted", "تأخر رفع التقارير اليومية يومين أو أكثر لثلاثة أسابيع متتالية.", cost)
            with tx(db):
                db.execute("UPDATE authority_changes SET set_at = ? WHERE id = (SELECT MAX(id) FROM authority_changes)", (ts(120),))
                db.execute("UPDATE engineer_levels SET set_at = ? WHERE user_id = ?", (ts(120), eng))
        if n == 150:
            AU.set_level(db, eng, "full", "انتظام رفع التقارير ودقة البيانات خلال فترة التقييد.", cost)
            with tx(db):
                db.execute("UPDATE authority_changes SET set_at = ? WHERE id = (SELECT MAX(id) FROM authority_changes)", (ts(150),))
                db.execute("UPDATE engineer_levels SET set_at = ? WHERE user_id = ?", (ts(150), eng))
        active = [ref for ref, ds in ACT_DAYS.items() if n in ds]
        if not active:
            continue
        form = MultiDict([("report_date", d(n))] + [("activities", str(A[ref])) for ref in active]
                         + [("steps", str(s)) for s in DONE.get(n, [])])
        for ref in active:  # الكمية موزعة بالتساوي على أيام العمل، والباقي في آخر يوم
            total, k = round(QTY[ref] * ACTUAL[ref][2] * 1000), ACT_DAYS[ref].index(n)
            q = total // len(ACT_DAYS[ref]) + (total % len(ACT_DAYS[ref]) if k == len(ACT_DAYS[ref]) - 1 else 0)
            if q:
                form.add(f"qty_{I[ref]}", f"{q / 1000:.3f}")
        for aid, ref, hours, kind in ALLOC:
            if ref in active and hours and kind != "subcontractor":
                form.add(f"hours_{aid}", str(hours))
                if kind == "equipment" and n in IDLE and ref == "A-04":
                    form.add(f"idle_{aid}", IDLE[n])
        if n % 7 == 4 and any(ref == "B-04" for ref in active):
            form.add(f"hours_{next(a for a, r, h, k in ALLOC if r == 'B-04' and h == 0)}", "6")  # يوم صب بالمضخة
        if n in ISSUES:
            form.add("issues", ISSUES[n])
        author = pm if dd(n).weekday() == 3 else eng
        rid = RID[n] = Y.create_report(db, pid, form, author)[0]
        late = 2 if author == eng and 96 <= n < 118 else 0
        stamp("daily_reports", rid, created_at=ts(n + late, 15))
        if n in RETURN:
            Y.return_report(db, pid, rid, RETURN[n], cost)
            Y.update_report(db, pid, rid, form, author)
        if author == eng and 120 <= n < 150:
            Y.pm_check(db, pid, rid, pm)
            stamp("daily_reports", rid, pm_checked_at=ts(n + late + 1, 9))
        Y.approve_report(db, pid, rid, cost)
        stamp("daily_reports", rid, reviewed_at=ts(n + late + 1, 11))
    print("daily reports:", one("SELECT COUNT(*) FROM daily_reports WHERE project_id = ?", pid))

    # ---------- المشتريات وأوامر الشراء وعقود الباطن (4.2) ----------
    def bought(ref, kind, qty, scope, docs, quotes, day, pick=None, reason=""):
        rid, _ = Q.create_request(db, pid, MultiDict([("kind", kind), ("boq_item_id", str(I[ref])), ("scope", scope),
                                                      ("qty", str(qty)), ("needed_on", d(day + 7))]
                                                     + [("documents", str(DOC[x])) for x in docs]
                                                     + [("steps", str(s)) for s in STEPS[ref]]), eng)
        for ent, price, ev in quotes:
            Q.add_quote(db, pid, rid, {"entity_id": str(ent), "unit_price": str(price), "duration_days": "7",
                                       "payment_terms": "30 يومًا من الاستلام", "valid_until": (TODAY + timedelta(days=30)).isoformat(),
                                       "evaluation": ev}, buyer)
        qid = (db.execute("SELECT id FROM quotes WHERE request_id = ? AND entity_id = ?", (rid, pick)).fetchone()[0] if pick
               else Q.comparison(db, Q.request(db, pid, rid))["lowest"])
        Q.select_quote(db, pid, rid, qid, reason, pm)
        code = Q.cc_approve(db, pid, rid, cost) or Q.director_approve(db, pid, rid, director)
        stamp("purchase_requests", rid, created_at=ts(day - 4))
        cid = one("SELECT id FROM commitments WHERE code = ?", code)
        stamp("commitments", cid, issued_at=ts(day))
        return cid

    C_, N_ = "compliant", "notes"
    PO = {
        "lab": bought("A-07", "subcontract", 1, "اختبارات التربة والخرسانة طوال المشروع في مختبر معتمد", ["spc"],
                      [(SUB_LAB, 15000, C_), (SUB_DIG2, 17500, N_)], 2),
        "dig": bought("A-04", "subcontract", 1800, "حفر عام للأساسات بمعدات المقاول ونقل الناتج", ["dig"],
                      [(SUB_DIG, 22, C_), (SUB_DIG2, 24, C_)], 5),
        "fill": bought("A-05", "material", 700, "توريد مواد ردم مختارة مطابقة للمواصفات", ["dig", "spc"],
                       [(SUP_SND, 14, C_), (SUP_RMX, 15.5, C_)], 26),
        "lean": bought("B-01", "material", 70, "توريد خرسانة جاهزة C15 للنظافة", ["ftg", "spc"],
                       [(SUP_RMX, 240, C_), (SUP_RMX2, 255, C_)], 38),
        "ftg_c": bought("B-02", "material", 160, "توريد خرسانة جاهزة C30 للقواعد", ["ftg", "spc"],
                        [(SUP_RMX, 290, C_), (SUP_RMX2, 298, C_)], 40),
        "ftg_s": bought("B-02", "material", 160, "توريد حديد تسليح للقواعد (لكل م3 خرسانة)", ["ftg", "shd"],
                        [(SUP_STL, 430, C_), (SUP_STL2, 445, N_)], 41),
        "tank": bought("B-06", "subcontract", 60, "تنفيذ الخزان الأرضي كاملًا بالمواد والعمالة", ["ftg"],
                       [(SUB_DIG2, 900, C_), (SUB_DIG, 950, C_)], 45),
        "bit": bought("B-07", "material", 600, "توريد عزل بيتوميني للأساسات", ["ftg", "spm"],
                      [(SUP_INS, 12, C_), (SUP_BLK, 13, C_)], 66),
        "col_s": bought("B-03", "material", 85, "توريد حديد تسليح للأعمدة (لكل م3 خرسانة)", ["col"],
                        [(SUP_STL, 450, C_), (SUP_STL2, 465, C_)], 72),
        "col_c": bought("B-03", "material", 85, "توريد خرسانة جاهزة C35 للأعمدة", ["col", "spc"],
                        [(SUP_RMX, 300, C_), (SUP_RMX2, 308, C_)], 74),
        "slb_c": bought("B-04", "material", 220, "توريد خرسانة جاهزة C35 للكمرات والبلاطات مع الضخ", ["col", "spc"],
                        [(SUP_RMX2, 292, "non_compliant"), (SUP_RMX, 295, C_)], 100, pick=SUP_RMX,
                        reason="العرض الأقل غير مطابق: لا يشمل الضخ ولا شهادات الاختبار."),
        "slb_s": bought("B-04", "material", 220, "توريد حديد تسليح للكمرات والبلاطات (لكل م3 خرسانة)", ["col"],
                        [(SUP_STL, 420, C_), (SUP_STL2, 435, C_)], 100),
        "stair_s": bought("B-05", "material", 26, "توريد حديد تسليح للسلالم (لكل م3 خرسانة)", ["col"],
                          [(SUP_STL, 450, C_), (SUP_STL2, 465, C_)], 104),
        "stair_c": bought("B-05", "material", 26, "توريد خرسانة جاهزة C35 للسلالم", ["col", "spc"],
                          [(SUP_RMX, 300, C_), (SUP_RMX2, 310, C_)], 106),
        "blk": bought("C-01", "material", 1100, "توريد بلوك أسمنتي 25 سم مع المونة", ["blk", "spm"],
                      [(SUP_BLK, 45, C_), (SUP_RMX2, 47, C_)], 122),
        "wpf": bought("C-03", "material", 480, "توريد لفائف عزل مائي 4 مم", ["ins", "spm"],
                      [(SUP_INS, 32, C_), (SUP_BLK, 34, N_)], 152),
        "ele": bought("D-02", "subcontract", 1200, "تمديدات الإنارة والقوى للطوابق الثلاثة", ["ele"],
                      [(SUB_ELE, 90, C_), (SUB_ELE2, 96, C_)], 155),
    }

    # ---------- الاستلام والفواتير والمستخلصات والصرف (4.7) ----------
    GRN = []

    def receive(key, day, qty):
        code = X.add_receipt(db, pid, {"commitment_id": str(PO[key]), "received_on": d(day), "qty": str(qty)}, eng)
        gid = one("SELECT id FROM goods_receipts WHERE code = ?", code)
        stamp("goods_receipts", gid, created_at=ts(day, 13))
        GRN.append((key, gid, day))

    def payable(form, day, approve=True, paid=None):
        code = X.raise_payable(db, pid, form, eng)
        xid = one("SELECT id FROM payables WHERE code = ?", code)
        stamp("payables", xid, created_at=ts(day, 12))
        if approve:
            X.approve(db, pid, xid, cost)
            stamp("payables", xid, cc_at=ts(day + 1))
            if one("SELECT status FROM payables WHERE id = ?", xid) == "cc_approved":
                X.approve(db, pid, xid, director, director=True)
                stamp("payables", xid, dir_at=ts(day + 2))
        if paid is not None:
            X.pay(db, pid, xid, {"paid_on": d(paid), "paid_ref": f"TRX-{xid:05d}"}, acc)
        return xid

    def invoice(key, qty, day, ref, **kw):
        return payable({"commitment_id": str(PO[key]), "qty": str(qty), "vendor_ref": ref}, day, **kw)

    receive("bit", 70, 600)
    invoice("bit", 600, 71, "INS-0655", paid=100)
    receive("stair_s", 108, 26)
    invoice("stair_s", 26, 110, "STL-5733", paid=140)
    receive("stair_c", 120, 26)
    invoice("stair_c", 26, 122, "RMX-9122", paid=152)
    receive("fill", 34, 400)
    receive("fill", 38, 300)
    invoice("fill", 700, 40, "SND-2214", paid=70)
    receive("lean", 45, 70)
    invoice("lean", 70, 47, "RMX-8812", paid=78)
    receive("ftg_s", 48, 160)
    invoice("ftg_s", 160, 50, "STL-5531", paid=80)
    receive("ftg_c", 60, 80)
    receive("ftg_c", 72, 80)
    invoice("ftg_c", 80, 62, "RMX-8890", paid=92)
    invoice("ftg_c", 80, 74, "RMX-8951", paid=104)
    receive("col_s", 79, 85)
    invoice("col_s", 85, 81, "STL-5602", paid=111)
    receive("col_c", 90, 85)
    invoice("col_c", 85, 92, "RMX-9033", paid=122)
    receive("slb_s", 108, 220)
    invoice("slb_s", 220, 110, "STL-5710", paid=140)
    receive("slb_c", 125, 110)
    receive("slb_c", 155, 110)
    invoice("slb_c", 110, 127, "RMX-9140", paid=157)
    invoice("slb_c", 110, 157, "RMX-9302")
    receive("blk", 127, 400)
    receive("blk", 160, 300)
    invoice("blk", 400, 130, "BLK-1180", paid=160)
    invoice("blk", 300, 163, "BLK-1244", approve=False)
    receive("wpf", 158, 480)
    invoice("wpf", 480, 160, "INS-0712")

    SPC = []

    def certificate(key, qty, start, end, day, **kw):
        SPC.append((end, day))
        return payable({"commitment_id": str(PO[key]), "qty": str(qty), "period_from": d(start), "period_to": d(end),
                        "retention_pct": "10"}, day, **kw)

    certificate("dig", 1000, 8, 20, 22, paid=52)
    certificate("dig", 800, 21, 33, 35, paid=65)
    certificate("tank", 30, 52, 75, 77, paid=100)
    certificate("tank", 20, 76, 95, 97, paid=125)
    certificate("lab", 0.5, 5, 90, 92, paid=120)
    certificate("ele", 350, 160, LAST - 1, LAST)

    # ---------- مستخلصات المالك والتحصيل (4.8) ----------
    def ipc(ref, day, submit, certify=None, amount=None, collect=None):
        due = next(x for x in B.due_without_certificate(db, pid) if x["m"]["activity_id"] == A[ref])
        code = B.create(db, pid, {"milestone_id": str(due["m"]["id"]), "period_to": d(day)}, pm)
        oid = one("SELECT id FROM owner_certificates WHERE code = ?", code)
        stamp("owner_certificates", oid, created_at=ts(day))
        B.advance(db, pid, oid, "agree", {}, cost)
        B.advance(db, pid, oid, "submit", {"on": d(submit)}, pm)
        if certify is not None:
            B.advance(db, pid, oid, "certify", {"on": d(certify), "amount": amount}, pm)
        if collect is not None:
            B.advance(db, pid, oid, "collect", {"on": d(collect)}, acc)

    ipc("A-05", 47, 49, 63, "200,000", 95)
    ipc("B-02", 78, 80, 98, "275,000", 134)
    ipc("B-04", 163, 165, 172, "520,000")

    # ---------- طلبات التغيير (4.9) ----------
    def cr(kind, source, desc, ref, amount, days, day):
        code = CH.create(db, pid, MultiDict([("kind", kind), ("source", source), ("description", desc), ("items", str(I[ref])),
                                             (f"amount_{I[ref]}", amount), ("days_impact", str(days))]), eng)
        cid = one("SELECT id FROM change_requests WHERE code = ?", code)
        stamp("change_requests", cid, created_at=ts(day))
        return cid

    c1 = cr("internal", "company", "زيادة سماكة خرسانة النظافة إلى 10 سم حسب ملاحظة الاستشاري", "B-01", "8,000", 0, 40)
    CH.advance(db, pid, c1, pm, "pm")
    CH.advance(db, pid, c1, cost, "cc")
    c2 = cr("contractual", "owner", "إضافة مظلات سيارات معدنية في الموقف الخارجي بطلب المالك", "E-04", "150,000", 12, 150)
    CH.advance(db, pid, c2, pm, "pm")
    CH.advance(db, pid, c2, cost, "cc")
    CH.advance(db, pid, c2, director, "director")
    cr("internal", "company", "تغيير بلوك القواطع إلى بلوك معزول لتحسين العزل الصوتي", "C-02", "18,000", 0, LAST - 1)
    v, _ = C.add_variation_order(db, con["id"], {"description": "استبدال الدهانات الخارجية بدهان مقاوم للحرارة بطلب الاستشاري",
                                                 "issued_on": d(120), "value_delta": "36,000", "days_delta": "0"}, cost)
    C.decide_variation_order(db, con["id"], v, "approved", "", director)

    # ---------- التأخير والإنذار المبكر والتعافي (4.5، 4.6) ----------
    G.set_overhead(db, pid, "4,500", cost)
    for act, days_, cause, who, day in (("A-04", "3", "تعطل الحفار الرئيسي وانتظار قطعة الغيار", "company", 15),
                                        ("B-02", "4", "تأخر اعتماد الاستشاري لمخطط تسليح القاعدة ق3 المعدّل", "consultant", 55),
                                        ("C-01", "6", "نقص عمالة المباني بسبب الإجازات", "company", 142)):
        code = G.record_delay(db, pid, {"activity_id": str(A[act]), "days": days_, "cause": cause, "responsible": who}, cost)
        stamp("delays", one("SELECT id FROM delays WHERE code = ?", code), created_at=ts(day))
    p1 = G.add_plan(db, pid, {"option": "overtime", "description": "وردية مسائية لطاقم المباني لمدة ثلاثة أسابيع",
                              "days_saved": "8", "extra_cost": "35,000"}, pm)
    p1 = one("SELECT id FROM recovery_plans WHERE code = ?", p1)
    G.decide_plan(db, pid, p1, "approve", "", cost)
    G.decide_plan(db, pid, p1, "approve", "", director, director=True)
    p2 = G.add_plan(db, pid, {"option": "resources", "description": "تشغيل طاقم المباني الثاني على القواطع بالتوازي",
                              "days_saved": "10", "extra_cost": "48,000"}, pm)
    G.decide_plan(db, pid, one("SELECT id FROM recovery_plans WHERE code = ?", p2), "approve", "", cost)

    # ---------- إعادة التخطيط بمراجعة خط الأساس (4.5) ----------
    T.reopen(db, pid, "تمديد المدة 12 يومًا بطلب التغيير لإضافة مظلات السيارات", director, str(c2))
    ps, pf, preds, name = PLANNED["E-04"]
    T.update_activity(db, pid, A["E-04"], {"name": name, "link": f"item-{I['E-04']}", "planned_start": d(ps + 12),
                                           "planned_finish": d(pf + 12), "predecessors": [str(A[x]) for x in preds]}, eng)
    T.review(db, pid, cost)
    T.approve(db, pid, director)

    # ---------- النسخ الموقّعة (قرار م. محمد) ----------
    if files.enabled():
        def sign(kind, doc_id, accept=True, back=None):
            code = one(f"SELECT code FROM {SG.DOCS[kind]} WHERE id = ?", doc_id)
            SG.upload(db, pid, kind, doc_id, io.BytesIO(pdf("AZM - signed copy (demo data)", code)), f"{code}.pdf", eng)
            sid = one("SELECT MAX(id) FROM signed_copies WHERE doc_kind = ? AND doc_id = ?", kind, doc_id)
            if back:
                SG.decide(db, pid, sid, False, back, cost)
                return sign(kind, doc_id, accept)
            if accept:
                SG.decide(db, pid, sid, True, "", cost)
                if one("SELECT status FROM signed_copies WHERE id = ?", sid) == "cc_ok":
                    SG.decide(db, pid, sid, True, "", director, director=True)
        for key, cid in PO.items():
            sign("commitment", cid, accept=key != "ele", back="التوقيع والختم غير واضحين في الصفحة الثانية." if key == "blk" else None)
        for xid in [r[0] for r in db.execute("SELECT id FROM payables WHERE project_id = ? AND kind = 'certificate' ORDER BY id",
                                             (pid,))][:2]:
            sign("payable", xid)
    else:
        print("file storage is off: signed copies skipped")

    # ---------- تقارير المهندس: نص وملفات PDF (قرار م. محمد 2026-10-26) ----------
    def report(kind, doc_id, day, text=None, title=None):
        data = pdf("AZM - engineer report (demo data)", title) if title and files.enabled() else None
        if not text and data is None:
            return
        AT.add(db, pid, kind, doc_id, text, io.BytesIO(data) if data else None, f"{title}.pdf" if data else None, eng)
        with tx(db):
            db.execute("UPDATE attachments SET created_at = ? WHERE id = (SELECT MAX(id) FROM attachments)", (ts(day, 16),))

    NAMES = {ref: name for ref, name, *_rest in PLAN}
    for n, rid in RID.items():
        code = one("SELECT code FROM daily_reports WHERE id = ?", rid)
        active = [NAMES[ref] for ref, ds in ACT_DAYS.items() if n in ds]
        steps = [r[0] for r in db.execute("SELECT s.name FROM dsr_steps x JOIN scope_steps s ON s.id = x.step_id "
                                          "WHERE x.report_id = ?", (rid,))]
        if steps:
            report("dsr", rid, n, "انتهت اليوم: " + "، ".join(steps) + ". استلمها مهندس الاستشاري بعد المعاينة، "
                   "ومحضر الاستلام مرفق.", f"{code} inspection record" if n % 3 == 0 else None)
        elif n in ISSUES:
            report("dsr", rid, n, ISSUES[n] + " أُبلغ مدير المشروع، والتفاصيل في التقرير الفني المرفق.", f"{code} technical note")
        elif dd(n).weekday() == 3:
            report("dsr", rid, n, f"ملخص الأسبوع حتى {d(n)}: العمل مستمر في " + "، ".join(active)
                   + ". لا حوادث، والطقس مناسب، ونسبة الحضور مطابقة لكشف العمالة.")
    for key, cid in PO.items():
        r = db.execute("SELECT r.id, r.code, r.qty_milli, r.unit, r.created_at FROM purchase_requests r JOIN commitments c "
                       "ON c.request_id = r.id WHERE c.id = ?", (cid,)).fetchone()
        day = (date.fromisoformat(str(r["created_at"])[:10]) - START).days
        report("pr", r["id"], day, f"حصر الكمية من المخطط المعتمد: {r['qty_milli'] / 1000:g} {r['unit']}، مع نسبة هالك محسوبة "
               "في سعر التوريد. العروض المستلمة راجعتها المشتريات.", f"{r['code']} quantity take-off"
               if key in ("ftg_c", "ftg_s", "slb_c", "slb_s", "tank", "ele") else None)
    report("cr", c1, 40, "ملاحظة الاستشاري على مخطط S-201 تطلب سماكة 10 سم لخرسانة النظافة بدل 7 سم، والفرق محسوب "
           "على كمية القواعد.")
    report("cr", c2, 150, "خطاب المالك يطلب مظلات سيارات معدنية لعدد 24 موقفًا، والسعر من عرض مقاول الباطن مع هامش الشركة.",
           "CR owner letter and quotation")
    for (end, day), xid in zip(SPC, [r[0] for r in db.execute(
            "SELECT id FROM payables WHERE project_id = ? AND kind = 'certificate' ORDER BY id", (pid,))]):
        code = one("SELECT code FROM payables WHERE id = ?", xid)
        report("payable", xid, day, f"الكمية من محضر القياس المعتمد من الاستشاري حتى {d(end)}، ومطابقة للكميات في التقارير "
               "اليومية المعتمدة.", f"{code} measurement sheet")
    for key, gid, day in GRN:
        report("grn", gid, day, "تم الاستلام ومطابقة الكمية لإشعار التسليم، وأُخذت العينات للمختبر.",
               f"{one('SELECT code FROM goods_receipts WHERE id = ?', gid)} mill certificate" if key.endswith("_s") else None)
    print("engineer reports:", one("SELECT COUNT(*) FROM attachments WHERE project_id = ?", pid),
          "| with PDF:", one("SELECT COUNT(*) FROM attachments WHERE project_id = ? AND storage_key IS NOT NULL", pid))

    from app import performance
    m = performance.indicators(db, pid)["project"]
    print("project:", pcode, "| BOQ:", one("SELECT SUM(amount) FROM boq_items WHERE project_id = ?", pid) / 100,
          "| progress:", m["progress"] / 100, "% | SPI:", m["spi"], "| CPI:", m["cpi"], "| status:", m["status"])
