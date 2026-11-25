from fastapi import APIRouter, Body, Request

from ..db import q, tx, x
from ..util import nz, ok, s

r = APIRouter(tags=["equipment"])

EVAL_KEYS = ["eval_1_1", "eval_1_2", "eval_2_3", "eval_2_4", "eval_3_5", "eval_3_6",
             "eval_4_7", "eval_4_8", "eval_4_9", "eval_5_10", "eval_5_11", "eval_total"]


@r.get("/equipment/list")
def equipment_list():
    return ok(q("SELECT * FROM vw_equip_summary ORDER BY equip_code"))


@r.get("/equipment/detail")
def equipment_detail(request: Request):
    code = request.query_params.get("equip_code", "")
    equip = q("SELECT * FROM equipment WHERE equip_code=%s", (code,))
    history = q(
        """SELECT r.report_id, r.report_dt, r.report_type, r.priority, r.line_impact,
             r.symptom_tag, r.symptom, r.photo_url AS report_photo, r.reporter, r.status,
             a.action_id, a.action_dt, a.technician, a.cause_group, a.cause,
             a.action_detail, a.result, a.downtime_min, a.photo_url AS action_photo,
             COALESCE(a.photo_url, r.photo_url) AS photo_url
           FROM breakdown_report r
           LEFT JOIN action_history a ON a.report_id = r.report_id
           WHERE r.equip_code=%s
           ORDER BY r.report_dt DESC, r.report_id DESC, a.action_id DESC""", (code,))
    parts = q(
        """SELECT esp.id, esp.equip_code, esp.part_master_id, esp.stock_qty, esp.safe_stock_qty, esp.note,
             spm.part_code, spm.part_name, spm.part_spec, spm.unit, spm.criticality
           FROM equipment_spare_parts esp
           JOIN spare_parts_master spm ON esp.part_master_id = spm.part_master_id
           WHERE esp.equip_code=%s ORDER BY spm.part_name""", (code,))
    base = ok(history)  # 날짜 등 직렬화는 ok()가 처리
    e = ok(equip)["data"]
    p = ok(parts)["data"]
    return {"success": True, "equipment": e[0] if e else None, "history": base["data"],
            "spare_parts": p, "data": [e, base["data"], p]}


@r.post("/equipment/upsert")
def equipment_upsert(b: dict = Body(default_factory=dict)):
    ev = {k: nz(b.get(k)) for k in EVAL_KEYS}
    owner = b.get("asset_owner")
    owner_ins = owner if owner in ("LSAT", "AIT") else None
    vendor = {k: nz(b.get(k)) for k in ("vendor_name", "vendor_contact", "vendor_phone")}
    # 키가 아예 없으면(None) 기존 값 유지, 빈 문자열이면 NULL로 지움 (n8n의 'undefined' 규칙과 동일)
    keep = {k: (b.get(k) is None or b.get(k) == "undefined") for k in vendor}
    raw = {k: b.get(k) for k in vendor}
    sql = f"""INSERT INTO equipment (
        equip_code, equip_name, location, manufacturer, vendor_name, vendor_contact, vendor_phone,
        manager, manager_dept, asset_no, asset_owner, mfg_date, spec, photo_url, status,
        {', '.join(EVAL_KEYS)}, eval_grade, pm_yn
      ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(NULLIF(%s,''),'정상'),
        {', '.join(['COALESCE(%s,0)'] * len(EVAL_KEYS))}, %s, COALESCE(%s,0))
      ON DUPLICATE KEY UPDATE
        equip_name=VALUES(equip_name), location=VALUES(location), manufacturer=VALUES(manufacturer),
        vendor_name=IF(%s, vendor_name, NULLIF(%s,'')),
        vendor_contact=IF(%s, vendor_contact, NULLIF(%s,'')),
        vendor_phone=IF(%s, vendor_phone, NULLIF(%s,'')),
        manager=VALUES(manager), manager_dept=VALUES(manager_dept), asset_no=VALUES(asset_no),
        asset_owner=CASE WHEN %s IN ('LSAT','AIT') THEN %s WHEN %s='-' THEN NULL ELSE asset_owner END,
        mfg_date=VALUES(mfg_date), spec=VALUES(spec),
        photo_url=IF(VALUES(photo_url)!='', VALUES(photo_url), photo_url),
        status=VALUES(status),
        {', '.join(f'{k}=COALESCE(%s,{k})' for k in EVAL_KEYS)},
        eval_grade=COALESCE(%s, eval_grade),
        pm_yn=COALESCE(%s, pm_yn),
        updated_at=NOW()"""
    grade = nz(b.get("eval_grade"))
    pm = nz(b.get("pm_yn"))
    params = (
        b.get("equip_code"), s(b.get("equip_name")), s(b.get("location")), s(b.get("manufacturer")),
        vendor["vendor_name"], vendor["vendor_contact"], vendor["vendor_phone"],
        s(b.get("manager")), s(b.get("manager_dept")), s(b.get("asset_no")), owner_ins,
        nz(b.get("mfg_date")), s(b.get("spec")), s(b.get("photo_url")), s(b.get("status")),
        *[ev[k] for k in EVAL_KEYS], s(grade), pm,
        # ON DUPLICATE KEY UPDATE 구간
        keep["vendor_name"], raw["vendor_name"], keep["vendor_contact"], raw["vendor_contact"],
        keep["vendor_phone"], raw["vendor_phone"],
        owner, owner, owner,
        *[ev[k] for k in EVAL_KEYS], grade, pm,
    )
    x(sql, params)
    return ok()


@r.post("/equipment/delete")
def equipment_delete(b: dict = Body(default_factory=dict)):
    with tx() as cur:
        cur.execute("DELETE FROM breakdown_report WHERE equip_code=%s", (b.get("equip_code"),))
        cur.execute("DELETE FROM equipment WHERE equip_code=%s", (b.get("equip_code"),))
    return ok()


@r.get("/equipment/spare-parts")
def equipment_spare_parts(request: Request):
    code = request.query_params.get("equip_code", "")
    return ok(q(
        """SELECT esp.id, esp.equip_code, esp.part_master_id, esp.stock_qty, esp.safe_stock_qty, esp.note,
             spm.part_code, spm.part_name, spm.part_spec, spm.unit, spm.std_cycle_days, spm.criticality
           FROM equipment_spare_parts esp
           JOIN spare_parts_master spm ON esp.part_master_id = spm.part_master_id
           WHERE (%s = '' OR esp.equip_code = %s)
           ORDER BY esp.equip_code, spm.part_name""", (code, code)))


@r.post("/equipment/spare-parts/upsert")
def equipment_spare_parts_upsert(b: dict = Body(default_factory=dict)):
    x("""INSERT INTO equipment_spare_parts (equip_code, part_master_id, stock_qty, safe_stock_qty, note)
         VALUES (%s,%s,%s,%s,%s)
         ON DUPLICATE KEY UPDATE stock_qty=VALUES(stock_qty), safe_stock_qty=VALUES(safe_stock_qty),
           note=VALUES(note), updated_at=NOW()""",
      (b.get("equip_code"), b.get("part_master_id"), b.get("stock_qty") or 0,
       b.get("safe_stock_qty") or 0, s(b.get("note"))))
    return ok()


@r.post("/equipment/spare-parts/delete")
def equipment_spare_parts_delete(b: dict = Body(default_factory=dict)):
    x("DELETE FROM equipment_spare_parts WHERE id=%s", (b.get("id"),))
    return ok()


@r.get("/equipment/sub-items")
def sub_items(request: Request):
    code = request.query_params.get("equip_code", "")
    return ok(q(
        """SELECT id, equip_code, sub_code, sub_name, quantity, memo, photo_url, created_at
           FROM equipment_sub_items WHERE (%s = '' OR equip_code = %s)
           ORDER BY equip_code, sub_code""", (code, code)))


@r.post("/equipment/sub-items/upsert")
def sub_items_upsert(b: dict = Body(default_factory=dict)):
    x("""INSERT INTO equipment_sub_items (equip_code, sub_code, sub_name, quantity, memo, photo_url)
         VALUES (%s,%s,%s,%s,%s,%s)
         ON DUPLICATE KEY UPDATE sub_name=VALUES(sub_name), quantity=VALUES(quantity),
           memo=VALUES(memo), photo_url=VALUES(photo_url), updated_at=NOW()""",
      (b.get("equip_code"), b.get("sub_code"), s(b.get("sub_name")), b.get("quantity") or 0,
       s(b.get("memo")), s(b.get("photo_url"))))
    return ok()


@r.post("/equipment/sub-items/delete")
def sub_items_delete(b: dict = Body(default_factory=dict)):
    x("DELETE FROM equipment_sub_items WHERE id=%s", (b.get("id"),))
    return ok()
