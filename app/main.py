import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request

from app import logic
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.timezone)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        logic.daily_append,
        CronTrigger(hour=0, minute=0, timezone=settings.timezone),
        id="daily_append",
    )
    scheduler.start()
    logger.info("scheduler iniciado: append diário 00:00 (%s)", settings.timezone)
    yield
    scheduler.shutdown()


app = FastAPI(title="SendFlow Leads Service", lifespan=lifespan)

EVENT_HANDLERS = {
    "group.updated.members.added": logic.handle_member_added,
    "group.updated.members.removed": logic.handle_member_removed,
    "campaign.metrics": logic.handle_campaign_metrics,
}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post(settings.webhook_path)
async def webhook_sendflow(request: Request):
    body = await request.json()
    event = body.get("event")
    data = body.get("data", {})

    handler = EVENT_HANDLERS.get(event)
    if handler is None:
        logger.info("evento ignorado: %s", event)
        return {"status": "ignored", "event": event}

    await handler(data)
    return {"status": "ok", "event": event}
