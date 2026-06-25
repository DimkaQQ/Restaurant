import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OnboardingModule(Base):
    __tablename__ = "onboarding_modules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    network_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("networks.id"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    pass_threshold: Mapped[int] = mapped_column(Integer, default=70)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    questions: Mapped[list["OnboardingQuestion"]] = relationship(
        "OnboardingQuestion", back_populates="module",
        cascade="all, delete-orphan",
        order_by="OnboardingQuestion.order_index",
    )
    progress: Mapped[list["OnboardingProgress"]] = relationship(
        "OnboardingProgress", back_populates="module", cascade="all, delete-orphan",
    )

    @property
    def embed_url(self) -> str | None:
        """Convert any YouTube URL to embed format."""
        if not self.video_url:
            return None
        url = self.video_url.strip()
        vid = None
        if "youtu.be/" in url:
            vid = url.split("youtu.be/")[1].split("?")[0]
        elif "youtube.com/watch" in url:
            for part in url.split("?")[1].split("&"):
                if part.startswith("v="):
                    vid = part[2:]
                    break
        elif "youtube.com/embed/" in url:
            return url
        return f"https://www.youtube.com/embed/{vid}" if vid else url


class OnboardingQuestion(Base):
    __tablename__ = "onboarding_questions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("onboarding_modules.id"))
    question: Mapped[str] = mapped_column(Text)
    option_a: Mapped[str] = mapped_column(String(500))
    option_b: Mapped[str] = mapped_column(String(500))
    option_c: Mapped[str | None] = mapped_column(String(500), nullable=True)
    option_d: Mapped[str | None] = mapped_column(String(500), nullable=True)
    correct_option: Mapped[str] = mapped_column(String(1))  # 'a', 'b', 'c', 'd'
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    module: Mapped["OnboardingModule"] = relationship("OnboardingModule", back_populates="questions")


class OnboardingProgress(Base):
    __tablename__ = "onboarding_progress"
    __table_args__ = (UniqueConstraint("staff_id", "module_id", name="uq_onboarding_progress"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    staff_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("staff.id"))
    module_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("onboarding_modules.id"))
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    module: Mapped["OnboardingModule"] = relationship("OnboardingModule", back_populates="progress")
