"""العقد الرئيسي مع المالك (الدستور، البند 3.2): البيانات والمدة والدفعات والغرامات، والضمانات البنكية، والتأمينات، وأوامر التغيير."""
import re
from datetime import date, timedelta

from . import audit
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .projects import parse_money

KINDS = {"lump_sum": "Lump sum", "remeasure": "Re-measurement"}
PENALTY_METHODS = {"daily_pct": "Daily percentage", "daily_amount": "Daily amount"}
GUARANTEES = {"bid": "Bid bond", "performance": "Performance bond", "advance": "Advance payment guarantee"}
INSURANCES = {"car": "Contractor's all risks", "third_party": "Third-party liability", "workers": "Workers' compensation"}
VO_STATUS = {"study": "Under study", "approved": "Approved", "rejected": "Rejected"}
EXPIRY_WARNING_DAYS = 30


def parse_pct(v, what, required=False) -> int | None:
    """'15' أو '15.5' ← أجزاء من عشرة آلاف (1500، 1550). الفراغ = None."""
    s = (str(v) if v is not None else "").strip().replace("%", "").replace("٫", ".")
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if not s:
        if required:
            raise AuthError(_("Enter {what}.", what=what))
        return None
    if not re.fullmatch(r"\d{1,3}(\.\d{1,2})?", s):
        raise AuthError(_("{what} must be a percentage between 0 and 100.", what=what))
    whole, _sep, frac = s.partition(".")
    bp = int(whole) * 100 + int((frac + "00")[:2])
    if bp > 10000:
        raise AuthError(_("{what} must be a percentage between 0 and 100.", what=what))
    return bp


def fmt_pct(bp) -> str:
    if bp is None:
        return "—"
    return f"{bp / 100:.2f}".rstrip("0").rstrip(".") + "%"


def _int(v, what, required=True, minimum=0):
    s = (str(v) if v is not None else "").strip().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    if not s:
        if required:
            raise AuthError(_("Enter {what}.", what=what))
        return None
    if not re.fullmatch(r"-?\d{1,6}", s) or int(s) < minimum:
        raise AuthError(_("{what} must be a whole number.", what=what))
    return int(s)


def _date(v, what, required=True):
    s = (str(v) if v is not None else "").strip()
    if not s:
        if required:
            raise AuthError(_("Enter {what}.", what=what))
        return None
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        raise AuthError(_("The date format is not valid."))


def contract_of(db, pid):
    return db.execute("SELECT * FROM contracts WHERE project_id = ?", (pid,)).fetchone()


def _clean(form):
    d = {
        "contract_no": (form.get("contract_no") or "").strip(),
        "signed_on": _date(form.get("signed_on"), _("the signing date")),
        "kind": form.get("kind") or "",
        "value_ex_vat": parse_money(form.get("value_ex_vat")),
        "vat_bp": parse_pct(form.get("vat_pct"), _("the VAT rate"), required=True),
        "scope": (form.get("scope") or "").strip(),
        "site_handover_on": _date(form.get("site_handover_on"), _("the site handover date")),
        "start_on": _date(form.get("start_on"), _("the start date")),
        "duration_days": _int(form.get("duration_days"), _("the duration in days"), minimum=1),
        "warranty_months": _int(form.get("warranty_months"), _("the warranty period in months")),
        "advance_bp": parse_pct(form.get("advance_pct"), _("the advance payment")),
        "advance_recovery_bp": parse_pct(form.get("advance_recovery_pct"), _("the advance recovery rate")),
        "retention_bp": parse_pct(form.get("retention_pct"), _("the retention rate"), required=True),
        "retention_cap_bp": parse_pct(form.get("retention_cap_pct"), _("the retention cap")),
        "payment_days": _int(form.get("payment_days"), _("the payment period in days"), required=False),
        "penalty_method": form.get("penalty_method") or None,
        "penalty_value": None,
        "penalty_cap_bp": parse_pct(form.get("penalty_cap_pct"), _("the penalty cap")),
    }
    if len(d["contract_no"]) < 2:
        raise AuthError(_("Enter the contract number."))
    if d["kind"] not in KINDS:
        raise AuthError(_("Choose the contract type."))
    if not d["value_ex_vat"]:
        raise AuthError(_("Enter the contract value."))
    if len(d["scope"]) < 10:
        raise AuthError(_("Write a short description of the works."))
    if d["penalty_method"]:
        if d["penalty_method"] not in PENALTY_METHODS:
            raise AuthError(_("Choose how the delay penalty is calculated."))
        d["penalty_value"] = (parse_pct(form.get("penalty_value"), _("the delay penalty"), required=True)
                              if d["penalty_method"] == "daily_pct" else parse_money(form.get("penalty_value")))
        if d["penalty_value"] is None:
            raise AuthError(_("Enter the delay penalty."))
    if d["advance_recovery_bp"] and not d["advance_bp"]:
        raise AuthError(_("An advance recovery rate needs an advance payment."))
    return d


def end_date(start_on, days) -> str:
    return (date.fromisoformat(start_on) + timedelta(days=days)).isoformat()


def _sync_project(db, pid, d):
    """بيانات العقد الأساسية تبقى متزامنة مع المشروع، فتبقى الشاشات والتحليلات وفحص الميزانية صحيحة."""
    db.execute("UPDATE projects SET contract_no = ?, contract_value = ?, start_date = ?, end_date = ? WHERE id = ?",
               (d["contract_no"], d["value_ex_vat"], d["start_on"], end_date(d["start_on"], d["duration_days"]), pid))


def save_contract(db, pid, form, actor_id) -> int:
    p = db.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
    if p is None:
        raise AuthError(_("This project doesn't exist."))
    d = _clean(form)
    cur = contract_of(db, pid)
    if cur and p["baseline_approved_at"]:
        locked = ("value_ex_vat", "start_on", "duration_days")
        if any(cur[k] != d[k] and str(cur[k]) != str(d[k]) for k in locked):
            raise AuthError(_("The budget is approved: the contract value, start and duration change only through "
                              "approved change orders."))
    with tx(db):
        if cur is None:
            code = f"{p['code']}-CON-{next_counter(db, f'contract-{pid}'):02d}"
            cid = db.execute(
                f"INSERT INTO contracts(project_id, code, {', '.join(d)}, created_at, created_by) "
                f"VALUES (?, ?, {', '.join('?' for _ in d)}, ?, ?) RETURNING id",
                (pid, code, *d.values(), utcnow(), actor_id)).fetchone()[0]
            audit.log(db, actor_id, "contract_created", "contract", cid, pid, code=code, contract_no=d["contract_no"],
                      contract_value=d["value_ex_vat"])
        else:
            cid = cur["id"]
            changes = {k: v for k, v in d.items() if str(cur[k]) != str(v) if not (cur[k] is None and v is None)}
            if changes:
                db.execute(f"UPDATE contracts SET {', '.join(f'{k} = ?' for k in changes)}, updated_at = ? WHERE id = ?",
                           (*changes.values(), utcnow(), cid))
                audit.log(db, actor_id, "contract_updated", "contract", cid, pid, code=cur["code"],
                          **{k: {"from": cur[k], "to": v} for k, v in changes.items()})
        _sync_project(db, pid, d)
    return cid


def summary(db, c) -> dict:
    """القيم المحسوبة: القيمة الحالية والتاريخ الحالي بعد أوامر التغيير المعتمدة، والضريبة، والدفعة المقدمة."""
    value_delta, days_delta = db.execute(
        "SELECT CAST(COALESCE(SUM(value_delta), 0) AS BIGINT), CAST(COALESCE(SUM(days_delta), 0) AS BIGINT) "
        "FROM variation_orders WHERE contract_id = ? AND status = 'approved'", (c["id"],)).fetchone()
    current = c["value_ex_vat"] + value_delta
    vat = lambda v: v * c["vat_bp"] // 10000  # noqa: E731
    contractual_end = end_date(str(c["start_on"]), c["duration_days"])
    return {
        "original": c["value_ex_vat"], "vo_total": value_delta, "current": current,
        "current_with_vat": current + vat(current), "vat_amount": vat(current),
        "advance": c["value_ex_vat"] * (c["advance_bp"] or 0) // 10000 if c["advance_bp"] else None,
        "contractual_end": contractual_end, "days_delta": days_delta,
        "current_end": end_date(str(c["start_on"]), c["duration_days"] + days_delta),
    }


# ---------- الضمانات والتأمينات ----------

def guarantees(db, cid):
    return db.execute("SELECT * FROM contract_guarantees WHERE contract_id = ? ORDER BY expires_on", (cid,)).fetchall()


def insurances(db, cid):
    return db.execute("SELECT * FROM contract_insurances WHERE contract_id = ? ORDER BY expires_on", (cid,)).fetchall()


def add_guarantee(db, cid, form, actor_id):
    c = db.execute("SELECT * FROM contracts WHERE id = ?", (cid,)).fetchone()
    kind = form.get("kind") or ""
    if kind not in GUARANTEES:
        raise AuthError(_("Choose the guarantee type."))
    bank, number = (form.get("bank") or "").strip(), (form.get("number") or "").strip()
    if len(bank) < 2 or len(number) < 2:
        raise AuthError(_("Enter the bank and the guarantee number."))
    amount = parse_money(form.get("amount"))
    if not amount:
        raise AuthError(_("Enter the guarantee amount."))
    issued, expires = _date(form.get("issued_on"), _("the issue date")), _date(form.get("expires_on"), _("the expiry date"))
    if expires <= issued:
        raise AuthError(_("The expiry date must be after the issue date."))
    with tx(db):
        gid = db.execute("INSERT INTO contract_guarantees(contract_id, kind, bank, number, amount, issued_on, expires_on, "
                         "created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?) RETURNING id",
                         (cid, kind, bank, number, amount, issued, expires, utcnow(), actor_id)).fetchone()[0]
        audit.log(db, actor_id, "guarantee_added", "contract", cid, c["project_id"], kind=kind, number=number,
                  amount=amount, expires_on=expires)
    return gid


def release_guarantee(db, cid, gid, actor_id):
    g = db.execute("SELECT g.*, c.project_id FROM contract_guarantees g JOIN contracts c ON c.id = g.contract_id "
                   "WHERE g.id = ? AND g.contract_id = ?", (gid, cid)).fetchone()
    if g is None or g["released_on"]:
        raise AuthError(_("This guarantee doesn't exist or was already released."))
    with tx(db):
        db.execute("UPDATE contract_guarantees SET released_on = ? WHERE id = ?", (utcnow()[:10], gid))
        audit.log(db, actor_id, "guarantee_released", "contract", cid, g["project_id"], kind=g["kind"], number=g["number"])


def add_insurance(db, cid, form, actor_id):
    c = db.execute("SELECT * FROM contracts WHERE id = ?", (cid,)).fetchone()
    kind = form.get("kind") or ""
    if kind not in INSURANCES:
        raise AuthError(_("Choose the insurance type."))
    insurer, policy = (form.get("insurer") or "").strip(), (form.get("policy_no") or "").strip()
    if len(insurer) < 2 or len(policy) < 2:
        raise AuthError(_("Enter the insurance company and the policy number."))
    cover = parse_money(form.get("cover_amount"))
    if not cover:
        raise AuthError(_("Enter the cover amount."))
    expires = _date(form.get("expires_on"), _("the expiry date"))
    with tx(db):
        iid = db.execute("INSERT INTO contract_insurances(contract_id, kind, insurer, policy_no, cover_amount, expires_on, "
                         "created_at, created_by) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
                         (cid, kind, insurer, policy, cover, expires, utcnow(), actor_id)).fetchone()[0]
        audit.log(db, actor_id, "insurance_added", "contract", cid, c["project_id"], kind=kind, policy_no=policy,
                  amount=cover, expires_on=expires)
    return iid


def expiring(db, cid, today=None) -> list[dict]:
    """الضمانات والتأمينات التي تنتهي خلال 30 يومًا أو انتهت (الدستور: تنبيه قبل الانتهاء بثلاثين يومًا)."""
    today = date.fromisoformat(today) if today else date.today()
    out = []
    rows = [(g, "guarantee") for g in guarantees(db, cid) if not g["released_on"]] + \
           [(i, "insurance") for i in insurances(db, cid)]
    for row, kind in rows:
        days = (date.fromisoformat(str(row["expires_on"])[:10]) - today).days
        if days <= EXPIRY_WARNING_DAYS:
            out.append({"kind": kind, "type": row["kind"], "ref": row["number"] if kind == "guarantee" else row["policy_no"],
                        "expires_on": str(row["expires_on"])[:10], "days": days})
    return sorted(out, key=lambda r: r["days"])


# ---------- أوامر التغيير ----------

def variation_orders(db, cid):
    return db.execute("SELECT v.*, u.full_name AS decided_name FROM variation_orders v LEFT JOIN users u ON u.id = v.decided_by "
                      "WHERE v.contract_id = ? ORDER BY v.id", (cid,)).fetchall()


def vo_items(db, vo_id):
    return db.execute("SELECT b.code, b.description FROM variation_order_items x JOIN boq_items b ON b.id = x.boq_item_id "
                      "WHERE x.vo_id = ? ORDER BY b.code", (vo_id,)).fetchall()


def _signed_money(v, what):
    s = (str(v) if v is not None else "").strip().replace(" ", "")
    neg = s.startswith("-") or s.startswith("−")
    amount = parse_money(s.lstrip("-−+"))
    if amount is None:
        raise AuthError(_("Enter {what}.", what=what))
    return -amount if neg else amount


def add_variation_order(db, cid, form, actor_id):
    c = db.execute("SELECT c.*, p.code AS pcode FROM contracts c JOIN projects p ON p.id = c.project_id WHERE c.id = ?",
                   (cid,)).fetchone()
    desc = (form.get("description") or "").strip()
    if len(desc) < 10:
        raise AuthError(_("Describe the change and its reason."))
    issued = _date(form.get("issued_on"), _("the date"))
    value = _signed_money(form.get("value_delta"), _("the effect on the value"))
    days = _int(form.get("days_delta"), _("the effect on the duration in days"), minimum=-99999)
    if value == 0 and days == 0:
        raise AuthError(_("A change order must change the value or the duration."))
    getlist = form.getlist if hasattr(form, "getlist") else (lambda k: form.get(k) or [])
    allowed = {r[0] for r in db.execute("SELECT id FROM boq_items WHERE project_id = ?", (c["project_id"],))}
    items = sorted({int(x) for x in getlist("items") if str(x).isdigit() and int(x) in allowed})
    counter = "vo-%d" % c["project_id"]
    with tx(db):
        code = f"{c['pcode']}-VO-{next_counter(db, counter):03d}"
        vid = db.execute("INSERT INTO variation_orders(contract_id, code, issued_on, description, value_delta, days_delta, "
                         "created_at, created_by) VALUES (?,?,?,?,?,?,?,?) RETURNING id",
                         (cid, code, issued, desc, value, days, utcnow(), actor_id)).fetchone()[0]
        for it in items:
            db.execute("INSERT INTO variation_order_items(vo_id, boq_item_id) VALUES (?, ?)", (vid, it))
        audit.log(db, actor_id, "vo_created", "contract", cid, c["project_id"], code=code, amount=value, days=days)
    return vid, code


def decide_variation_order(db, cid, vid, decision, note, actor_id):
    v = db.execute("SELECT v.*, c.project_id FROM variation_orders v JOIN contracts c ON c.id = v.contract_id "
                   "WHERE v.id = ? AND v.contract_id = ?", (vid, cid)).fetchone()
    if v is None:
        raise AuthError(_("This change order doesn't exist."))
    if v["status"] != "study":
        raise AuthError(_("This change order was already decided."))
    if decision not in ("approved", "rejected"):
        raise AuthError(_("Choose approve or reject."))
    if v["created_by"] == actor_id:
        raise AuthError(_("Whoever prepares a change order can't approve it."))
    note = (note or "").strip() or None
    if decision == "rejected" and not note:
        raise AuthError(_("Write the reason for rejecting."))
    with tx(db):
        db.execute("UPDATE variation_orders SET status = ?, decided_at = ?, decided_by = ?, decision_note = ? WHERE id = ?",
                   (decision, utcnow(), actor_id, note, vid))
        audit.log(db, actor_id, "vo_approved" if decision == "approved" else "vo_rejected", "contract", cid,
                  v["project_id"], code=v["code"], reason=note)
