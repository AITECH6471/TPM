import logging
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import equipment, misc, parts, pm, photo, reports

log = logging.getLogger("api")
app = FastAPI(title="AIT TPM API", version="1.0.0")

# CORS는 여기서 한 번만 설정 (n8n의 헤더 중복 문제 없음)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 같은 라우터를 '/api', '/webhook', '/' 에 붙인다.
#   baseUrl = https://tpm.aitkorea.app/api  → /api/report/list   (운영)
#   baseUrl = https://<host>/webhook        → /webhook/report/list (n8n 주소 형태 그대로)
health = APIRouter()


@health.get("/health")
def health_check():
    return {"ok": True}


for prefix in ("/api", "/webhook", ""):
    for router in [m.r for m in (equipment, parts, pm, reports, misc, photo)] + [health]:
        app.include_router(router, prefix=prefix, include_in_schema=prefix == "/api")

# 화면 파일: 저장소 루트에는 서버 코드(.env 등)도 있으므로 폴더째 열지 않고 아래 목록만 제공한다.
STATIC = Path(settings.static_dir) if settings.static_dir else Path(__file__).resolve().parents[2]
PAGES = ("index.html", "report.html", "sw.js", "manifest.json", "ait-logo.png", "style.css", "script.js")


def _serve(path: Path):
    def endpoint():
        return FileResponse(path, headers={"Cache-Control": "no-cache"})
    return endpoint


if (STATIC / "index.html").is_file():
    app.add_api_route("/", _serve(STATIC / "index.html"), include_in_schema=False)
    for name in PAGES:
        app.add_api_route(f"/{name}", _serve(STATIC / name), include_in_schema=False)
    app.mount("/js", StaticFiles(directory=STATIC / "js"), name="js")


@app.exception_handler(Exception)
async def on_error(request: Request, exc: Exception):
    # 프론트는 {message|error} 를 읽는다.
    log.exception("%s %s", request.method, request.url.path)
    return JSONResponse({"success": False, "message": str(exc)}, status_code=500)
