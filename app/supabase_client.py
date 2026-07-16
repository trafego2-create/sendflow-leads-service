from supabase import create_client, Client

from app.config import settings

_client: Client = create_client(settings.supabase_url, settings.supabase_service_key)
_table = settings.supabase_table


def get_lead(numero: str) -> dict | None:
    resp = _client.table(_table).select("*").eq("NÚMERO", numero).execute()
    rows = resp.data or []
    return rows[0] if rows else None


def insert_lead(fields: dict) -> dict:
    resp = _client.table(_table).insert(fields).execute()
    return resp.data[0] if resp.data else {}


def update_lead(numero: str, fields: dict) -> dict:
    resp = _client.table(_table).update(fields).eq("NÚMERO", numero).execute()
    return resp.data[0] if resp.data else {}


def get_leads_by_date(data1: str) -> list[dict]:
    resp = _client.table(_table).select("*").eq("DATA1", data1).execute()
    return resp.data or []


def count_unique_leads() -> int:
    """Fonte de verdade do total de leads: pessoas únicas (LEAD ÚNICO=1),
    já deduplicadas por número — diferente do total bruto de eventos da API do SendFlow."""
    resp = _client.table(_table).select("NÚMERO", count="exact").eq("LEAD ÚNICO", 1).execute()
    return resp.count or 0
