# AIT TPM API (FastAPI)

n8n TPM 워크플로우의 API 44개를 같은 경로·같은 응답 형태로 옮긴 서버입니다. 화면 파일(index.html, report.html 등)도 함께 제공합니다.

```
https://tpm.aitkorea.app        → 화면
https://tpm.aitkorea.app/api/…  → API → MySQL
```

추가 API 3개(설비 상세 이력 편집): `POST /report/history-add`, `/report/update`, `/report/delete`.
이 3개는 n8n TPM 워크플로우에 없습니다. 경로는 `/api`, `/webhook`, `/` 모두에서 동작합니다.

> n8n은 끄지 말고 옆에서 같이 돌립니다. 같은 DB를 쓰며, 문제가 생기면 주소만 되돌리면 됩니다.

## 확인 상태 (2026-11-25)
- 자동 테스트 19개 통과 (`python -m pytest tests -q`, DB 불필요)
- 조회(GET) API: 운영 DB를 읽기 전용으로 연결해 n8n 응답과 값 단위로 비교, 일치
  - 차이 1: 파라미터를 아예 빼고 호출하면 n8n은 0건, FastAPI는 전체 목록(빈 파라미터를 넣은 호출은 일치)
  - 입출고 이력은 DB에 데이터가 0건이라 실데이터 비교 불가
- 저장·수정·삭제 API: 코드 대조만 했고 **실제 DB 쓰기는 시험하지 않음**
- 푸시: n8n의 VAPID 키로 서명·암호화 되는 것까지 오프라인 확인, 실제 발송은 미시험
- 사진 업로드: Google Drive 토큰 설정 전에는 501 반환, 미시험

## 서버 PC(192.168.1.147) 설치

### 1. 코드 받기
```powershell
git clone https://github.com/AITECH6471/TPM.git C:\tpm
cd C:\tpm\fastapi_server
copy .env.example .env
mkdir secrets
```

### 2. `.env` 채우기 (커밋 금지)
| 항목 | 값 |
|---|---|
| `DB_PASSWORD` | MySQL 비밀번호 |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | n8n `CODE_send_push_report` 노드의 값 그대로 (그래야 같은 키로 발송) |
| `DRIVE_FOLDER_EQUIP`, `DRIVE_FOLDER_SUB` | n8n `Drive_upload`, `Drive_upload_photo_upload_sub` 노드의 folderId |
| `DRIVE_FOLDER_PARTS` | n8n `Drive_upload_photo_upload_parts` 노드의 folderId |

### 3. 사진 업로드 토큰
`get_drive_token.py` 파일 위쪽 설명대로 `secrets\token.json` 을 만듭니다.

### 4. 실행 (기본 포트 8200)
서버의 다른 서비스가 쓰지 않는 포트를 고릅니다. 8200이 사용 중이면 `.env` 의 `API_PORT` 만 바꾸고, 아래 명령과 터널 주소의 번호도 같이 바꿉니다.
```powershell
Get-NetTCPConnection -State Listen | Where-Object LocalPort -eq 8200   # 아무것도 안 나와야 함
docker compose up -d --build
curl.exe http://localhost:8200/api/health        # {"ok":true}
curl.exe http://localhost:8200/api/settings/get  # DB 연결 확인
```
컨테이너는 `host.docker.internal` 로 MySQL에 접속합니다. 접속이 거부되면 `docker-compose.yml` 의 `DB_HOST` 를 `192.168.1.147` 로 바꿉니다.

Docker 없이 실행:
```powershell
pip install -r requirements.txt
$env:GOOGLE_TOKEN_FILE="secrets\token.json"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8200
```

화면 업데이트는 `git pull` 로 반영됩니다. 서버 코드(`app/`)가 바뀌면 `docker compose up -d --build` 를 다시 실행합니다.

## 도메인 전환 (서버 확인이 끝난 뒤)
GitHub Pages는 `/api` 를 실행할 수 없으므로 `tpm.aitkorea.app` 을 서버의 Cloudflare Tunnel로 옮깁니다.

1. Cloudflare → `aitkorea.app` → DNS: `tpm` CNAME(→ aitech6471.github.io) 레코드 삭제
2. 바로 이어서 Zero Trust → Networks → Tunnels → `aitech-app` → Public Hostname 추가
   - `tpm.aitkorea.app` → `http://localhost:8200`
   - cloudflared가 컨테이너로 돌면 `localhost` 대신 `host.docker.internal` (기존 호스트 설정 방식을 따름)
3. `https://tpm.aitkorea.app/api/health` 확인. 이 시점의 화면은 아직 n8n API를 호출하므로 그대로 동작합니다.
4. API 주소 전환
   - `js/core.js` 의 `baseUrl`, `report.html` 의 `BASE`, `index.html` 설정 칸 기본값 → `https://tpm.aitkorea.app/api`
   - 브라우저에 저장된 예전 n8n 주소도 무시하도록 처리 (지금은 ngrok 주소만 무시)
   - DB `settings.base_url` 도 같은 값으로 변경 (코드 기본값보다 우선, 이전 사이트에도 적용됨)
5. n8n TPM 워크플로우는 며칠 지켜본 뒤 비활성화

되돌리기: 4번을 원래 주소로 돌리면 n8n을 다시 사용합니다.

## 보안
로그인(인증)이 없습니다. 주소를 아는 사람은 조회·수정·삭제 API를 호출할 수 있으므로 접속 제한을 검토해야 합니다.

## n8n과 달라진 점
- SQL을 `%s` 바인딩으로 실행합니다. 작은따옴표(`ASS'Y`) 오류와 SQL 삽입 문제가 없습니다.
- NULL은 `null` 로 내려갑니다(n8n은 문자열 `'undefined'`).
- 만료된 푸시 구독(404/410)은 자동 삭제합니다.
- `action/create` 는 n8n 동작 그대로입니다. `status_code` 없이 `status:'완료'` 만 보내면 설비 상태도 `'완료'` 가 됩니다.
