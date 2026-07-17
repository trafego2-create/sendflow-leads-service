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

    # Números de telefone de admin/staff (separados por vírgula) — eventos de
    # membro adicionado/removido vindos desses números são ignorados. Identificados
    # analisando o histórico real: aparecem em dezenas/centenas de grupos diferentes,
    # ao contrário de um lead real (que só passa por 1 grupo).
    admin_numbers: str = ""

    @property
    def admin_numbers_set(self) -> set[str]:
        return {n.strip() for n in self.admin_numbers.split(",") if n.strip()}

    # Scheduler
    timezone: str = "America/Sao_Paulo"

    # Webhook
    webhook_path: str = "/webhook/sendflow"
    port: int = 8000


settings = Settings()
