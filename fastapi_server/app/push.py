"""브라우저 푸시 발송. VAPID 키가 없거나 pywebpush가 없으면 조용히 건너뛴다(접수/조치 저장은 영향 없음)."""
import json
import logging

from .config import settings
from .db import q, x

log = logging.getLogger("push")


def send_all(title: str, body: str) -> dict:
    if not (settings.vapid_public_key and settings.vapid_private_key):
        return {"sent": 0, "reason": "vapid_not_configured"}
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return {"sent": 0, "reason": "pywebpush_not_installed"}

    subs = q("SELECT endpoint, p256dh, auth FROM push_subscriptions")
    payload = json.dumps({"title": title, "body": body, "url": settings.push_url}, ensure_ascii=False)
    sent = failed = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=86400,
            )
            sent += 1
        except WebPushException as e:
            failed += 1
            # 만료된 구독(404/410)은 삭제
            if e.response is not None and e.response.status_code in (404, 410):
                x("DELETE FROM push_subscriptions WHERE endpoint=%s", (sub["endpoint"],))
            else:
                log.warning("push failed: %s", e)
        except Exception as e:  # 네트워크 오류 등
            failed += 1
            log.warning("push error: %s", e)
    return {"sent": sent, "failed": failed, "total": len(subs)}
