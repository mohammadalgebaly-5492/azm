"""نشاط الدخول خلال آخر 14 يومًا: عدد مرات الدخول الناجحة يوميًا، والمحاولات الفاشلة."""
from datetime import datetime, timedelta, timezone

KEY = "signin_activity"
TITLE = "Sign-in activity, last 14 days"
PERMISSION = "audit.view"
SIZE = "half"
DAYS = 14


def data(db, user, scope):
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=DAYS - 1)
    since = datetime(start.year, start.month, start.day, tzinfo=timezone.utc).isoformat(timespec="seconds")
    counts = {d: [0, 0] for d in (start + timedelta(days=i) for i in range(DAYS))}
    for at, action in db.execute("SELECT at, action FROM audit_log WHERE at >= ? AND action IN "
                                 "('login', 'login_failed', 'account_locked')", (since,)):
        d = datetime.fromisoformat(at).date()
        if d in counts:
            counts[d][0 if action == "login" else 1] += 1
    top = max((ok for ok, _f in counts.values()), default=0)
    days = [{"date": d.isoformat(), "label": d.strftime("%d/%m"), "ok": ok, "failed": bad,
             "h": round(100 * ok / top, 1) if top else 0} for d, (ok, bad) in counts.items()]
    return {"days": days, "ok": sum(x["ok"] for x in days), "failed": sum(x["failed"] for x in days), "top": top}
