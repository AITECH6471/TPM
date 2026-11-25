"""설정 / 알림 수신자 / 푸시 구독 / 통계"""
from fastapi import APIRouter, Body

from ..db import q, tx, x
from ..util import nz, ok, s

r = APIRouter(tags=["misc"])


# ---- settings ----
def _settings():
    rows = q("SELECT base_url FROM settings WHERE settings_id = 1")
    cfg = {"base_url": (rows[0]["base_url"] if rows else "") or ""}
    return {"success": True, "data": cfg, "settings": cfg}


@r.get("/settings/get")
def settings_get():
    return _settings()


@r.post("/settings/save")
def settings_save(b: dict = Body(default_factory=dict)):
    x("""INSERT INTO settings (settings_id, base_url) VALUES (1, %s)
         ON DUPLICATE KEY UPDATE base_url=VALUES(base_url), updated_at=NOW()""", (s(b.get("base_url")),))
    return _settings()


# ---- notification recipients ----
@r.get("/notification/recipients")
def recipients():
    return ok(q("SELECT id, email, name, dept, is_active FROM notification_recipients ORDER BY name"))


@r.post("/notification/recipients/upsert")
def recipients_upsert(b: dict = Body(default_factory=dict)):
    x("""INSERT INTO notification_recipients (email, name, dept, is_active) VALUES (%s,%s,%s,%s)
         ON DUPLICATE KEY UPDATE name=VALUES(name), dept=VALUES(dept), is_active=VALUES(is_active), updated_at=NOW()""",
      (b.get("email"), s(b.get("name")), s(b.get("dept")), b.get("is_active", 1)))
    return ok()


@r.post("/notification/recipients/delete")
def recipients_delete(b: dict = Body(default_factory=dict)):
    x("DELETE FROM notification_recipients WHERE id=%s", (b.get("id"),))
    return ok()


# ---- push subscriptions ----
@r.post("/push/subscribe")
def push_subscribe(b: dict = Body(default_factory=dict)):
    x("""INSERT INTO push_subscriptions (endpoint, p256dh, auth, user_label, device_info) VALUES (%s,%s,%s,%s,%s)
         ON DUPLICATE KEY UPDATE p256dh=VALUES(p256dh), auth=VALUES(auth), user_label=VALUES(user_label),
           last_used_at=NOW()""",
      (b.get("endpoint"), b.get("p256dh"), b.get("auth"), nz(b.get("user_label")), nz(b.get("device_info"))))
    return {"success": True}


@r.post("/push/unsubscribe")
def push_unsubscribe(b: dict = Body(default_factory=dict)):
    x("DELETE FROM push_subscriptions WHERE endpoint=%s", (b.get("endpoint"),))
    return {"success": True}


# ---- stats ----
_EXCL = "report_type NOT IN ('정기점검','개선/변경','입고/이설')"


@r.get("/stats/equipment")
def stats_equipment():
    monthly = q(f"""SELECT DATE_FORMAT(report_dt,'%Y-%m') AS month, COUNT(*) AS count FROM breakdown_report
                    WHERE report_dt >= DATE_SUB(NOW(), INTERVAL 12 MONTH) AND {_EXCL}
                    GROUP BY month ORDER BY month""")
    by_loc = q(f"""SELECT e.location, COUNT(r.report_id) AS count FROM breakdown_report r
                   JOIN equipment e ON e.equip_code=r.equip_code
                   WHERE r.{_EXCL} AND r.report_dt >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
                   GROUP BY e.location ORDER BY count DESC""")
    mttr = q(f"""SELECT e.equip_code, e.equip_name, e.location, COUNT(r.report_id) AS total_breakdowns,
                   COALESCE(SUM(a.downtime_min),0) AS total_downtime, MAX(r.report_dt) AS last_fault_dt,
                   ROUND(COALESCE(SUM(a.downtime_min),0)/NULLIF(SUM(CASE WHEN r.status='완료' THEN 1 ELSE 0 END),0),1) AS mttr_min
                 FROM equipment e
                 LEFT JOIN breakdown_report r ON e.equip_code=r.equip_code AND r.{_EXCL}
                   AND r.report_dt >= DATE_SUB(NOW(), INTERVAL 12 MONTH)
                 LEFT JOIN action_history a ON a.report_id=r.report_id AND a.downtime_min>0
                 GROUP BY e.equip_code, e.equip_name, e.location
                 HAVING total_breakdowns > 0 ORDER BY mttr_min DESC LIMIT 20""")
    m, l, t = ok(monthly)["data"], ok(by_loc)["data"], ok(mttr)["data"]
    return {"success": True, "monthly_trend": m, "by_location": l, "data": t, "legacy_data": [m, l, t]}
