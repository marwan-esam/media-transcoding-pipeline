from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
  pass

class Video(Base):
  __tablename__ = "videos"

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  filename: Mapped[str] = mapped_column(String(255), nullable=False)
  s3_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
  status: Mapped[str] = mapped_column(String(50), default="uploaded")
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())