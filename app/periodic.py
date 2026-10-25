"""التقارير الأسبوعية والشهرية التلقائية لكل مشروع (الدستور، البند 4.3): الحالة بالألوان، ومنحنى التقدم المخطط مقابل الفعلي،
والتكلفة المخططة مقابل الفعلية، وأكثر البنود انحرافًا. تُحسب من البيانات المعتمدة حتى نهاية الفترة، فتظهر كل فترة تلقائيًا
دون أن يُعِدها أحد. الأسبوع من الأحد إلى السبت."""
from datetime import date, timedelta

from . import performance as P, schedule as T

KINDS = {"weekly": "Weekly report", "monthly": "Monthly report"}
SATURDAY = 5


def _month_end(d: date) -> date:
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def _start_of(kind, end: date) -> date:
    return end - timedelta(days=6) if kind == "weekly" else end.replace(day=1)


def first_day(db, pid):
    v = db.execute("SELECT MIN(planned_start) FROM activities WHERE project_id = ?", (pid,)).fetchone()[0]
    return T._d(v)


def periods(db, pid, kind, now=None) -> list[dict]:
    """كل الفترات من بداية الجدول حتى اليوم، الأحدث أولًا. الفترة الجارية تُحسب حتى اليوم."""
    now, start = now or T.today(), first_day(db, pid)
    if start is None or start > now:
        return []
    if kind == "weekly":
        end = start + timedelta(days=(SATURDAY - start.weekday()) % 7)
        step = lambda d: d + timedelta(days=7)  # noqa: E731
    else:
        end = _month_end(start)
        step = lambda d: _month_end(d + timedelta(days=1))  # noqa: E731
    out = []
    while _start_of(kind, end) <= now:
        out.append({"kind": kind, "start": _start_of(kind, end), "end": end, "current": end >= now})
        end = step(end)
    return out[::-1]


def valid_end(kind, end: date) -> bool:
    return end.weekday() == SATURDAY if kind == "weekly" else end == _month_end(end)


def build(db, pid, kind, end: date, now=None) -> dict | None:
    now = now or T.today()
    start = _start_of(kind, end)
    if kind not in KINDS or not valid_end(kind, end) or start > now or first_day(db, pid) is None:
        return None
    at = min(end, now)
    ind = P.indicators(db, pid, at)
    before = P.indicators(db, pid, start - timedelta(days=1))["project"]
    m = ind["project"]
    items = {b["id"]: b for b in ind["item_rows"]}
    counts = {s: db.execute("SELECT COUNT(*) FROM daily_reports WHERE project_id = ? AND status = ? AND report_date >= ? "
                            "AND report_date <= ?", (pid, s, start.isoformat(), at.isoformat())).fetchone()[0]
              for s in ("approved", "review", "returned")}
    steps = db.execute("SELECT COUNT(*) FROM scope_steps WHERE project_id = ? AND finished_on >= ? AND finished_on <= ?",
                       (pid, start.isoformat(), at.isoformat())).fetchone()[0]
    return {"kind": kind, "start": start, "end": end, "at": at, "current": end >= now, "m": m, "ind": ind,
            "period": {"ev": m["ev"] - before["ev"], "ac": m["ac"] - before["ac"], "pv": m["pv"] - before["pv"],
                       "steps": steps, **counts},
            "worst": [items[i] for i in P.most_deviating(ind)],
            "curve": T.s_curve(db, pid, ind["rows"], at), "cost": P.cost_curve(db, pid, ind["rows"], at)}
