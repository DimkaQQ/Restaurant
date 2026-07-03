"""Tenant-scoped staff audit trail. Call log_action inside the same
transaction as the action itself (no commit here — the caller commits),
so the audit entry and the action succeed or fail together."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import StaffAuditLog


def log_action(
    db: AsyncSession,
    network_id: uuid.UUID,
    user_email: str,
    action: str,
    detail: str = "",
) -> None:
    db.add(StaffAuditLog(
        id=uuid.uuid4(),
        network_id=network_id,
        user_email=user_email,
        action=action,
        detail=detail or None,
    ))
