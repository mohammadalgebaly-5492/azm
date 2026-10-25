"""مستخلصات الشركة إلى المالك (الدستور، البند 4.8): مسودة تلقائية عند استحقاق الدفعة، وموافقة مهندس تحكم تكلفة، ثم التقديم
واعتماد الاستشاري والتحصيل، ومتابعة المستحقات المتأخرة وأعمارها."""
from datetime import date, timedelta

from . import audit
from .contracts import contract_of
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .projects import parse_money
from .resources import _date
from .schedule import milestones

STATUS = {"draft": "Draft", "agreed": "Agreed by cost control", "submitted": "Submitted to the owner",
          "certified": "Certified by the consultant", "collected": "Collected"}


def certificates(db, pid):
    return db.execute("SELECT o.*, m.code AS ms_code, m.description AS ms_desc FROM owner_certificates o "
                      "LEFT JOIN payment_milestones m ON m.id = o.milestone_id WHERE o.project_id = ? ORDER BY o.id DESC",
                      (pid,)).fetchall()


def due_without_certificate(db, pid):
    """الدفعات التي بلغ نشاطها نسبة الاستحقاق ولم تُعَد لها مسودة: تُعِدها المنصة بضغطة."""
    have = {r[0] for r in db.execute("SELECT milestone_id FROM owner_certificates WHERE project_id = ? AND milestone_id IS NOT NULL",
                                     (pid,)).fetchall()}
    return [m for m in milestones(db, pid) if m["due"] and m["m"]["id"] not in have]


def _amounts(db, pid, c, gross):
    """المحتجزات واسترداد الدفعة المقدمة والضريبة من شروط العقد، مع حد المحتجزات وحد الدفعة المقدمة."""
    prev = db.execute("SELECT CAST(COALESCE(SUM(retention), 0) AS BIGINT), CAST(COALESCE(SUM(advance), 0) AS BIGINT) "
                      "FROM owner_certificates WHERE project_id = ?", (pid,)).fetchone()
    retention = gross * (c["retention_bp"] or 0) // 10000
    if c["retention_cap_bp"]:
        retention = max(0, min(retention, c["value_ex_vat"] * c["retention_cap_bp"] // 10000 - prev[0]))
    advance_total = c["value_ex_vat"] * (c["advance_bp"] or 0) // 10000
    advance = max(0, min(gross * (c["advance_recovery_bp"] or 0) // 10000, advance_total - prev[1]))
    vat = gross * c["vat_bp"] // 10000
    return {"retention": retention, "advance": advance, "vat": vat, "net": gross - retention - advance + vat}


def create(db, pid, form, actor_id) -> str:
    c = contract_of(db, pid)
    if c is None:
        raise AuthError(_("Record the main contract first."))
    raw = str(form.get("milestone_id") or "")
    ms = None
    if raw.isdigit():
        ms = next((m for m in milestones(db, pid) if m["m"]["id"] == int(raw)), None)
        if ms is None:
            raise AuthError(_("This payment doesn't exist."))
        if db.execute("SELECT 1 FROM owner_certificates WHERE milestone_id = ?", (ms["m"]["id"],)).fetchone():
            raise AuthError(_("A certificate already exists for this payment."))
        gross = ms["value"]
    else:
        gross = parse_money(form.get("gross"))
        if not gross:
            raise AuthError(_("Enter the value of the works in this certificate."))
    period = _date(form.get("period_to") or date.today().isoformat(), _("the period end"))
    a = _amounts(db, pid, c, gross)
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    counter = "ipc-%d" % pid
    with tx(db):
        code = f"{p['code']}-IPC-{next_counter(db, counter):03d}"
        db.execute("INSERT INTO owner_certificates(project_id, code, milestone_id, period_to, gross, retention, advance, vat, net, "
                   "notes, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (pid, code, ms["m"]["id"] if ms else None, period, gross, a["retention"], a["advance"], a["vat"], a["net"],
                    (form.get("notes") or "").strip() or None, utcnow(), actor_id))
        audit.log(db, actor_id, "ipc_drafted", "project", pid, pid, code=code, amount=gross)
    return code


def _cert(db, pid, oid):
    o = db.execute("SELECT * FROM owner_certificates WHERE id = ? AND project_id = ?", (oid, pid)).fetchone()
    if o is None:
        raise AuthError(_("This certificate doesn't exist."))
    return o


def advance(db, pid, oid, step, form, actor_id):
    """مسار المستخلص: موافقة مهندس تحكم تكلفة، ثم التقديم، ثم اعتماد الاستشاري، ثم التحصيل."""
    o = _cert(db, pid, oid)
    order = {"agree": ("draft", "agreed"), "submit": ("agreed", "submitted"), "certify": ("submitted", "certified"),
             "collect": ("certified", "collected")}
    if step not in order or o["status"] != order[step][0]:
        raise AuthError(_("This step doesn't apply to the certificate now."))
    sets, args = {"status": order[step][1]}, []
    if step == "agree":
        if o["created_by"] == actor_id:
            raise AuthError(_("Whoever prepares the certificate can't agree to it."))
        sets.update(agreed_at=utcnow(), agreed_by=actor_id)
    else:
        on = _date(form.get("on"), _("the date"))
        if on > date.today().isoformat():
            raise AuthError(_("Actual dates can't be in the future."))
        if step == "submit":
            sets["submitted_on"] = on
        elif step == "certify":
            amount = parse_money(form.get("amount"))
            if amount is None or amount <= 0:
                raise AuthError(_("Enter the amount certified by the consultant."))
            sets.update(certified_on=on, certified_amount=amount)
        else:
            sets.update(collected_on=on, collected_by=actor_id)
    with tx(db):
        db.execute(f"UPDATE owner_certificates SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), *args, oid))
        audit.log(db, actor_id, f"ipc_{step}", "project", pid, pid, code=o["code"])


def receivables(db, pid, today=None):
    """المستحقات من المالك: المعتمدة غير المحصلة، وعمر كل منها مقابل مدة السداد في العقد."""
    today = today or date.today()
    c = contract_of(db, pid)
    days = (c["payment_days"] or 0) if c else 0
    out = []
    for o in db.execute("SELECT * FROM owner_certificates WHERE project_id = ? AND status = 'certified' ORDER BY certified_on",
                        (pid,)).fetchall():
        on = date.fromisoformat(str(o["certified_on"])[:10])
        due = on + timedelta(days=days)
        out.append({"o": o, "due": due, "age": (today - on).days, "late": max(0, (today - due).days)})
    return out
