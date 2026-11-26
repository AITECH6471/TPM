"""설비 고장접수 → 디스코드 웹훅 알림.

DISCORD_BREAKDOWN_WEBHOOK_URL 이 비어 있으면 조용히 건너뛴다. 전송 실패도 로그만 남기고 넘어간다
(접수 저장은 이미 끝난 뒤 백그라운드로 실행되므로 영향 없음).
"""
import json
import logging
import urllib.request
from datetime import datetime

from .config import settings

log = logging.getLogger("discord")

# 디스코드는 urllib 기본 User-Agent(Python-urllib/x.y)를 403으로 막는다 → 반드시 지정
_UA = "AIT-TPM/1.0 (+https://tpm.aitkorea.app)"

# 라인정지 또는 긴급이면 빨강, 높음이면 주황, 나머지 노랑
_RED, _ORANGE, _YELLOW = 0xE53935, 0xFB8C00, 0xFDD835


def _color(priority: str, line_impact: str) -> int:
    if line_impact == "라인정지" or priority in ("긴급", "최우선"):
        return _RED
    if priority == "높음":
        return _ORANGE
    return _YELLOW


def _v(x, limit: int = 1024) -> str:
    t = str(x).strip() if x not in (None, "") else ""
    if not t or t == "undefined":
        return "-"
    return t if len(t) <= limit else t[: limit - 1] + "…"


def build_breakdown_message(report_id, b: dict, info: dict) -> dict:
    priority, impact = _v(b.get("priority")), _v(b.get("line_impact"))
    stop = impact == "라인정지"
    fields = [
        {"name": "설비", "value": f"{_v(info.get('equip_name'))}\n`{_v(b.get('equip_code'))}`", "inline": True},
        {"name": "위치/라인", "value": _v(info.get("location")), "inline": True},
        {"name": "유형", "value": _v(b.get("report_type")), "inline": True},
        {"name": "우선순위", "value": priority, "inline": True},
        {"name": "라인 영향", "value": f"🛑 {impact}" if stop else impact, "inline": True},
        {"name": "접수자", "value": " / ".join(p for p in (_v(b.get("reporter")), _v(b.get("reporter_dept"))) if p != "-") or "-", "inline": True},
        {"name": "증상", "value": (f"[{_v(b.get('symptom_tag'))}] " if _v(b.get("symptom_tag")) != "-" else "") + _v(b.get("symptom"), 900)},
    ]
    embed = {
        "title": f"🚨 설비 고장접수 #{report_id}" + (" — 라인정지" if stop else ""),
        "url": settings.push_url,
        "color": _color(priority, impact),
        "fields": fields,
        "timestamp": datetime.now().astimezone().isoformat(),
        "footer": {"text": "AIT 설비 관리시스템"},
    }
    photo = _v(b.get("photo_url"), 2000)
    if photo.startswith("http"):
        embed["image"] = {"url": photo}
    return {"username": "설비 고장접수", "embeds": [embed], "allowed_mentions": {"parse": []}}


def post(payload: dict, url: str | None = None) -> bool:
    url = (url or settings.discord_breakdown_webhook_url).strip()
    if not url:
        return False
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": _UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return 200 <= res.status < 300
    except Exception as e:  # 네트워크 오류, 4xx/5xx 등
        log.warning("discord webhook failed: %s", e)
        return False


def notify_breakdown(report_id, b: dict, info: dict) -> bool:
    if not settings.discord_breakdown_webhook_url.strip():
        return False
    return post(build_breakdown_message(report_id, b, info))
