"""متابعة التقدم والتكلفة بالقيمة المكتسبة (الدستور، البند 4.3): القيمة المخططة والمكتسبة والتكلفة الفعلية، ومؤشرا أداء
الزمن والتكلفة، والتكلفة المتوقعة عند الإنجاز، وحالة البند والقسم والمشروع بالألوان (الأسوأ بين الزمن والتكلفة)."""
from datetime import timedelta

from . import daily, payables, schedule as T

FULL = 10000
RAG = {"green": "On track", "yellow": "Watch", "red": "At risk", "critical": "Critical"}
ORDER = ("green", "yellow", "red", "critical")


def rag(index_bp):
    """أخضر من 0.95، وأصفر من 0.90، وأحمر من 0.70، وحرج تحتها (قرار م. محمد: 5% و10% و30%)."""
    if index_bp is None:
        return None
    return "green" if index_bp >= 9500 else "yellow" if index_bp >= 9000 else "red" if index_bp >= 7000 else "critical"


def worst(*keys):
    keys = [k for k in keys if k]
    return max(keys, key=ORDER.index) if keys else None


def _ratio(a, b):
    return a * FULL // b if b else None


def _pv_rows(rows, at):
    for r in rows:
        if at >= r["pf"]:
            yield r, r["cost"]
        elif at >= r["ps"]:
            yield r, r["cost"] * ((at - r["ps"]).days + 1) // r["dur"]
        else:
            yield r, 0


def _measure(bac, pv, ev, ac):
    spi, cpi = _ratio(ev, pv), _ratio(ev, ac)
    return {"bac": bac, "pv": pv, "ev": ev, "ac": ac, "spi": spi, "cpi": cpi,
            "eac": bac * ac // ev if ev and ac else bac, "status": worst(rag(spi), rag(cpi)) if (pv or ac) else None,
            "progress": _ratio(ev, bac) or 0}


def actual_cost(db, pid, until=None) -> dict[int, int]:
    """التكلفة الفعلية لكل بند: الموارد من التقارير اليومية المعتمدة، والمستخلصات والفواتير المعتمدة."""
    ac = daily.actual_cost(db, pid, until)
    for iid, v in payables.cost_by_item(db, pid, until).items():
        ac[iid] = ac.get(iid, 0) + v
    return ac


def indicators(db, pid, now=None) -> dict:
    now = now or T.today()
    rows = T.compute(db, pid, now)
    under, items = T._subtree(db, pid)
    prog = T.item_progress(db, pid, now)
    ac = actual_cost(db, pid, now)
    direct = {r["a"]["boq_item_id"] for r in rows if r["a"]["boq_item_id"]}
    pv = {i["id"]: 0 for i in items}
    for r, v in _pv_rows(rows, now):
        a = r["a"]
        if a["boq_item_id"]:
            pv[a["boq_item_id"]] += v
        else:  # نشاط القسم يوزَّع على بنوده التي ليس لها نشاط مباشر، بنسبة قيمها
            free = [i for i in under.get(a["wbs_id"], []) if i["id"] not in direct]
            total = sum(i["amount"] for i in free)
            for i in free:
                pv[i["id"]] += v * i["amount"] // total if total else 0
    per_item = {}
    for i in items:
        ev = i["amount"] * prog.get(i["id"], 0) // FULL
        per_item[i["id"]] = _measure(i["amount"], pv[i["id"]], ev, ac.get(i["id"], 0))
    nodes = db.execute("SELECT id, code, name, parent_id FROM wbs_nodes WHERE project_id = ? ORDER BY code", (pid,)).fetchall()
    per_node = {}
    for n in nodes:
        ids = [i["id"] for i in under.get(n["id"], [])]
        per_node[n["id"]] = _measure(*(sum(per_item[x][k] for x in ids) for k in ("bac", "pv", "ev", "ac")))
    project = _measure(*(sum(m[k] for m in per_item.values()) for k in ("bac", "pv", "ev", "ac")))
    finish = max((r["pf"] for r in rows), default=None)
    forecast = max((r["ff"] for r in rows), default=None)
    project.update({"finish": finish, "forecast": forecast, "delay": (forecast - finish).days if finish else 0})
    # الحالة الزمنية تأخذ أيضًا التأخر المتوقع في تاريخ الإنجاز كنسبة من المدة
    if finish and rows:
        span = (finish - min(r["ps"] for r in rows)).days + 1
        late = project["delay"] * FULL // span if project["delay"] > 0 else 0
        project["status"] = worst(project["status"], rag(FULL - late)) if (project["pv"] or late) else project["status"]
    return {"project": project, "by_item": per_item, "nodes": per_node, "wbs": nodes, "rows": rows,
            "item_rows": db.execute("SELECT b.*, w.code AS wbs_code FROM boq_items b JOIN wbs_nodes w ON w.id = b.wbs_id "
                                    "WHERE b.project_id = ? ORDER BY b.code", (pid,)).fetchall()}


def most_deviating(ind, n=5):
    """البنود الأسوأ أداءً: الأدنى في أقل المؤشرين."""
    scored = []
    for iid, m in ind["by_item"].items():
        idx = [x for x in (m["spi"], m["cpi"]) if x is not None]
        if idx and min(idx) < 9500:
            scored.append((min(idx), iid))
    return [iid for _s, iid in sorted(scored)[:n]]


def cost_curve(db, pid, rows, now=None) -> list[dict]:
    """التكلفة المخططة مقابل الفعلية على الزمن (البند 3.4)، تراكميًا لكل فترة، والفعلية حتى اليوم فقط."""
    now = now or T.today()
    if not rows:
        return []
    start = min(r["ps"] for r in rows)
    end = max(max(r["pf"] for r in rows), max(r["ff"] for r in rows))
    out, last = [], start - timedelta(days=1)
    for t in T.periods(start, end):
        out.append({"date": t, "planned": T.planned_value(rows, t),
                    "actual": sum(actual_cost(db, pid, min(t, now)).values()) if last < now else None})
        last = t
    return out
