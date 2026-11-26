"""DB 없이 실행: python -m pytest tests -q"""
import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app

# n8n TPM 워크플로우의 webhook 44개 (2026-11-25 기준)
N8N = {
    ("GET", "/equipment/detail"),
    ("GET", "/equipment/list"),
    ("GET", "/equipment/spare-parts"),
    ("GET", "/equipment/sub-items"),
    ("GET", "/notification/recipients"),
    ("GET", "/pm/list"),
    ("GET", "/pm/master/list"),
    ("GET", "/pm/result/list"),
    ("GET", "/report/list"),
    ("GET", "/settings/get"),
    ("GET", "/spare-parts/master/list"),
    ("GET", "/spare-parts/summary"),
    ("GET", "/spare-parts/transaction/list"),
    ("GET", "/stats/equipment"),
    ("POST", "/action/create"),
    ("POST", "/equipment/delete"),
    ("POST", "/equipment/spare-parts/delete"),
    ("POST", "/equipment/spare-parts/upsert"),
    ("POST", "/equipment/sub-items/delete"),
    ("POST", "/equipment/sub-items/upsert"),
    ("POST", "/equipment/upsert"),
    ("POST", "/notification/recipients/delete"),
    ("POST", "/notification/recipients/upsert"),
    ("POST", "/photo/upload"),
    ("POST", "/photo/upload-parts"),
    ("POST", "/photo/upload-sub"),
    ("POST", "/pm/checklist/submit"),
    ("POST", "/pm/master/create"),
    ("POST", "/pm/master/delete"),
    ("POST", "/pm/master/update"),
    ("POST", "/pm/result/delete"),
    ("POST", "/pm/result/update"),
    ("POST", "/pm/upsert-plan"),
    ("POST", "/push/subscribe"),
    ("POST", "/push/unsubscribe"),
    ("POST", "/report/create"),
    ("POST", "/settings/save"),
    ("POST", "/spare-parts/master/create"),
    ("POST", "/spare-parts/master/delete"),
    ("POST", "/spare-parts/master/update"),
    ("POST", "/spare-parts/master/upsert"),
    ("POST", "/spare-parts/transaction/in"),
    ("POST", "/spare-parts/transaction/out"),
    ("PUT", "/report/update-status"),
}
NEW = {("POST", "/report/history-add"), ("POST", "/report/update"), ("POST", "/report/delete"),
       ("GET", "/pm/result/year")}


def test_all_endpoints_exist_under_api():
    have = {(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods}
    missing = {(m, "/api" + p) for m, p in N8N | NEW} - have
    assert not missing, f"FastAPI에 없는 경로: {sorted(missing)}"


def test_prefixes():
    c = TestClient(app)
    for p in ("/api/health", "/webhook/health", "/health"):
        assert c.get(p).json() == {"ok": True}


def test_static_serves_only_allowed_files():
    c = TestClient(app)
    for p in ("/", "/report.html", "/sw.js", "/manifest.json", "/js/core.js"):
        assert c.get(p).status_code == 200, p
    for p in ("/CNAME", "/fastapi_server/.env.example", "/fastapi_server/app/config.py", "/.git/config",
              "/js/../fastapi_server/.env.example", "/js/%2e%2e/fastapi_server/.env.example",
              "/js/..%5cfastapi_server%5c.env.example"):
        assert c.get(p).status_code == 404, p
    assert c.get("/report.html?path=fastapi_server/.env.example").content.decode("utf-8-sig").lstrip().lower().startswith("<!doctype")


def test_stats_month_format(sqllog):
    TestClient(app).get("/api/stats/equipment")
    assert "'%Y-%m'" in sqllog[0] and "%%" not in sqllog[0]


def test_pm_result_year_filters_by_year(monkeypatch):
    from app.routers import pm
    seen = {}
    monkeypatch.setattr(pm, "q", lambda sql, p=None: seen.update(sql=sql, p=p) or [])
    assert TestClient(app).get("/api/pm/result/year?year=2026").json()["success"]
    assert seen["p"] == ("2026-%",) and "LIKE %s" in seen["sql"]
    TestClient(app).get("/api/pm/result/year?year=2026' OR 1=1")   # 숫자가 아니면 빈 연도 → 결과 없음
    assert seen["p"] == ("-%",)


@pytest.fixture
def sqllog(monkeypatch):
    """모든 SQL을 DB 대신 기록하고, %s 개수와 파라미터 개수가 맞는지 즉시 검사"""
    calls = []

    class Cur:
        lastrowid = 7
        def execute(self, sql, params=None):
            n = sql.count("%s")
            assert n == len(params or ()), f"플레이스홀더 {n} != 파라미터 {len(params or ())}\n{sql}"
            calls.append(sql)
            return 1
        def fetchone(self): return {"aid": 1, "location": "L3", "equip_name": "CNC"}
        def fetchall(self): return []

    from contextlib import contextmanager

    @contextmanager
    def fake_tx():
        yield Cur()

    for mod in ("app.db", "app.routers.equipment", "app.routers.parts", "app.routers.pm",
                "app.routers.reports", "app.routers.misc", "app.push"):
        m = __import__(mod, fromlist=["x"])
        if hasattr(m, "tx"): monkeypatch.setattr(m, "tx", fake_tx)
        if hasattr(m, "q"): monkeypatch.setattr(m, "q", lambda sql, p=None: (Cur().execute(sql, p), [])[1])
        if hasattr(m, "x"): monkeypatch.setattr(m, "x", lambda sql, p=None: Cur().execute(sql, p))
    return calls


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/equipment/upsert", {"equip_code": "A-1", "equip_name": "x", "asset_owner": "AIT", "eval_1_1": "3"}),
    ("POST", "/equipment/upsert", {"equip_code": "A-1"}),
    ("POST", "/report/history-add", {"equip_code": "A-1", "symptom": "s", "report_dt": "2026-11-12T09:14", "technician": "t"}),
    ("POST", "/report/update", {"report_id": 1, "equip_code": "A-1", "symptom": "s", "status": "완료", "downtime_min": "30"}),
    ("POST", "/report/delete", {"report_id": 1}),
    ("POST", "/report/create", {"equip_code": "A-1", "symptom": "s"}),
    ("POST", "/action/create", {"report_id": 1, "equip_code": "A-1", "status_code": "DONE"}),
    ("POST", "/pm/upsert-plan", {"equip_code": "A-1", "plan_year": 2026, "m1": "P"}),
    ("POST", "/pm/checklist/submit", {"pm_master_id": 1, "equip_code": "A-1"}),
    ("POST", "/spare-parts/master/update", {"part_master_id": 1, "part_name": "p"}),
    ("POST", "/spare-parts/transaction/in", {"part_master_id": 1, "qty": 3}),
    ("POST", "/spare-parts/transaction/out", {"part_master_id": 1, "qty": 3}),
    ("GET", "/stats/equipment", None),
])
def test_sql_placeholders_match(sqllog, method, path, body):
    c = TestClient(app, raise_server_exceptions=True)
    res = c.request(method, path, json=body) if body is not None else c.request(method, path)
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True


def test_history_delete_uses_cascade(sqllog):
    TestClient(app).post("/report/delete", json={"report_id": 5})
    assert sqllog == ["DELETE FROM breakdown_report WHERE report_id=%s"]


def test_cors_preflight():
    r = TestClient(app).options("/report/list", headers={
        "Origin": "https://tpm.aitkorea.app", "Access-Control-Request-Method": "GET"})
    assert r.headers["access-control-allow-origin"] == "https://tpm.aitkorea.app"


def test_report_create_sends_discord(sqllog, monkeypatch):
    """고장접수 시 디스코드 웹훅으로 한 번 전송한다(웹훅 URL이 있을 때만)."""
    from app import discord
    from app.config import settings
    sent = []
    monkeypatch.setattr(settings, "discord_breakdown_webhook_url", "https://discord.test/hook")
    monkeypatch.setattr(discord, "post", lambda payload, url=None: sent.append(payload) or True)
    monkeypatch.setattr("app.routers.reports.send_all", lambda *a, **k: None)
    TestClient(app).post("/api/report/create", json={
        "equip_code": "A-1", "priority": "보통", "line_impact": "라인정지", "symptom": "누유", "reporter": "홍길동"})
    assert len(sent) == 1
    e = sent[0]["embeds"][0]
    assert "#7" in e["title"] and "라인정지" in e["title"] and e["color"] == 0xE53935
    vals = {f["name"]: f["value"] for f in e["fields"]}
    assert vals["위치/라인"] == "L3" and "CNC" in vals["설비"] and vals["증상"] == "누유"


def test_discord_skipped_without_url(monkeypatch):
    from app import discord
    from app.config import settings
    monkeypatch.setattr(settings, "discord_breakdown_webhook_url", "")
    called = []
    monkeypatch.setattr(discord, "post", lambda *a, **k: called.append(1))
    assert discord.notify_breakdown(1, {"equip_code": "A-1"}, {}) is False and not called


def test_discord_sets_user_agent(monkeypatch):
    """디스코드는 urllib 기본 User-Agent를 403으로 막는다."""
    from app import discord
    seen = {}

    class Res:
        status = 204
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        return Res()
    monkeypatch.setattr(discord.urllib.request, "urlopen", fake_open)
    assert discord.post({"content": "x"}, url="https://discord.test/hook") is True
    assert seen["ua"] and "urllib" not in seen["ua"].lower()
