"""Создание SQLAlchemy engine и асинхронных сессий PostgreSQL."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.models import Base


class Database:
    def __init__(self, settings: Settings) -> None:
        # ``self`` — явная ссылка на объект, похожая на this в C++ и Self в Delphi.
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        # Фабрика создаёт отдельную session/транзакцию для каждой операции.
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_schema(self) -> None:
        # ``async with`` — асинхронный RAII/context manager. Ресурс освободится
        # автоматически, как объект на стеке с деструктором в C++.
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def session(self) -> AsyncIterator[AsyncSession]:
        # Наличие yield делает функцию генератором. Здесь это заготовка
        # асинхронного генератора, способного выдавать сессию вызывающему коду.
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
