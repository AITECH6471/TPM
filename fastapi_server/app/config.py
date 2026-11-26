from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "equipment_db"

    cors_origins: str = "https://tpm.aitkorea.app,https://aitech6471.github.io,https://aitmt6471.github.io,http://localhost:5500,http://127.0.0.1:5500"

    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:admin@ait.com"
    push_url: str = "https://tpm.aitkorea.app/report.html"
    # 화면 파일 위치. 비우면 이 폴더의 상위(저장소 루트)
    static_dir: str = ""

    # 고장접수(report/create) 디스코드 알림. 비우면 알림만 건너뜀
    discord_breakdown_webhook_url: str = ""

    google_token_file: str = ""
    drive_folder_equip: str = ""
    drive_folder_parts: str = ""
    drive_folder_sub: str = ""


settings = Settings()
