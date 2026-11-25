from fastapi import APIRouter, Body, Request

from ..db import q, x
from ..util import nz, num, ok, s

r = APIRouter(tags=["pm"])

MONTHS = [f"m{i}" for i in range(1, 13)]
DATES = [f"m{i}_date" for i in range(1, 13)]


@r.get("/pm/list")
def pm_list(request: Request):
    year = request.query_params.get("year", "")
    return ok(q(
        """SELECT p.*, e.equip_name, e.location, e.eval_grade
           FROM pm_plans p JOIN equipment e ON e.equip_code=p.equip_code
           WHERE p.plan_year=COALESCE(NULLIF(%s,''), YEAR(NOW()))
           ORDER BY e.location, e.equip_code""", (year,)))


@r.post("/pm/upsert-plan")
def pm_upsert_plan(b: dict = Body(default_factory=dict)):
    cols = MONTHS + DATES
    sql = f"""INSERT INTO pm_plans (equip_code, plan_year, {', '.join(cols)})
              VALUES (%s,%s,{','.join(['%s'] * 24)})
              ON DUPLICATE KEY UPDATE {', '.join(f'{c}=VALUES({c})' for c in cols)}, updated_at=NOW()"""
    x(sql, (b.get("equip_code"), b.get("plan_year"),
            *[s(b.get(m)) for m in MONTHS], *[nz(b.get(d)) for d in DATES]))
    return ok()


@r.get("/pm/master/list")
def master_list(request: Request):
    code = request.query_params.get("equip_code", "")
    return ok(q("SELECT * FROM pm_master WHERE (equip_code=%s OR %s='') ORDER BY equip_code, sort_order, id",
                (code, code)))


@r.post("/pm/master/create")
def master_create(b: dict = Body(default_factory=dict)):
    x("""INSERT INTO pm_master (equip_code, part_name, item_name, criteria, input_type, sort_order, criteria_photo)
         VALUES (%s,%s,%s,%s,%s,%s,%s)""",
      (b.get("equip_code"), s(b.get("part_name")), s(b.get("item_name")), s(b.get("criteria")),
       s(b.get("input_type")), num(b.get("sort_order")), nz(b.get("criteria_photo"))))
    return ok()


@r.post("/pm/master/update")
def master_update(b: dict = Body(default_factory=dict)):
    x("""UPDATE pm_master SET part_name=%s, item_name=%s, criteria=%s, input_type=%s,
           sort_order=COALESCE(%s, sort_order), criteria_photo=%s WHERE id=%s""",
      (s(b.get("part_name")), s(b.get("item_name")), s(b.get("criteria")), s(b.get("input_type")),
       nz(b.get("sort_order")), nz(b.get("criteria_photo")), b.get("id")))
    return ok()


@r.post("/pm/master/delete")
def master_delete(b: dict = Body(default_factory=dict)):
    x("DELETE FROM pm_master WHERE id=%s", (b.get("id"),))
    return ok()


@r.post("/pm/checklist/submit")
def checklist_submit(b: dict = Body(default_factory=dict)):
    x("""INSERT INTO pm_result (pm_master_id, equip_code, item_name, input_type, pass_fail, value_num, memo,
           check_month, inspector, inspect_date, photo_url)
         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
         ON DUPLICATE KEY UPDATE pass_fail=VALUES(pass_fail), value_num=VALUES(value_num), memo=VALUES(memo),
           inspector=VALUES(inspector), inspect_date=VALUES(inspect_date), photo_url=VALUES(photo_url),
           created_at=NOW()""",
      (b.get("pm_master_id"), b.get("equip_code"), s(b.get("item_name")), s(b.get("input_type")),
       nz(b.get("pass_fail")), nz(b.get("value_num")), s(b.get("memo")), nz(b.get("check_month")),
       nz(b.get("inspector")), nz(b.get("inspect_date")), nz(b.get("photo_url"))))
    return ok()


@r.get("/pm/result/list")
def result_list(request: Request):
    return ok(q(
        """SELECT pr.result_id AS id, pr.pm_master_id, pr.equip_code, pm.item_name, pm.input_type, pm.part_name,
             pm.criteria, pm.criteria_photo, pr.pass_fail, pr.value_num, pr.memo, pr.check_month, pr.created_at,
             pr.inspector, pr.inspect_date, pr.photo_url
           FROM pm_result pr JOIN pm_master pm ON pr.pm_master_id = pm.id
           WHERE pr.equip_code=%s ORDER BY pr.created_at DESC""",
        (request.query_params.get("equip_code", ""),)))


@r.post("/pm/result/update")
def result_update(b: dict = Body(default_factory=dict)):
    x("""UPDATE pm_result SET pass_fail=%s, value_num=%s, memo=%s, inspector=%s, inspect_date=%s, photo_url=%s
         WHERE result_id=%s""",
      (nz(b.get("pass_fail")), nz(b.get("value_num")), nz(b.get("memo")), nz(b.get("inspector")),
       nz(b.get("inspect_date")), nz(b.get("photo_url")), b.get("id")))
    return {"success": True}


@r.post("/pm/result/delete")
def result_delete(b: dict = Body(default_factory=dict)):
    rid = num(b.get("id") or b.get("result_id"))
    if not rid:
        return {"success": False, "message": "result_id is required"}
    x("DELETE FROM pm_result WHERE result_id=%s", (rid,))
    return {"success": True}
