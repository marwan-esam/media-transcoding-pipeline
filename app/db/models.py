from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, func, Float, Boolean, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
  pass


class User(Base):
  __tablename__ = "users"

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
  hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
  is_active: Mapped[bool] = mapped_column(Boolean, default=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

  videos: Mapped[list["Video"]] = relationship(back_populates="owner", cascade="all, delete-orphan")

class Video(Base):
  __tablename__ = "videos"

  id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
  title: Mapped[str] = mapped_column(String(255), nullable=False)
  filename: Mapped[str] = mapped_column(String(255), nullable=False)
  s3_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
  status: Mapped[str] = mapped_column(String(50), default="uploaded")
  duration: Mapped[float] = mapped_column(Float, nullable=True)
  created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

  user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

  owner: Mapped["User"] = relationship(back_populates="videos")