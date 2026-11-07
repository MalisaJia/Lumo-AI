"""Computer Use audit logging."""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import desc, select

from app.core.db import async_session_factory


async def log_action(
    conversation_id: str,
    action: str,
    parameters: dict,
    screenshot_hash: str | None,
    confirmation_status: str,
    result_summary: str,
    duration_ms: int,
) -> None:
    """Log a computer use action to the audit table."""
    from app.models import ComputerUseAudit

    async with async_session_factory() as session:
        entry = ComputerUseAudit(
            conversation_id=conversation_id,
            timestamp=datetime.now(timezone.utc),
            action=action,
            parameters_json=json.dumps(parameters, ensure_ascii=False),
            screenshot_hash=screenshot_hash,
            confirmation_status=confirmation_status,
            result_summary=result_summary[:500],
            duration_ms=duration_ms,
        )
        session.add(entry)
        await session.commit()


async def get_audit_log(
    conversation_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Query audit log entries."""
    from app.models import ComputerUseAudit

    async with async_session_factory() as session:
        query = select(ComputerUseAudit).order_by(desc(ComputerUseAudit.timestamp))
        if conversation_id:
            query = query.where(ComputerUseAudit.conversation_id == conversation_id)
        query = query.limit(limit).offset(offset)
        result = await session.execute(query)
        return result.scalars().all()


def compute_screenshot_hash(image_bytes: bytes) -> str:
    """Compute a truncated SHA-256 hash of a screenshot for the audit trail."""
    return hashlib.sha256(image_bytes).hexdigest()[:16]
