"""
Activity service — append-only ledger of all inventory events.

All services call log_activity() after committing their domain changes.
The ledger never replaces domain tables — it references them.
"""

import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog

log = logging.getLogger(__name__)


async def log_activity(
    db: AsyncSession,
    *,
    activity_type: str,
    actor_id: Optional[int] = None,
    target_item_id: Optional[int] = None,
    target_bin_id: Optional[int] = None,
    target_cabinet_id: Optional[int] = None,
    target_user_id: Optional[int] = None,
    quantity_delta: Optional[int] = None,
    cost_impact: Optional[float] = None,
    notes: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    source_type: Optional[str] = None,
    source_id: Optional[int] = None,
) -> ActivityLog:
    """
    Append one activity record. Must be called inside an open transaction;
    caller is responsible for committing.
    """
    entry = ActivityLog(
        activity_type=activity_type,
        actor_id=actor_id,
        target_item_id=target_item_id,
        target_bin_id=target_bin_id,
        target_cabinet_id=target_cabinet_id,
        target_user_id=target_user_id,
        quantity_delta=quantity_delta,
        cost_impact=cost_impact,
        notes=notes,
        metadata_=metadata,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(entry)
    await db.flush()
    log.debug("ActivityLog: %s actor=%s item=%s", activity_type, actor_id, target_item_id)
    return entry
