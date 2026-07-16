import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app import sendflow_client, sheets_client, supabase_client

logger = logging.getLogger(__name__)


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def today_str() -> str:
    return datetime.now(_tz()).strftime("%d/%m/%Y")


def today_ddmmyyyy() -> str:
    return datetime.now(_tz()).strftime("%d%m%Y")


async def handle_member_added(data: dict) -> None:
    numero = data["number"]
    grupo = data.get("groupName", "")
    existing = supabase_client.get_lead(numero)
    if existing:
        novo_lead_numero = (existing.get("LEAD NÚMERO") or 0) + 1
        supabase_client.update_lead(numero, {"LEAD NÚMERO": novo_lead_numero, "LEAD ÚNICO": 1})
    else:
        supabase_client.insert_lead(
            {
                "DATA1": today_str(),
                "GRUPO DA CAMPANHA": grupo,
                "LEAD NÚMERO": 1,
                "LEAD ÚNICO": 1,
                "NÚMERO": numero,
            }
        )


async def handle_member_removed(data: dict) -> None:
    numero = data["number"]
    existing = supabase_client.get_lead(numero)
    if not existing:
        logger.warning("member removed mas não encontrei lead NÚMERO=%s", numero)
        return
    novo_lead_numero = (existing.get("LEAD NÚMERO") or 0) - 1
    lead_unico = 1 if novo_lead_numero > 0 else 0
    supabase_client.update_lead(
        numero, {"LEAD NÚMERO": novo_lead_numero, "LEAD ÚNICO": lead_unico}
    )


async def handle_campaign_metrics(data: dict) -> None:
    sheets_client.update_summary_row(
        {
            "TOTAL GRUPOS CHEIOS": data.get("groupsFullAmount"),
            "TOTAL LEADS": supabase_client.count_unique_leads(),
        }
    )


async def poll_analytics() -> None:
    try:
        analytics = await sendflow_client.get_analytics()
    except Exception:
        logger.exception("falha ao consultar analytics do SendFlow")
        return

    add_total = analytics.get("add", {}).get("total", 0)
    remove_total = analytics.get("remove", {}).get("total", 0)
    add_dates = analytics.get("add", {}).get("dates", {})
    remove_dates = analytics.get("remove", {}).get("dates", {})

    # TOTAL GRUPOS CHEIOS ainda vem da fórmula do SendFlow (eventos brutos / 900) -
    # não temos como saber grupo por grupo a partir do Supabase.
    total_grupos_cheios = round((add_total - settings.admin_offset - remove_total) / 900)

    # TOTAL LEADS vem do Supabase (contagem real de pessoas únicas, já deduplicada),
    # não do total bruto de eventos da API do SendFlow - alguém que sai e volta,
    # ou entra em mais de um grupo, gera múltiplos eventos mas continua sendo 1 lead.
    total_leads = supabase_client.count_unique_leads()

    sheets_client.update_summary_row(
        {
            "TOTAL GRUPOS CHEIOS": total_grupos_cheios,
            "TOTAL LEADS": total_leads,
        }
    )

    hoje = today_ddmmyyyy()
    sheets_client.upsert_row(
        "DATA",
        today_str(),
        {
            "ENTRADAS": add_dates.get(hoje, 0),
            "SAÍDAS": remove_dates.get(hoje, 0),
            "LEADS NO DIA": total_leads,
        },
    )


async def daily_append() -> None:
    hoje = today_str()
    sheets_client.append_row({"DATA2": hoje, "DATA": hoje})
