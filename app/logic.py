import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app import sheets_client, supabase_client

logger = logging.getLogger(__name__)


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def today_str() -> str:
    return datetime.now(_tz()).strftime("%d/%m/%Y")


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
    total_leads_limpo = supabase_client.count_unique_leads()
    # A célula TOTAL LEADS da planilha é o valor "bruto" que alimenta a fórmula
    # TOTAL LIMPO = TOTAL LEADS - QTD. de ADMs (já cadastrada na planilha), por
    # isso somamos o admin_offset de volta ao total limpo antes de escrever.
    sheets_client.update_summary_row(
        {
            "TOTAL GRUPOS CHEIOS": data.get("groupsFullAmount"),
            "TOTAL LEADS": total_leads_limpo + settings.admin_offset,
        }
    )
    # Atualiza a linha do dia atual na tabela DATA/LEADS NO DIA a cada push de
    # métricas; a linha fica congelada com o valor final assim que o daily_append
    # cria a linha do próximo dia à meia-noite.
    sheets_client.upsert_row("DATA", today_str(), {"LEADS NO DIA": total_leads_limpo})


async def daily_append() -> None:
    hoje = today_str()
    sheets_client.append_row({"DATA2": hoje, "DATA": hoje})
