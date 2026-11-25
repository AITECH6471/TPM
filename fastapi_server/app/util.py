from datetime import date, datetime
from decimal import Decimal


def _clean(v):
    # n8n(dateStrings)과 같은 형식: 'YYYY-MM-DD HH:MM:SS'
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)  # n8n(mysql2)도 DECIMAL을 문자열로 내려준다. 프론트가 그 형태에 맞춰져 있음
    return v


def ok(rows=None, **extra):
    """n8n과 동일한 응답: {success, data, count}"""
    data = [{k: _clean(v) for k, v in r.items()} for r in (rows or [])]
    return {"success": True, "data": data, "count": len(data), **extra}


def nz(v):
    """프론트가 보내는 빈 값('', 'null', 'undefined')을 NULL로"""
    return None if v is None or str(v).strip() in ("", "null", "undefined") else v


def num(v, default=0):
    v = nz(v)
    if v is None:
        return default
    try:
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return default


def s(v):
    """문자열 컬럼용: 없으면 빈 문자열"""
    v = nz(v)
    return "" if v is None else str(v)
