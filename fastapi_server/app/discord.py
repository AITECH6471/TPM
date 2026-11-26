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


def _md(x, limit: int = 1024) -> str:
    """사용자 입력값이 디스코드 마크다운으로 깨지지 않게 이스케이프(+줄바꿈 정리)."""
    s = " ".join(_v(x, limit).split())
    for ch in "\\*_~`|>":
        s = s.replace(ch, "\\" + ch)
    return s


def build_breakdown_message(report_id, b: dict, info: dict) -> dict:
    """디스코드 알림 공통 양식(2026-11-26 사용자요청 "웹훅 메시지 양식 통일" — 공정문서 점검알람·불량알림과 동일):
    제목 "이모지 [라인] 종류 · 핵심" / 본문 **묶음** + "└ 항목 · 값" 줄 / 하단 "시스템 · 시각"."""
    priority, impact = _v(b.get("priority")), _v(b.get("line_impact"))
    stop = impact == "라인정지"
    line = _v(info.get("location"))
    reporter = " / ".join(p for p in (_md(b.get("reporter")), _md(b.get("reporter_dept"))) if p != "-") or "-"
    tag = _md(b.get("symptom_tag"))
    symptom = [_md(s) for s in _v(b.get("symptom"), 900).splitlines() if s.strip()] or ["-"]
    if tag != "-":
        symptom[0] = f"[{tag}] {symptom[0]}"
    sections = [
        "**설비**\n"
        f"└ {_md(info.get('equip_name'))} · `{_v(b.get('equip_code')).replace('`', '')}`\n"
        f"└ 유형 · {_md(b.get('report_type'))}",
        "**상태**\n"
        f"└ 우선순위 · **{_md(priority)}**\n"
        f"└ 라인 영향 · " + (f"🛑 **{_md(impact)}**" if stop else _md(impact)),
        "**증상**\n" + "\n".join(f"└ {s}" for s in (symptom or ["-"])),
        f"**접수자**\n└ {reporter}",
    ]
    now = datetime.now().astimezone()
    embed = {
        "title": f"🚨 [{line}] 설비 고장접수 · #{report_id}" + (" · 라인정지" if stop else ""),
        "url": settings.push_url,
        "color": _color(priority, impact),
        "description": "\n\n".join(sections)[:4000],
        "footer": {"text": f"설비 관리시스템 · {now.strftime('%m-%d %H:%M')} 접수"},
    }
    photo = _v(b.get("photo_url"), 2000)
    if photo.startswith("http"):
        embed["image"] = {"url": photo}
    return {"username": "AIT 설비알림", "embeds": [embed], "allowed_mentions": {"parse": []}}


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
