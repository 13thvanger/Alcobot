from datetime import date
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlcoholEntry, User
from app.statistics import EntryValue


async def get_user(session: AsyncSession, telegram_user_id: int) -> User | None:
    return await session.get(User, telegram_user_id)


async def set_user_name(
    session: AsyncSession,
    telegram_user_id: int,
    display_name: str,
    telegram_username: str | None,
) -> User:
    user = await get_user(session, telegram_user_id)
    if user is None:
        user = User(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            telegram_username=telegram_username,
        )
        session.add(user)
    else:
        user.display_name = display_name
        user.telegram_username = telegram_username
    await session.commit()
    return user


async def ensure_user(
    session: AsyncSession,
    telegram_user_id: int,
    fallback_name: str,
    telegram_username: str | None,
) -> User:
    user = await get_user(session, telegram_user_id)
    if user is None:
        user = User(
            telegram_user_id=telegram_user_id,
            display_name=fallback_name,
            telegram_username=telegram_username,
        )
        session.add(user)
        await session.commit()
    elif user.telegram_username != telegram_username:
        user.telegram_username = telegram_username
        await session.commit()
    return user


async def add_entry(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    source_chat_id: int,
    source_message_id: int,
    original_text: str,
    pure_alcohol_ml: Decimal,
    consumed_on: date,
    llm_model: str,
    llm_result: dict,
) -> AlcoholEntry:
    entry = AlcoholEntry(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        original_text=original_text,
        pure_alcohol_ml=pure_alcohol_ml,
        consumed_on=consumed_on,
        llm_model=llm_model,
        llm_result=llm_result,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


async def list_entry_values(session: AsyncSession, telegram_user_id: int) -> list[EntryValue]:
    rows = await session.execute(
        select(AlcoholEntry.consumed_on, AlcoholEntry.pure_alcohol_ml)
        .where(AlcoholEntry.telegram_user_id == telegram_user_id)
        .order_by(AlcoholEntry.consumed_on)
    )
    return [EntryValue(consumed_on=row[0], amount=row[1]) for row in rows]


async def latest_entries(
    session: AsyncSession, telegram_user_id: int, limit: int = 10
) -> list[AlcoholEntry]:
    rows = await session.scalars(
        select(AlcoholEntry)
        .where(AlcoholEntry.telegram_user_id == telegram_user_id)
        .order_by(AlcoholEntry.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def get_owned_entry(
    session: AsyncSession, telegram_user_id: int, entry_id: int
) -> AlcoholEntry | None:
    return await session.scalar(
        select(AlcoholEntry).where(
            AlcoholEntry.id == entry_id,
            AlcoholEntry.telegram_user_id == telegram_user_id,
        )
    )


async def update_entry(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    entry_id: int,
    original_text: str,
    pure_alcohol_ml: Decimal,
    llm_model: str,
    llm_result: dict,
) -> AlcoholEntry | None:
    entry = await get_owned_entry(session, telegram_user_id, entry_id)
    if entry is None:
        return None
    entry.original_text = original_text
    entry.pure_alcohol_ml = pure_alcohol_ml
    entry.llm_model = llm_model
    entry.llm_result = llm_result
    await session.commit()
    await session.refresh(entry)
    return entry


async def delete_entry(
    session: AsyncSession, telegram_user_id: int, entry_id: int
) -> AlcoholEntry | None:
    entry = await get_owned_entry(session, telegram_user_id, entry_id)
    if entry is None:
        return None
    await session.delete(entry)
    await session.commit()
    return entry


async def admin_delete_entry(session: AsyncSession, entry_id: int) -> AlcoholEntry | None:
    entry = await session.get(AlcoholEntry, entry_id)
    if entry is None:
        return None
    await session.delete(entry)
    await session.commit()
    return entry


async def reset_user_entries(session: AsyncSession, telegram_user_id: int) -> int:
    result = await session.execute(
        delete(AlcoholEntry).where(AlcoholEntry.telegram_user_id == telegram_user_id)
    )
    await session.commit()
    return result.rowcount or 0


async def undo_latest(session: AsyncSession, telegram_user_id: int) -> AlcoholEntry | None:
    entry = await session.scalar(
        select(AlcoholEntry)
        .where(AlcoholEntry.telegram_user_id == telegram_user_id)
        .order_by(AlcoholEntry.created_at.desc())
        .limit(1)
    )
    if entry is None:
        return None
    await session.execute(delete(AlcoholEntry).where(AlcoholEntry.id == entry.id))
    await session.commit()
    return entry
