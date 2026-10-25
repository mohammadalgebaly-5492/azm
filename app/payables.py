"""مستخلصات مقاولي الباطن وفواتير الموردين (الدستور، البند 4.7): محضر الاستلام، والمطابقة الثلاثية، ولا مستخلص بأكثر من
المنجز ولا بأكثر من الالتزام، والاعتماد حسب الحدود، والصرف من المحاسبة. من يُعِد لا يعتمد، ومن يعتمد لا يصرف."""
from datetime import date

from . import audit
from .boq import fmt_qty, parse_qty
from .contracts import parse_pct
from .db import next_counter, tx, utcnow
from .errors import AuthError
from .i18n import _
from .procurement import LIMIT
from .projects import parse_money
from .resources import _date

KINDS = {"certificate": "Subcontractor certificate", "invoice": "Supplier invoice"}
STATUS = {"review": "Waiting for cost control", "cc_approved": "Waiting for the Director", "approved": "Approved for payment",
          "paid": "Paid", "returned": "Returned"}
LIVE = ("review", "cc_approved", "approved", "paid")


def _sum(db, sql, args):
    return db.execute(sql, args).fetchone()[0] or 0


def orders(db, pid):
    """الأوامر والعقود مع ما استُلم وما استُخلص وما صُرف."""
    rows = db.execute("SELECT c.*, e.name AS entity_name, b.code AS item_code, b.unit AS item_unit FROM commitments c "
                      "JOIN entities e ON e.id = c.entity_id JOIN boq_items b ON b.id = c.boq_item_id "
                      "WHERE c.project_id = ? ORDER BY c.code", (pid,)).fetchall()
    out = []
    for c in rows:
        out.append({"c": c, "received": received(db, c["id"]), "billed_qty": billed_qty(db, c["id"]),
                    "billed": _sum(db, "SELECT CAST(COALESCE(SUM(gross), 0) AS BIGINT) FROM payables WHERE commitment_id = ? "
                                       "AND status IN ('review','cc_approved','approved','paid')", (c["id"],)),
                    "paid": _sum(db, "SELECT CAST(COALESCE(SUM(net), 0) AS BIGINT) FROM payables WHERE commitment_id = ? "
                                     "AND status = 'paid'", (c["id"],))})
    return out


def received(db, cid) -> int:
    return _sum(db, "SELECT CAST(COALESCE(SUM(qty_milli), 0) AS BIGINT) FROM goods_receipts WHERE commitment_id = ?", (cid,))


def billed_qty(db, cid) -> int:
    return _sum(db, "SELECT CAST(COALESCE(SUM(qty_milli), 0) AS BIGINT) FROM payables WHERE commitment_id = ? "
                    "AND status IN ('review','cc_approved','approved','paid')", (cid,))


def executed(db, item_id) -> int:
    """الكمية المنجزة المسجلة في المنصة: من التقارير اليومية المعتمدة."""
    return _sum(db, "SELECT CAST(COALESCE(SUM(q.qty_milli), 0) AS BIGINT) FROM dsr_quantities q JOIN daily_reports r "
                    "ON r.id = q.report_id WHERE q.boq_item_id = ? AND r.status = 'approved'", (item_id,))


def _order(db, pid, raw):
    raw = str(raw or "")
    c = db.execute("SELECT * FROM commitments WHERE id = ? AND project_id = ?", (int(raw), pid)).fetchone() if raw.isdigit() else None
    if c is None:
        raise AuthError(_("Choose the order or subcontract."))
    return c


def add_receipt(db, pid, form, actor_id) -> str:
    """محضر استلام المواد: لا يتجاوز المستلم كمية أمر الشراء."""
    c = _order(db, pid, form.get("commitment_id"))
    if c["kind"] != "material":
        raise AuthError(_("Goods receipts are for purchase orders of materials."))
    on = _date(form.get("received_on"), _("the receipt date"))
    if on > date.today().isoformat():
        raise AuthError(_("Actual dates can't be in the future."))
    qty = parse_qty(form.get("qty"))
    if qty <= 0:
        raise AuthError(_("Enter the quantity."))
    if received(db, c["id"]) + qty > c["qty_milli"]:
        raise AuthError(_("The received quantity would exceed the ordered quantity ({qty}).", qty=fmt_qty(c["qty_milli"])))
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    counter = "grn-%d" % pid
    with tx(db):
        code = f"{p['code']}-GRN-{next_counter(db, counter):04d}"
        db.execute("INSERT INTO goods_receipts(project_id, code, commitment_id, received_on, qty_milli, notes, created_at, created_by) "
                   "VALUES (?,?,?,?,?,?,?,?)", (pid, code, c["id"], on, qty, (form.get("notes") or "").strip() or None,
                                                utcnow(), actor_id))
        audit.log(db, actor_id, "goods_received", "project", pid, pid, code=code, order=c["code"])
    return code


def raise_payable(db, pid, form, actor_id) -> str:
    c = _order(db, pid, form.get("commitment_id"))
    kind = "certificate" if c["kind"] == "subcontract" else "invoice"
    qty = parse_qty(form.get("qty"))
    if qty <= 0:
        raise AuthError(_("Enter the quantity."))
    d = {"period_from": None, "period_to": None, "vendor_ref": (form.get("vendor_ref") or "").strip() or None}
    done = billed_qty(db, c["id"])
    if kind == "certificate":
        d["period_from"] = _date(form.get("period_from"), _("the period start"))
        d["period_to"] = _date(form.get("period_to"), _("the period end"))
        if d["period_to"] < d["period_from"]:
            raise AuthError(_("The end date must be after the start date."))
        limit = executed(db, c["boq_item_id"])
        if done + qty > limit:
            raise AuthError(_("The certified quantity would exceed the executed quantity recorded in the platform ({qty}).",
                              qty=fmt_qty(limit)))
    else:
        if not d["vendor_ref"]:
            raise AuthError(_("Enter the supplier's invoice number."))
        if c["kind"] == "material" and done + qty > received(db, c["id"]):
            raise AuthError(_("Three-way match: the invoiced quantity would exceed the received quantity ({qty}).",
                              qty=fmt_qty(received(db, c["id"]))))
    if done + qty > c["qty_milli"]:
        raise AuthError(_("The quantity would exceed the quantity of the order ({qty}).", qty=fmt_qty(c["qty_milli"])))
    gross = (qty * c["unit_price"] + 500) // 1000
    billed = _sum(db, "SELECT CAST(COALESCE(SUM(gross), 0) AS BIGINT) FROM payables WHERE commitment_id = ? AND status IN "
                      "('review','cc_approved','approved','paid')", (c["id"],))
    if billed + gross > c["total"]:
        raise AuthError(_("The amount would exceed the approved commitment."))
    ret_bp = parse_pct(form.get("retention_pct"), _("the retention rate")) or 0 if kind == "certificate" else 0
    retention = gross * ret_bp // 10000
    advance = parse_money(form.get("advance")) or 0
    deductions = parse_money(form.get("deductions")) or 0
    note = (form.get("deduction_note") or "").strip() or None
    if deductions and not note:
        raise AuthError(_("Write the reason for the deductions."))
    net = gross - retention - advance - deductions
    if net < 0:
        raise AuthError(_("The deductions are more than the value of the works."))
    p = db.execute("SELECT code FROM projects WHERE id = ?", (pid,)).fetchone()
    with tx(db):
        if kind == "certificate":
            code = f"{p['code']}-SPC-{next_counter(db, 'spc-%d' % pid):03d}"
        else:
            code = f"{p['code']}-INV-{next_counter(db, 'inv-%d' % pid):04d}"
        db.execute("INSERT INTO payables(project_id, code, commitment_id, kind, period_from, period_to, vendor_ref, qty_milli, gross, "
                   "retention_bp, retention, advance, deductions, deduction_note, net, needs_director, created_at, created_by) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (pid, code, c["id"], kind, d["period_from"], d["period_to"], d["vendor_ref"], qty, gross, ret_bp, retention,
                    advance, deductions, note, net, net > LIMIT, utcnow(), actor_id))
        audit.log(db, actor_id, "payable_raised", "project", pid, pid, code=code, amount=net)
    return code


def payables(db, pid):
    return db.execute("SELECT x.*, c.code AS order_code, e.name AS entity_name FROM payables x JOIN commitments c ON c.id = x.commitment_id "
                      "JOIN entities e ON e.id = c.entity_id WHERE x.project_id = ? ORDER BY x.id DESC", (pid,)).fetchall()


def _payable(db, pid, xid):
    x = db.execute("SELECT * FROM payables WHERE id = ? AND project_id = ?", (xid, pid)).fetchone()
    if x is None:
        raise AuthError(_("This certificate or invoice doesn't exist."))
    return x


def approve(db, pid, xid, actor_id, director=False):
    x = _payable(db, pid, xid)
    if director:
        if x["status"] != "cc_approved":
            raise AuthError(_("This is not waiting for the Director."))
        if actor_id in (x["created_by"], x["cc_by"]):
            raise AuthError(_("Whoever prepares or approved before can't approve again."))
        sets, args = "status = 'approved', dir_at = ?, dir_by = ?", (utcnow(), actor_id)
    else:
        if x["status"] != "review":
            raise AuthError(_("This is not waiting for cost control."))
        if actor_id == x["created_by"]:
            raise AuthError(_("Whoever prepares or approved before can't approve again."))
        sets = "status = ?, cc_at = ?, cc_by = ?"
        args = ("cc_approved" if x["needs_director"] else "approved", utcnow(), actor_id)
    with tx(db):
        db.execute(f"UPDATE payables SET {sets} WHERE id = ?", (*args, xid))
        audit.log(db, actor_id, "payable_approved", "project", pid, pid, code=x["code"], amount=x["net"])


def return_payable(db, pid, xid, reason, actor_id, director=False):
    x = _payable(db, pid, xid)
    if x["status"] != ("cc_approved" if director else "review"):
        raise AuthError(_("Only one waiting for approval can be returned."))
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise AuthError(_("Write the reason for returning."))
    with tx(db):
        db.execute("UPDATE payables SET status = 'returned', return_reason = ? WHERE id = ?", (reason, xid))
        audit.log(db, actor_id, "payable_returned", "project", pid, pid, code=x["code"], reason=reason)


def pay(db, pid, xid, form, actor_id):
    """الصرف من المحاسبة بعد الاعتماد، ولا يصرف من أعدّ أو اعتمد."""
    x = _payable(db, pid, xid)
    if x["status"] != "approved":
        raise AuthError(_("Only an approved certificate or invoice can be paid."))
    if actor_id in (x["created_by"], x["cc_by"], x["dir_by"]):
        raise AuthError(_("Whoever approves doesn't pay."))
    on = _date(form.get("paid_on"), _("the payment date"))
    if on > date.today().isoformat():
        raise AuthError(_("Actual dates can't be in the future."))
    ref = (form.get("paid_ref") or "").strip()
    if len(ref) < 2:
        raise AuthError(_("Enter the payment reference."))
    with tx(db):
        db.execute("UPDATE payables SET status = 'paid', paid_on = ?, paid_ref = ?, paid_by = ? WHERE id = ?", (on, ref, actor_id, xid))
        audit.log(db, actor_id, "payable_paid", "project", pid, pid, code=x["code"], amount=x["net"])


def cost_by_item(db, pid) -> dict[int, int]:
    """التكلفة الفعلية من المستخلصات والفواتير المعتمدة (قيمة الأعمال قبل الاستقطاعات)."""
    return {r[0]: r[1] for r in db.execute(
        "SELECT c.boq_item_id, CAST(SUM(x.gross) AS BIGINT) FROM payables x JOIN commitments c ON c.id = x.commitment_id "
        "WHERE x.project_id = ? AND x.status IN ('approved','paid') GROUP BY c.boq_item_id", (pid,)).fetchall()}
