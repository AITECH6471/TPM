"""사진 업로드용 Google Drive 토큰을 한 번 발급한다. 브라우저가 있는 PC에서 실행.

1) Google Cloud Console → API 및 서비스 → 사용자 인증 정보 → OAuth 클라이언트 ID(데스크톱 앱)를 만들고
   JSON을 이 폴더에 client_secret.json 으로 저장 (같은 프로젝트에서 Google Drive API 사용 설정)
2) pip install -r requirements.txt && python get_drive_token.py
3) 로그인 창에서 사진 폴더에 쓰기 권한이 있는 계정으로 허용 → secrets/token.json 생성

OAuth 동의 화면이 '테스트' 상태면 토큰이 7일 뒤 만료되므로 '프로덕션'으로 게시해 둔다.
client_secret.json, secrets/ 는 커밋 금지(.gitignore에 포함).
"""
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

here = Path(__file__).resolve().parent
flow = InstalledAppFlow.from_client_secrets_file(here / "client_secret.json",
                                                 ["https://www.googleapis.com/auth/drive"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
out = here / "secrets" / "token.json"
out.parent.mkdir(exist_ok=True)
out.write_text(creds.to_json(), encoding="utf-8")
print("saved:", out)
