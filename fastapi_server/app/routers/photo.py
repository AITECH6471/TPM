"""사진 → Google Drive 업로드 (n8n Drive_upload + share 노드와 같은 동작: 폴더에 저장 후 '링크가 있는 모든 사용자 읽기')."""
import io

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..config import settings

r = APIRouter(tags=["photo"])


def _upload(file: UploadFile, folder_id: str) -> dict:
    if not settings.google_token_file or not folder_id:
        raise HTTPException(501, "Google Drive 인증이 설정되지 않았습니다 (.env의 GOOGLE_TOKEN_FILE, DRIVE_FOLDER_*)")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload

    drive = build("drive", "v3", credentials=Credentials.from_authorized_user_file(settings.google_token_file),
                  cache_discovery=False)
    media = MediaIoBaseUpload(io.BytesIO(file.file.read()), mimetype=file.content_type or "application/octet-stream")
    meta = drive.files().create(body={"name": file.filename, "parents": [folder_id]}, media_body=media,
                                fields="id,name,webViewLink,mimeType").execute()
    drive.permissions().create(fileId=meta["id"], body={"role": "reader", "type": "anyone"}).execute()
    return {"success": True, "data": [meta], "url": meta.get("webViewLink", ""),
            "direct_url": f"https://drive.google.com/thumbnail?id={meta['id']}&sz=w800"}


@r.post("/photo/upload")
def photo_upload(photo: UploadFile = File(...)):
    return _upload(photo, settings.drive_folder_equip)


@r.post("/photo/upload-parts")
def photo_upload_parts(photo: UploadFile = File(...)):
    return _upload(photo, settings.drive_folder_parts)


@r.post("/photo/upload-sub")
def photo_upload_sub(photo: UploadFile = File(...)):
    return _upload(photo, settings.drive_folder_sub)
