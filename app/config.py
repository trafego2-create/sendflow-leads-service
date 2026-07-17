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

    # Nome exato do grupo real de captação (os demais são reserva/staff e devem
    # ser ignorados nos eventos de membro adicionado/removido)
    campaign_group_name: str

    # Scheduler
    timezone: str = "America/Sao_Paulo"

    # Webhook
    webhook_path: str = "/webhook/sendflow"
    port: int = 8000


settings = Settings()
