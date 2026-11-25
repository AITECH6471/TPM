from fastapi import APIRouter, Body, Request

from ..db import q, tx, x
from ..util import num, ok, s

r = APIRouter(tags=["spare-parts"])

_MASTER_COLS = "part_code, part_name, part_spec, unit, std_cycle_days, criticality, eval_1, eval_2, eval_3, eval_4, eval_total, photo_url"


def _master_params(b):
    return (s(b.get("part_code")), s(b.get("part_name")), s(b.get("part_spec")), s(b.get("unit")),
            num(b.get("std_cycle_days")), s(b.get("criticality")),
            num(b.get("eval_1")), num(b.get("eval_2")), num(b.get("eval_3")), num(b.get("eval_4")),
            num(b.get("eval_total")), s(b.get("photo_url")))


@r.get("/spare-parts/summary")
def summary():
    return ok(q("SELECT * FROM vw_spare_parts_total ORDER BY part_name"))


@r.get("/spare-parts/master/list")
def master_list():
    return ok(q(
        """SELECT spm.*, spm.stock_qty AS total_stock,
             COALESCE(SUM(esp.safe_stock_qty), 0) AS total_safe_stock, MIN(esp.id) AS equip_spare_id
           FROM spare_parts_master spm
           LEFT JOIN equipment_spare_parts esp ON spm.part_master_id = esp.part_master_id
           GROUP BY spm.part_master_id ORDER BY spm.part_name, spm.part_spec"""))


@r.post("/spare-parts/master/create")
def master_create(b: dict = Body(default_factory=dict)):
    x(f"INSERT INTO spare_parts_master ({_MASTER_COLS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", _master_params(b))
    return ok()


@r.post("/spare-parts/master/upsert")
def master_upsert(b: dict = Body(default_factory=dict)):
    x(f"""INSERT INTO spare_parts_master ({_MASTER_COLS}) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
          ON DUPLICATE KEY UPDATE part_code=VALUES(part_code), unit=VALUES(unit),
            std_cycle_days=VALUES(std_cycle_days), criticality=VALUES(criticality),
            eval_1=VALUES(eval_1), eval_2=VALUES(eval_2), eval_3=VALUES(eval_3), eval_4=VALUES(eval_4),
            eval_total=VALUES(eval_total), photo_url=VALUES(photo_url), updated_at=NOW()""", _master_params(b))
    return ok()


@r.post("/spare-parts/master/update")
def master_update(b: dict = Body(default_factory=dict)):
    x("""UPDATE spare_parts_master SET part_code=%s, part_name=%s, part_spec=%s, unit=%s,
           std_cycle_days=%s, criticality=%s, eval_1=%s, eval_2=%s, eval_3=%s, eval_4=%s,
           eval_total=%s, updated_at=NOW() WHERE part_master_id=%s""",
      (*_master_params(b)[:11], b.get("part_master_id")))
    return ok()


@r.post("/spare-parts/master/delete")
def master_delete(b: dict = Body(default_factory=dict)):
    pid = b.get("part_master_id")
    with tx() as cur:
        cur.execute("""DELETE pt FROM parts_transaction pt
                       JOIN equipment_spare_parts esp ON esp.id = pt.equip_spare_id
                       WHERE esp.part_master_id=%s""", (pid,))
        cur.execute("DELETE FROM equipment_spare_parts WHERE part_master_id=%s", (pid,))
        cur.execute("DELETE FROM spare_parts_master WHERE part_master_id=%s", (pid,))
    return ok()


def _move(b, kind):
    pid, qty = b.get("part_master_id"), num(b.get("qty"))
    sign = "stock_qty + %s" if kind == "IN" else "GREATEST(0, stock_qty - %s)"
    with tx() as cur:
        cur.execute(f"UPDATE spare_parts_master SET stock_qty = {sign} WHERE part_master_id=%s", (qty, pid))
        cur.execute(f"UPDATE equipment_spare_parts SET stock_qty = {sign} WHERE part_master_id=%s LIMIT 1", (qty, pid))
        cur.execute("""INSERT INTO parts_transaction (equip_spare_id, trans_type, qty, worker, memo)
                       SELECT id, %s, %s, %s, %s FROM equipment_spare_parts WHERE part_master_id=%s LIMIT 1""",
                    (kind, qty, s(b.get("worker")), s(b.get("memo")), pid))
    return ok()


@r.post("/spare-parts/transaction/in")
def transaction_in(b: dict = Body(default_factory=dict)):
    return _move(b, "IN")


@r.post("/spare-parts/transaction/out")
def transaction_out(b: dict = Body(default_factory=dict)):
    return _move(b, "OUT")


@r.get("/spare-parts/transaction/list")
def transaction_list(request: Request):
    return ok(q(
        """SELECT t.trans_id, t.trans_type, t.qty, t.trans_date, t.worker, t.memo, esp.equip_code, e.equip_name
           FROM parts_transaction t
           JOIN equipment_spare_parts esp ON t.equip_spare_id = esp.id
           LEFT JOIN equipment e ON esp.equip_code = e.equip_code
           WHERE esp.part_master_id=%s ORDER BY t.trans_date DESC""",
        (request.query_params.get("part_master_id", 0),)))
