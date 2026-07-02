import uuid
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class AdminAuditLog(Base):
    """Record of every platform-admin action (subscription overrides,
    impersonation) — the audit trail the earlier launch-readiness review
    flagged as missing beyond a bare log line."""
    __tablename__ = "admin_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    admin_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(50))  # subscription_update, impersonate
    network_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("networks.id"), nullable=True, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
