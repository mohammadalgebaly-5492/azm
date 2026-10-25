"""يبني مثالًا حيًّا كاملًا عبر دوال المنصة نفسها: جهات، ومشروع بمليون ريال في خمس مراحل، وعقد بضمانات وتأمينات وأوامر تغيير.
الاستخدام (من مجلد المشروع): python scripts/demo_full.py <اسم مستخدم المنفّذ> [<اسم مستخدم المعتمِد لأوامر التغيير>]
يعمل على قاعدة البيانات التي يقرؤها wsgi.py: الحقيقية إذا وُجد .env.local، وإلا يُضبط DATABASE_URL فارغًا مع CC_DATABASE.
يضيف فقط ولا يحذف ولا يعدّل شيئًا موجودًا؛ وما سبق إنشاؤه من المثال يُعاد استخدامه. وافق م. محمد على إضافته للمنصة (2026-10-25)."""
import sys
from datetime import date, timedelta

from werkzeug.datastructures import MultiDict

sys.path.insert(0, ".")
from wsgi import app  # noqa: E402
from app import boq, contracts as C, projects, registers as R  # noqa: E402
from app.db import connect  # noqa: E402

TAG = "(بيانات تجريبية)"
CONTRACT_NO = "DEMO-2026-014"
db = connect(app.config["DATABASE"])
print("database:", "LIVE POSTGRES" if str(app.config["DATABASE"]).startswith("postgres") else app.config["DATABASE"])

def user_id(username):
    row = db.execute("SELECT id FROM users WHERE username = ? AND status = 'active'", (username,)).fetchone()
    if row is None:
        sys.exit(f"no active user {username!r}")
    return row[0]

actor = user_id(sys.argv[1])
approver = user_id(sys.argv[2]) if len(sys.argv) > 2 else None


def entity(kind, name, form, people, address):
    row = db.execute("SELECT id FROM entities WHERE name = ?", (name,)).fetchone()
    if row:
        return row[0], [r["id"] for r in R.people(db, row[0], active_only=True)]
    eid, _ = R.create_entity(db, kind, MultiDict([("name", name), *form]), actor)
    R.add_address(db, eid, address, actor)
    ids = [R.add_person(db, eid, {"full_name": n, "job_title": t, "phone": ph, "email": e}, actor)[0] for n, t, ph, e in people]
    return eid, ids


with app.test_request_context():
    owner, o_people = entity("owner", f"شركة النخبة للتطوير العقاري {TAG}",
                             [("email", "info@nukhba.example"), ("phone", "0112345678"), ("cr_no", "1010000001")],
                             [("م. سلمان العتيبي", "مدير المشاريع", "0501111111", "salman@nukhba.example"),
                              ("م. نورة القحطاني", "مهندسة متابعة", "0502222222", "noura@nukhba.example")],
                             {"label": "main", "city": "الرياض", "details": "طريق الملك فهد، برج النخبة"})
    cons, c_people = entity("consultant", f"مكتب الرؤية للاستشارات الهندسية {TAG}",
                            [("email", "office@ruya.example"), ("phone", "0119876543")],
                            [("م. خالد الدوسري", "المهندس المقيم", "0504444444", "khaled@ruya.example"),
                             ("م. ريم الحربي", "مهندسة إشراف", "0505555555", "reem@ruya.example")],
                            {"label": "main", "city": "الرياض", "details": "حي العليا، شارع التحلية"})
    entity("subcontractor", f"مؤسسة الإتقان للحفريات {TAG}",
           [("email", "ops@itqan.example"), ("phone", "0506666666"), ("cr_no", "1010000002"),
            ("vat_no", "300000000000003"), ("classification", "الدرجة الثالثة"), ("approval_status", "approved"),
            ("specialties", "CNC"), ("specialties", "MAS")],
           [("أ. ماجد الزهراني", "مدير العمليات", "0507777777", "majed@itqan.example")],
           {"label": "main", "city": "الرياض", "details": "المنطقة الصناعية الثانية"})

    row = db.execute("SELECT id FROM projects WHERE contract_no = ?", (CONTRACT_NO,)).fetchone()
    if row:
        pid = row[0]
    else:
        pid, _ = projects.create_project(db, {"name": f"مبنى إداري من ثلاثة طوابق {TAG}", "location": "الرياض، حي الملقا",
                                              "contract_no": CONTRACT_NO, "contract_value": "1,000,000.00",
                                              "start_date": "2026-11-01", "end_date": "2027-11-01"}, actor)
        projects.add_member(db, pid, actor, actor)
    print("project id:", pid)

    if not R.representatives(db, pid):
        R.set_project_parties(db, pid, MultiDict([
            ("owner_entity_id", str(owner)), ("owner_reps", str(o_people[0])), ("owner_reps", str(o_people[1])),
            ("consultant_entity_id", str(cons)), ("consultant_reps", str(c_people[0])), ("consultant_reps", str(c_people[1]))]),
            actor)

    if C.contract_of(db, pid) is None:
        C.save_contract(db, pid, {
            "contract_no": CONTRACT_NO, "signed_on": "2026-10-20", "kind": "lump_sum", "value_ex_vat": "1,000,000.00",
            "vat_pct": "15", "scope": "إنشاء مبنى إداري من ثلاثة طوابق شامل الأعمال الإنشائية والكهروميكانيكية والتشطيبات",
            "site_handover_on": "2026-10-28", "start_on": "2026-11-01", "duration_days": "365", "warranty_months": "12",
            "advance_pct": "10", "advance_recovery_pct": "10", "retention_pct": "10", "retention_cap_pct": "5",
            "payment_days": "30", "penalty_method": "daily_pct", "penalty_value": "0.1", "penalty_cap_pct": "10"}, actor)

    if not db.execute("SELECT 1 FROM boq_items WHERE project_id = ?", (pid,)).fetchone():
        PHASES = [
            ("الأعمال التمهيدية والحفر", [
                ("تجهيز الموقع", [("A-01", "تسوير الموقع بسور مؤقت", "exec", "م.ط", "180", "70"),
                                  ("A-02", "تسوية الموقع وتنظيفه", "exec", "م2", "1500", "9"),
                                  ("A-03", "مكتب ومرافق الموقع المؤقتة", "both", "مقطوعية", "1", "22000")]),
                ("الحفر والردم", [("A-04", "حفر عام للأساسات", "exec", "م3", "1800", "18"),
                                  ("A-05", "ردم بمواد مختارة ومدموكة", "both", "م3", "700", "30")])]),
            ("الأعمال الإنشائية", [
                ("الأساسات", [("B-01", "خرسانة عادية للنظافة", "both", "م3", "70", "280"),
                              ("B-02", "خرسانة مسلحة للقواعد", "both", "م3", "160", "620")]),
                ("الهيكل الخرساني", [("B-03", "خرسانة مسلحة للأعمدة", "both", "م3", "85", "780"),
                                     ("B-04", "خرسانة مسلحة للكمرات والبلاطات", "both", "م3", "220", "690")])]),
            ("أعمال المباني والعزل", [
                ("أعمال البناء", [("C-01", "بناء بلوك أسمنتي 25 سم للجدران الخارجية", "both", "م2", "1100", "78"),
                                  ("C-02", "بناء بلوك أسمنتي 10 سم للقواطع", "both", "م2", "650", "52")]),
                ("العزل", [("C-03", "عزل مائي للأسطح", "both", "م2", "480", "42"),
                           ("C-04", "عزل حراري للأسطح", "both", "م2", "480", "38")])]),
            ("الأعمال الكهروميكانيكية", [
                ("الأعمال الكهربائية", [("D-01", "لوحات توزيع رئيسية وفرعية", "both", "عدد", "6", "9500"),
                                        ("D-02", "تمديدات كهربائية للإنارة والقوى", "both", "م2", "1350", "38")]),
                ("التكييف والسباكة", [("D-03", "وحدات تكييف منفصلة", "both", "عدد", "14", "6800"),
                                      ("D-04", "شبكة سباكة وتصريف", "both", "مقطوعية", "1", "48000")])]),
            ("التشطيبات والتسليم", [
                ("التشطيبات الداخلية", [("E-01", "أرضيات بورسلان", "both", "م2", "900", "64"),
                                        ("E-02", "دهانات داخلية وخارجية", "exec", "م2", "2400", "16"),
                                        ("E-03", "أبواب خشبية ونوافذ ألمنيوم", "both", "عدد", "20", "1850")]),
                ("التسليم", [("E-04", "تنظيف نهائي وتسليم المشروع للمالك", "exec", "مقطوعية", "1", "19100")])]),
        ]
        for pname, secs in PHASES:
            p_id, _ = boq.add_wbs(db, pid, pname, None, actor)
            for sname, rows in secs:
                s_id, _ = boq.add_wbs(db, pid, sname, p_id, actor)
                for ref, desc, typ, unit, qty, rate in rows:
                    boq.add_item(db, pid, s_id, {"ref_no": ref, "description": desc, "item_type": typ, "unit": unit,
                                                 "qty": qty, "unit_rate": rate}, actor)
    checks, ok, total = boq.baseline_checks(db, pid)
    print("budget checks:", [(bool(c), t) for c, t, b in checks])
    if ok and not db.execute("SELECT baseline_approved_at FROM projects WHERE id = ?", (pid,)).fetchone()[0]:
        boq.approve_baseline(db, pid, actor)

    c = C.contract_of(db, pid)
    today = date.today()
    if not C.guarantees(db, c["id"]):
        C.add_guarantee(db, c["id"], {"kind": "performance", "bank": "البنك الأهلي السعودي", "number": "LG-2026-0417",
                                      "amount": "50,000", "issued_on": "2026-10-20",
                                      "expires_on": (today + timedelta(days=21)).isoformat()}, actor)
        C.add_guarantee(db, c["id"], {"kind": "advance", "bank": "بنك الرياض", "number": "LG-2026-0418",
                                      "amount": "100,000", "issued_on": "2026-10-20", "expires_on": "2027-11-30"}, actor)
    if not C.insurances(db, c["id"]):
        C.add_insurance(db, c["id"], {"kind": "car", "insurer": "التعاونية للتأمين", "policy_no": "CAR-55120",
                                      "cover_amount": "1,000,000", "expires_on": "2027-12-31"}, actor)
        C.add_insurance(db, c["id"], {"kind": "third_party", "insurer": "التعاونية للتأمين", "policy_no": "TPL-55121",
                                      "cover_amount": "500,000", "expires_on": "2027-12-31"}, actor)
    if not C.variation_orders(db, c["id"]):
        v1, _ = C.add_variation_order(db, c["id"], {"description": "إضافة مظلات سيارات معدنية في الموقف الخارجي بطلب المالك",
                                                    "issued_on": "2027-01-15", "value_delta": "38,500", "days_delta": "12"}, actor)
        C.add_variation_order(db, c["id"], {"description": "استبدال الدهانات الخارجية بدهان مقاوم للحرارة بطلب الاستشاري",
                                            "issued_on": "2027-02-03", "value_delta": "9,600", "days_delta": "0"}, actor)
        if approver and approver != actor:
            C.decide_variation_order(db, c["id"], v1, "approved", "", approver)

    s = C.summary(db, C.contract_of(db, pid))
    print("contract:", c["code"], "| current value:", s["current"] / 100, "| handover:", s["current_end"])
    print("expiring alerts:", len(C.expiring(db, c["id"])))
