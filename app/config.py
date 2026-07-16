from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_service_key: str
    supabase_table: str

    # Google Sheets (Service Account)
    google_service_account_json: str
    google_sheet_id: str
    google_sheet_name: str = "LEAD TOTAL"

    # SendFlow
    sendflow_base_url: str = "https://sendflow.pro"
    sendflow_api_token: str
    sendflow_campaign_id: str

    # Calibração (admins que precisam ser descontados do total de grupos/leads)
    admin_offset: int = 0

    # Scheduler
    poll_interval_minutes: int = 2
    timezone: str = "America/Sao_Paulo"

    # Webhook
    webhook_path: str = "/webhook/sendflow"
    port: int = 8000


settings = Settings()
