"""
Protected HTTP endpoints for externally triggering scheduled jobs.

Used by GitHub Actions cron workflows so Sunday checklist jobs fire even when
the Render Free dyno has been sleeping (APScheduler backup still runs if awake).

Auth: Authorization: Bearer <CRON_SECRET>
"""
import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.bot.checklist_helpers import (
    run_sunday_evening_all_groups,
    run_sunday_morning_all_groups,
)
from app.config import settings

log = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/jobs", tags=["internal"])


def _require_cron_secret(request: Request) -> None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Authorization header")
    token = auth.removeprefix("Bearer ")
    if not settings.cron_secret or not secrets.compare_digest(token, settings.cron_secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid CRON_SECRET")


def _build_response(
    job: str,
    results: dict[str, str],
    dm_warnings: dict[str, list[str]] | None = None,
) -> JSONResponse | dict:
    skipped = bool(results) and all(v == "skipped" for v in results.values())
    failed_groups = [g for g, v in results.items() if v == "error"]
    base: dict = {"job": job, "skipped": skipped, "results": results}
    if dm_warnings:
        base["dm_warnings"] = dm_warnings
    if failed_groups:
        return JSONResponse(
            status_code=502,
            content={**base, "skipped": False, "failed_groups": failed_groups},
        )
    return base


@router.post("/sunday-checklist-morning")
async def trigger_sunday_morning(request: Request):
    _require_cron_secret(request)
    log.info("internal job: sunday-checklist-morning triggered via HTTP")
    results = await run_sunday_morning_all_groups()
    return _build_response("sunday-checklist-morning", results)


@router.post("/sunday-checklist-evening")
async def trigger_sunday_evening(request: Request):
    _require_cron_secret(request)
    log.info("internal job: sunday-checklist-evening triggered via HTTP")
    results, dm_warnings = await run_sunday_evening_all_groups()
    return _build_response("sunday-checklist-evening", results, dm_warnings)
