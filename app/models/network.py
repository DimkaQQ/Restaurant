import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Network(Base):
    __tablename__ = "networks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    venues: Mapped[list["Venue"]] = relationship("Venue", back_populates="network")
    users: Mapped[list["User"]] = relationship("User", back_populates="network")
    guests: Mapped[list["Guest"]] = relationship("Guest", back_populates="network")
