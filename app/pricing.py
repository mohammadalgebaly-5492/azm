"""المناقصات: تحليل سعر البند (الدستور، البند 3.3): التكلفة المباشرة للوحدة من سطور التحليل، والمصاريف غير المباشرة والربح،
والسعر المقترح، وهامش البند مقابل سعره في العقد. يُعِده مهندس تحكم تكلفة، ويُقفل مع اعتماد خط أساس الميزانية."""
from . import audit
from .boq import is_locked, parse_qty
from .contracts import parse_pct
from .db import tx, utcnow
from .errors import AuthError
from .i18n import _
from .projects import parse_money

COST_TYPES = {"material": "Materials", "labour": "Labour", "equipment": "Equipment", "subcontract": "Subcontractor"}
FULL = 10000


def lines(db, iid):
    return db.execute("SELECT * FROM price_lines WHERE boq_item_id = ? ORDER BY cost_type, id", (iid,)).fetchall()


def line_total(r) -> int:
    return (r["qty_per_unit_milli"] * r["unit_price"] + 500) // 1000


def result(db, item) -> dict:
    """التكلفة المباشرة للوحدة، والسعر المقترح، وهامش البند ونسبته."""
    rows = lines(db, item["id"])
    pr = db.execute("SELECT * FROM item_pricing WHERE boq_item_id = ?", (item["id"],)).fetchone()
    oh, profit = (pr["overhead_bp"], pr["profit_bp"]) if pr else (0, 0)
    direct = sum(line_total(r) for r in rows)
    by_type = {}
    for r in rows:
        by_type[r["cost_type"]] = by_type.get(r["cost_type"], 0) + line_total(r)
    cost = direct + direct * oh // FULL
    proposed = cost + cost * profit // FULL
    margin = item["unit_rate"] - cost
    return {"lines": rows, "direct": direct, "by_type": by_type, "overhead_bp": oh, "profit_bp": profit, "cost": cost,
            "proposed": proposed, "margin": margin, "margin_bp": margin * FULL // item["unit_rate"] if item["unit_rate"] else None,
            "has": bool(rows)}


def _item(db, pid, iid):
    item = db.execute("SELECT * FROM boq_items WHERE id = ? AND project_id = ?", (iid, pid)).fetchone()
    if item is None:
        raise AuthError(_("Item not found."))
    if is_locked(db, pid):
        raise AuthError(_("The budget baseline is approved, so the price analysis is locked with it."))
    return item


def add_line(db, pid, iid, form, actor_id):
    item = _item(db, pid, iid)
    kind = form.get("cost_type") or ""
    if kind not in COST_TYPES:
        raise AuthError(_("Choose the cost type."))
    desc = (form.get("description") or "").strip()
    if len(desc) < 2:
        raise AuthError(_("Enter the description."))
    unit = (form.get("unit") or "").strip()
    if not unit:
        raise AuthError(_("Enter the unit."))
    qty = parse_qty(form.get("qty"))
    if qty <= 0:
        raise AuthError(_("Enter the quantity per unit of the item."))
    price = parse_money(form.get("unit_price"))
    if price is None:
        raise AuthError(_("Enter the unit price."))
    with tx(db):
        db.execute("INSERT INTO price_lines(boq_item_id, cost_type, description, unit, qty_per_unit_milli, unit_price, created_at, "
                   "created_by) VALUES (?,?,?,?,?,?,?,?)", (iid, kind, desc, unit, qty, price, utcnow(), actor_id))
        audit.log(db, actor_id, "price_line_added", "boq_item", iid, pid, code=item["code"], description=desc)


def delete_line(db, pid, iid, line_id, actor_id):
    item = _item(db, pid, iid)
    with tx(db):
        n = db.execute("DELETE FROM price_lines WHERE id = ? AND boq_item_id = ?", (line_id, iid)).rowcount
        if n:
            audit.log(db, actor_id, "price_line_removed", "boq_item", iid, pid, code=item["code"])


def set_rates(db, pid, iid, form, actor_id):
    item = _item(db, pid, iid)
    oh = parse_pct(form.get("overhead_pct") or "0", _("the overhead rate"), required=True)
    profit = parse_pct(form.get("profit_pct") or "0", _("the profit rate"), required=True)
    with tx(db):
        if db.execute("SELECT 1 FROM item_pricing WHERE boq_item_id = ?", (iid,)).fetchone():
            db.execute("UPDATE item_pricing SET overhead_bp = ?, profit_bp = ?, updated_at = ?, updated_by = ? WHERE boq_item_id = ?",
                       (oh, profit, utcnow(), actor_id, iid))
        else:
            db.execute("INSERT INTO item_pricing(boq_item_id, overhead_bp, profit_bp, updated_at, updated_by) VALUES (?,?,?,?,?)",
                       (iid, oh, profit, utcnow(), actor_id))
        audit.log(db, actor_id, "pricing_rates_set", "boq_item", iid, pid, code=item["code"], overhead_bp=oh, profit_bp=profit)


def unit_cost_of_type(db, iid, resource_kind):
    """سطر التحليل المقابل لنوع المورد المخصَّص (القاعدة 5 في البند 3.6)."""
    kind = {"person": "labour", "crew": "labour", "equipment": "equipment", "subcontractor": "subcontract"}[resource_kind]
    rows = [r for r in lines(db, iid) if r["cost_type"] == kind]
    return sum(line_total(r) for r in rows) if rows else None
