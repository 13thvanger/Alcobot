from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100))
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    entries: Mapped[list["AlcoholEntry"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class AlcoholEntry(Base):
    __tablename__ = "alcohol_entries"
    __table_args__ = (
        UniqueConstraint("source_chat_id", "source_message_id", name="uq_entry_source_message"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_user_id", ondelete="CASCADE"), index=True
    )
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    source_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    original_text: Mapped[str] = mapped_column(Text)
    pure_alcohol_ml: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    consumed_on: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    llm_model: Mapped[str] = mapped_column(String(100))
    llm_result: Mapped[dict] = mapped_column(JSONB)

    user: Mapped[User] = relationship(back_populates="entries")


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
