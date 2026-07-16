import httpx

from app.config import settings


async def get_analytics() -> dict:
    url = f"{settings.sendflow_base_url}/sendapi/releases/{settings.sendflow_campaign_id}/analytics"
    headers = {
        "accept": "application/json",
        "referrer": settings.sendflow_base_url + "/",
        "Authorization": f"Bearer {settings.sendflow_api_token}",
        "accept-language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        # a API retorna uma lista com um único objeto: [{"add": ..., "remove": ..., "clicks": ...}]
        if isinstance(data, list):
            data = data[0] if data else {}
        return data
