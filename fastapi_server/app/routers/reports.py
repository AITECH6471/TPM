from fastapi import APIRouter, BackgroundTasks, Body

from ..db import q, tx, x
from ..push import send_all
from ..util import nz, num, ok, s

r = APIRouter(tags=["reports"])

# report.html이 보내는 영문 상태코드 → 한글
STATUS_CODES = {"RECEIVED": "접수", "INSPECTING": "확인중", "REPAIRING": "수리중", "DONE": "완료"}


def new_status(b: dict) -> str:
    return STATUS_CODES.get(b.get("status_code")) or s(b.get("status"))


@r.get("/report/list")
def report_list():
    return ok(q(
        """SELECT r.report_id, r.equip_code, r.report_dt, r.report_type, r.priority, r.line_impact,
             r.symptom_tag, r.symptom, r.reporter, r.status, r.photo_url AS report_photo_url,
             e.equip_name, e.location, e.photo_url AS equip_photo_url,
             a.technician, a.cause_group, a.cause, a.action_detail, a.downtime_min, a.action_dt
           FROM breakdown_report r
           LEFT JOIN equipment e ON e.equip_code = r.equip_code
           LEFT JOIN action_history a ON a.action_id = (
             SELECT MAX(a2.action_id) FROM action_history a2 WHERE a2.report_id = r.report_id)
           ORDER BY FIELD(r.status,'접수','확인중','수리중','완료'), r.report_dt DESC, r.report_id DESC"""))


@r.post("/report/create")
def report_create(bg: BackgroundTasks, b: dict = Body(default_factory=dict)):
    code = b.get("equip_code")
    with tx() as cur:
        cur.execute(
            """INSERT INTO breakdown_report (equip_code, report_type, priority, line_impact, symptom_tag,
                 symptom, photo_url, reporter, reporter_dept, status)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'접수')""",
            (code, s(b.get("report_type")), s(b.get("priority")), s(b.get("line_impact")),
             s(b.get("symptom_tag")), s(b.get("symptom")), s(b.get("photo_url")),
             s(b.get("reporter")), s(b.get("reporter_dept"))))
        report_id = cur.lastrowid
        cur.execute("UPDATE equipment SET status='접수' WHERE equip_code=%s", (code,))
        cur.execute("SELECT location, equip_name FROM equipment WHERE equip_code=%s", (code,))
        info = cur.fetchone() or {}
    bg.add_task(send_all, "🚨 신규 안돈 접수",
                f"라인: {info.get('location') or '-'} | 설비: {code or '-'} | 우선순위: {b.get('priority') or '-'}\n{b.get('symptom') or '-'}")
    return {"success": True, "report_id": report_id, "data": [{"report_id": report_id, **info}]}


@r.put("/report/update-status")
def report_update_status(b: dict = Body(default_factory=dict)):
    x("UPDATE breakdown_report SET status=%s WHERE report_id=%s", (s(b.get("status")), b.get("report_id")))
    return ok()


@r.post("/action/create")
def action_create(bg: BackgroundTasks, b: dict = Body(default_factory=dict)):
    st = new_status(b)
    code, rid = b.get("equip_code"), b.get("report_id")
    with tx() as cur:
        cur.execute(
            """INSERT INTO action_history (report_id, equip_code, technician, cause_group, cause, cause_detail,
                 action_detail, result, downtime_min, delay_type, delay_reason, photo_url, status_changed_to)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, code, s(b.get("technician")), s(b.get("cause_group")), s(b.get("cause")),
             s(b.get("cause_detail")), s(b.get("action_detail")), s(b.get("result")),
             num(b.get("downtime_min")), s(b.get("delay_type")), s(b.get("delay_reason")),
             s(b.get("photo_url")), st))
        if st:
            cur.execute("UPDATE breakdown_report SET status=%s WHERE report_id=%s", (st, rid))
        # 기존 n8n 동작 그대로: DONE이면 설비 '정상', 그 외 상태값이 있으면 그 값
        eq = "정상" if b.get("status_code") == "DONE" else st
        if eq:
            cur.execute("UPDATE equipment SET status=%s WHERE equip_code=%s", (eq, code))
    bg.add_task(send_all, "✅ 고장 처리 완료", f"설비: {code or '-'} | 조치자: {b.get('technician') or '-'}")
    return ok()


# ---- 설비 상세 '고장 이력' 추가/수정/삭제 (신규) ----

def _dt(v):
    v = nz(v)
    return str(v).replace("T", " ") if v else None


@r.post("/report/history-add")
def history_add(b: dict = Body(default_factory=dict)):
    """과거 이력 직접 등록. report/create와 달리 설비 상태 변경과 푸시 알람이 없다."""
    st = s(b.get("status")) or "완료"
    with tx() as cur:
        cur.execute(
            """INSERT INTO breakdown_report (equip_code, report_dt, report_type, symptom, reporter, status)
               VALUES (%s, COALESCE(%s, NOW()), %s, %s, %s, %s)""",
            (b.get("equip_code"), _dt(b.get("report_dt")), s(b.get("report_type")), s(b.get("symptom")),
             s(b.get("reporter")), st))
        rid = cur.lastrowid
        if s(b.get("technician")) or s(b.get("action_detail")) or num(b.get("downtime_min")):
            cur.execute(
                """INSERT INTO action_history (report_id, equip_code, technician, action_detail, downtime_min,
                     status_changed_to)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (rid, b.get("equip_code"), s(b.get("technician")), s(b.get("action_detail")),
                 num(b.get("downtime_min")), st))
    return {"success": True, "report_id": rid}


@r.post("/report/update")
def history_update(b: dict = Body(default_factory=dict)):
    """접수 내용 + 가장 최근 조치 1건을 함께 수정. 조치가 없으면 새로 만든다."""
    rid = b.get("report_id")
    st = s(b.get("status"))  # 빈 값이면 상태 변경 안 함
    with tx() as cur:
        cur.execute(
            """UPDATE breakdown_report SET report_dt=COALESCE(%s, report_dt), report_type=%s, symptom=%s,
                 reporter=%s, status=COALESCE(NULLIF(%s,''), status) WHERE report_id=%s""",
            (_dt(b.get("report_dt")), s(b.get("report_type")), s(b.get("symptom")), s(b.get("reporter")), st, rid))
        cur.execute("SELECT MAX(action_id) AS aid FROM action_history WHERE report_id=%s", (rid,))
        aid = (cur.fetchone() or {}).get("aid")
        if aid:
            cur.execute(
                """UPDATE action_history SET technician=%s, action_detail=%s, downtime_min=%s WHERE action_id=%s""",
                (s(b.get("technician")), s(b.get("action_detail")), num(b.get("downtime_min")), aid))
        elif s(b.get("technician")) or s(b.get("action_detail")) or num(b.get("downtime_min")):
            cur.execute(
                """INSERT INTO action_history (report_id, equip_code, technician, action_detail, downtime_min)
                   VALUES (%s,%s,%s,%s,%s)""",
                (rid, b.get("equip_code"), s(b.get("technician")), s(b.get("action_detail")), num(b.get("downtime_min"))))
    return {"success": True}


@r.post("/report/delete")
def history_delete(b: dict = Body(default_factory=dict)):
    """접수 삭제. action_history는 FK ON DELETE CASCADE로 함께 삭제된다."""
    x("DELETE FROM breakdown_report WHERE report_id=%s", (b.get("report_id"),))
    return {"success": True}
