"""Telegram-команды и callback-обработчики.

Этот файл полезно читать после main.py и repository.py: здесь виден полный путь
данных от сообщения пользователя до LLM/БД и обратно в Telegram.
"""

import logging
from datetime import datetime
from decimal import Decimal
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db import Database
from app.drinks import DRINK_KEYS, DRINKS, calculate_short_add
from app.llm import AlcoholLLMClient, LLMError
from app.phrases import random_phrase
from app.repository import (
    admin_delete_entry,
    cancel_pending_entry,
    confirm_pending_entry,
    create_pending_entry,
    delete_entry,
    ensure_user,
    latest_entries,
    list_entry_values,
    reset_user_entries,
    set_user_name,
    undo_latest,
    update_entry,
)
from app.runtime_settings import (
    SETTING_DESCRIPTIONS,
    delete_setting,
    get_all_settings,
    get_runtime_config,
    set_setting,
    validate_setting,
)
from app.statistics import calculate_statistics

logger = logging.getLogger(__name__)
router = Router()

MONTHS = (
    "",
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)

HELP_TEXT = """
🍷 <b>Команды Alcobot</b>

<b>/add</b> — добавить выпитое сегодня.

Короткий формат по таблице напитков:
<code>/add beer 500</code> — 500 мл пива
<code>/add beer 500 4%</code> — 500 мл пива крепостью 4%
<code>/add wine 12%</code> — стандартная порция вина крепостью 12%
<code>/add beer 24 мая 4% 500</code> — параметры могут идти в любом порядке
<code>/add wine</code> — стандартные 150 мл вина
<code>/add tequila 100</code> — 100 мл текилы
<code>/add 30</code> — 30 мл чистого спирта

Можно использовать русские названия: пиво, сидр, вино, шампанское, вермут, водка,
виски, ром, джин, текила, коньяк, ликёр, абсент.

Свободное описание рассчитывается через ИИ:
<code>/add две бутылки пива по 0.5 л и 50 мл виски</code>
<code>/add выпил пузырь водки 24 мая</code>
<code>/add бутылка красного вина 12%</code>

Если объём не указан, стандартная порция составляет 500 мл для пива и сидра,
150 мл для вина и похожих напитков, 50 мл для крепкого алкоголя.
«Пузырь» считается бутылкой; дата из текста используется как дата записи.
Перед сохранением бот покажет распознанные напитки и попросит подтвердить добавление.

<b>/stat</b> — статистика за текущий год по всем чатам.
<code>/stat</code>

Показывает общую сумму, средние показатели, самый алкогольный месяц и день,
а также текущий и самый длинный стрики.

<b>/history</b> — последние 10 записей с их ID.
<code>/history</code>

<b>/edit ID описание</b> — исправить запись и заново рассчитать её.
<code>/edit 42 wine 300</code>
<code>/edit 42 два бокала красного вина</code>

<b>/delete ID</b> — удалить выбранную запись.
<code>/delete 42</code>

<b>/undo</b> — удалить свою последнюю запись.
<code>/undo</code>

<b>/username Имя</b> — изменить отображаемое имя.
<code>/username Илья</code>

<b>/help</b> — показать эту справку.

Расчёты являются приблизительными и не заменяют медицинскую консультацию.
""".strip()

ADMIN_HELP_TEXT = """
🛠 <b>Администрирование Alcobot</b>

<code>/admin</code> — эта справка
<code>/admin_config</code> — текущие изменённые настройки
<code>/admin_set timezone Europe/Moscow</code>
<code>/admin_set llm_temperature 0</code>
<code>/admin_set llm_max_tokens 4000</code>
<code>/admin_set drink.beer.abv 5</code>
<code>/admin_set drink.beer.volume 500</code>
<code>/admin_unset drink.beer.abv</code> — вернуть значение по умолчанию

Настройки напитков имеют вид <code>drink.КЛЮЧ.abv</code> и
<code>drink.КЛЮЧ.volume</code>.

<code>/admin_reset_user TELEGRAM_ID</code> — удалить всю статистику пользователя
<code>/admin_delete_entry ID</code> — удалить любую запись

Изменения сохраняются в PostgreSQL и применяются без перезапуска.
""".strip()


def command_argument(message: Message) -> str:
    # ``or`` здесь заменяет возможный None на пустую строку.
    text = message.text or ""
    # partition всегда возвращает tuple: (до разделителя, разделитель, после).
    return text.partition(" ")[2].strip()


def ml(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.1'))} мл"


def confirmation_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Добавить",
                    callback_data=f"add_confirm:{token}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"add_cancel:{token}",
                ),
            ]
        ]
    )


def format_calculation_items(result: dict, original_text: str) -> str:
    items = result.get("items")
    if not isinstance(items, list) or not items:
        return f"• {escape(original_text)}"

    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = escape(str(item.get("name") or "напиток"))
        volume = item.get("volume_ml")
        abv = item.get("abv_percent")
        item_alcohol = item.get("pure_alcohol_ml")
        details: list[str] = []
        if volume is not None:
            details.append(f"{escape(str(volume))} мл")
        if abv is not None:
            details.append(f"{escape(str(abv))}%")
        # join объединяет строки без ручной обработки последней запятой.
        suffix = f" ({', '.join(details)})" if details else ""
        alcohol = (
            f" → {escape(str(item_alcohol))} мл спирта"
            if item_alcohol is not None
            else ""
        )
        lines.append(f"• <b>{name}</b>{suffix}{alcohol}")
    return "\n".join(lines) if lines else f"• {escape(original_text)}"


async def require_admin(message: Message, settings: Settings) -> bool:
    if message.from_user is not None and message.from_user.id in settings.admin_ids:
        return True
    await message.answer("Эта команда доступна только администратору.")
    return False


async def ensure_message_user(message: Message, db: Database):
    if message.from_user is None:
        return None
    # Short-circuit: full_name используется только если username пуст.
    fallback_name = message.from_user.username or message.from_user.full_name
    async with db.session_factory() as session:
        user = await ensure_user(
            session,
            message.from_user.id,
            fallback_name,
            message.from_user.username,
        )
    return user


# Декоратор регистрирует функцию в Router. Aiogram вызовет её только для
# сообщений, которые прошли фильтр CommandStart.
@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Я считаю выпитый чистый алкоголь и объединяю статистику из всех чатов.\n\n"
        "Используйте <code>/add beer 500</code> или опишите выпитое свободным текстом.\n"
        "Полный список команд и примеры: /help"
    )


@router.message(Command("help"))
async def help_handler(message: Message, settings: Settings) -> None:
    text = HELP_TEXT
    if message.from_user is not None and message.from_user.id in settings.admin_ids:
        text += "\n\n" + ADMIN_HELP_TEXT
    await message.answer(text)


@router.message(Command("username"))
async def username_handler(message: Message, db: Database) -> None:
    # db внедряется aiogram по имени параметра из start_polling(..., db=db).
    if message.from_user is None:
        return
    name = command_argument(message)
    if not name:
        await message.answer("Использование: <code>/username Ваше имя</code>")
        return
    if len(name) > 100:
        await message.answer("Имя не должно быть длиннее 100 символов.")
        return
    async with db.session_factory() as session:
        await set_user_name(session, message.from_user.id, name, message.from_user.username)
    await message.answer(f"Имя сохранено: <b>{escape(name)}</b>")


@router.message(Command("add"))
async def add_handler(
    message: Message,
    db: Database,
    llm: AlcoholLLMClient,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return
    user = await ensure_message_user(message, db)
    if user is None:
        return
    description = command_argument(message)
    if not description:
        await message.answer(
            "Укажите напиток и объём или опишите выпитое, например:\n"
            "<code>/add beer 500</code>\n"
            "<code>/add beer 500 4%</code>\n"
            "<code>/add beer 24 мая 4% 500</code>\n"
            "<code>/add wine</code>\n"
            "<code>/add 30</code> — 30 мл чистого спирта\n"
            "<code>/add 2 бутылки пива и 50 мл виски</code>"
        )
        return
    if len(description) > 2000:
        await message.answer("Описание слишком длинное. Максимум — 2000 символов.")
        return

    waiting = await message.answer("Считаю количество чистого алкоголя…")
    try:
        async with db.session_factory() as session:
            runtime = await get_runtime_config(session, settings)
        today = datetime.now(runtime.timezone).date()
        short_calculation = calculate_short_add(
            description,
            runtime.drink_overrides,
            current_date=today,
        )
        if short_calculation is None:
            # None здесь — сигнал "локальный парсер не понял ввод", поэтому
            # используем более дорогой fallback через LLM.
            estimate = await llm.estimate(
                description,
                current_date=today,
                temperature=runtime.llm_temperature,
                max_tokens=runtime.llm_max_tokens,
            )
            amount = estimate.pure_alcohol_ml
            result = estimate.raw
            summary = estimate.summary
            consumed_on = estimate.consumed_on
            calculation_model = llm.model
        else:
            amount = short_calculation.pure_alcohol_ml
            result = short_calculation.as_result()
            summary = short_calculation.summary
            consumed_on = short_calculation.consumed_on or today
            calculation_model = "built-in-drink-table/v1"
        async with db.session_factory() as session:
            pending = await create_pending_entry(
                session,
                telegram_user_id=message.from_user.id,
                telegram_username=message.from_user.username,
                source_chat_id=message.chat.id,
                source_message_id=message.message_id,
                original_text=description,
                pure_alcohol_ml=amount,
                consumed_on=consumed_on,
                llm_model=calculation_model,
                llm_result=result,
            )
    except LLMError as exc:
        logger.warning("LLM request failed: %s", exc)
        await waiting.edit_text(
            "Не удалось рассчитать алкоголь. Попробуйте уточнить объёмы и крепость."
        )
        return
    except Exception:
        # Широкий Exception допустим на внешней границе: пользователю отдаём
        # безопасный текст, а полный traceback остаётся в логах.
        logger.exception("Failed to prepare alcohol entry")
        await waiting.edit_text("Не удалось подготовить запись. Попробуйте позже.")
        return

    items_text = format_calculation_items(result, description)
    details = f"\n\n<i>{escape(summary)}</i>" if summary else ""
    await waiting.edit_text(
        f"Ты выпил за <b>{consumed_on:%d.%m.%Y}</b>:\n\n"
        f"{items_text}\n\n"
        f"Итого: <b>{ml(amount)}</b> чистого спирта.{details}\n\n"
        "<b>Добавляю в статистику?</b>",
        reply_markup=confirmation_keyboard(pending.token),
    )


@router.callback_query(F.data.startswith("add_confirm:"))
async def confirm_add_handler(callback: CallbackQuery, db: Database) -> None:
    if callback.from_user is None or callback.data is None:
        return
    token = callback.data.partition(":")[2]
    try:
        async with db.session_factory() as session:
            # Tuple unpacking: два результата функции сразу попадают в переменные.
            status, entry = await confirm_pending_entry(
                session,
                token,
                callback.from_user.id,
            )
    except IntegrityError:
        await callback.answer("Эта команда уже была учтена.", show_alert=True)
        return
    except Exception:
        logger.exception("Failed to confirm alcohol entry")
        await callback.answer("Не удалось сохранить запись.", show_alert=True)
        return

    if status == "forbidden":
        await callback.answer("Подтвердить может только автор команды.", show_alert=True)
        return
    if status == "expired":
        await callback.answer("Подтверждение устарело. Выполните /add ещё раз.", show_alert=True)
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
        return
    if status == "missing" or entry is None:
        await callback.answer("Этот расчёт уже обработан или отменён.", show_alert=True)
        return

    phrase = random_phrase("add")
    phrase_text = f"\n\n💬 <i>{escape(phrase)}</i>" if phrase else ""
    # Для Optional это краткая форма ``if callback.message is not None``.
    if callback.message:
        await callback.message.edit_text(
            f"✅ Записано за {entry.consumed_on:%d.%m.%Y}: "
            f"<b>{ml(entry.pure_alcohol_ml)}</b> чистого спирта."
            f"{phrase_text}"
        )
    await callback.answer("Добавлено")


@router.callback_query(F.data.startswith("add_cancel:"))
async def cancel_add_handler(callback: CallbackQuery, db: Database) -> None:
    if callback.from_user is None or callback.data is None:
        return
    token = callback.data.partition(":")[2]
    async with db.session_factory() as session:
        cancelled = await cancel_pending_entry(session, token, callback.from_user.id)
    if not cancelled:
        await callback.answer(
            "Отменить может только автор, либо расчёт уже обработан.",
            show_alert=True,
        )
        return
    if callback.message:
        await callback.message.edit_text("❌ Добавление отменено. В статистику ничего не записано.")
    await callback.answer("Отменено")


@router.message(Command("stat"))
async def stat_handler(message: Message, db: Database, settings: Settings) -> None:
    if message.from_user is None:
        return
    user = await ensure_message_user(message, db)
    if user is None:
        return
    async with db.session_factory() as session:
        values = await list_entry_values(session, message.from_user.id)
    async with db.session_factory() as session:
        runtime = await get_runtime_config(session, settings)
    today = datetime.now(runtime.timezone).date()
    stat = calculate_statistics(values, today)
    if stat is None:
        await message.answer("Пока нет записей с алкоголем.")
        return

    year, month, month_amount = stat.strongest_month
    strongest_day, day_amount = stat.strongest_day
    phrase = random_phrase("stat")
    phrase_text = f"\n\n💡 <i>{escape(phrase)}</i>" if phrase else ""
    await message.answer(
        f"🍷 <b>Статистика за {today.year}: {escape(user.display_name)}</b>\n\n"
        f"Всего: <b>{ml(stat.total)}</b>\n"
        f"Записей: <b>{stat.entries_count}</b>\n"
        f"Дней с алкоголем: <b>{stat.drinking_days}</b>\n"
        f"Среднее в месяц: <b>{ml(stat.average_per_month)}</b>\n"
        f"Среднее в год (по текущему темпу): <b>{ml(stat.average_per_year)}</b>\n"
        f"Самый алкогольный месяц: <b>{MONTHS[month]} {year} — {ml(month_amount)}</b>\n"
        f"Самый алкогольный день: <b>{strongest_day:%d.%m.%Y} — {ml(day_amount)}</b>\n"
        f"Самый длинный стрик: <b>{stat.longest_streak} дн.</b>\n"
        f"Текущий стрик: <b>{stat.current_streak} дн.</b>"
        f"{phrase_text}"
    )


@router.message(Command("history"))
async def history_handler(message: Message, db: Database) -> None:
    if message.from_user is None or await ensure_message_user(message, db) is None:
        return
    async with db.session_factory() as session:
        entries = await latest_entries(session, message.from_user.id)
    if not entries:
        await message.answer("История пока пуста.")
        return
    # Comprehension удобен для преобразования каждого элемента без side effects.
    lines = [
        f"<code>#{entry.id}</code> · {entry.consumed_on:%d.%m.%Y} — "
        f"<b>{ml(entry.pure_alcohol_ml)}</b>: "
        f"{escape(entry.original_text[:120])}"
        for entry in entries
    ]
    await message.answer("<b>Последние записи</b>\n\n" + "\n".join(lines))


@router.message(Command("edit"))
async def edit_handler(
    message: Message,
    db: Database,
    llm: AlcoholLLMClient,
    settings: Settings,
) -> None:
    if message.from_user is None or await ensure_message_user(message, db) is None:
        return
    arguments = command_argument(message)
    entry_id_text, separator, description = arguments.partition(" ")
    if not separator or not entry_id_text.isdigit() or not description.strip():
        await message.answer(
            "Использование: <code>/edit ID новое описание выпитого</code>\n"
            "ID записи можно посмотреть через /history."
        )
        return
    description = description.strip()
    if len(description) > 2000:
        await message.answer("Описание слишком длинное. Максимум — 2000 символов.")
        return

    waiting = await message.answer("Пересчитываю запись…")
    try:
        async with db.session_factory() as session:
            runtime = await get_runtime_config(session, settings)
        today = datetime.now(runtime.timezone).date()
        short_calculation = calculate_short_add(
            description,
            runtime.drink_overrides,
            current_date=today,
        )
        if short_calculation is None:
            estimate = await llm.estimate(
                description,
                current_date=today,
                temperature=runtime.llm_temperature,
                max_tokens=runtime.llm_max_tokens,
            )
            amount = estimate.pure_alcohol_ml
            result = estimate.raw
            calculation_model = llm.model
        else:
            amount = short_calculation.pure_alcohol_ml
            result = short_calculation.as_result()
            calculation_model = "built-in-drink-table/v1"
        async with db.session_factory() as session:
            entry = await update_entry(
                session,
                telegram_user_id=message.from_user.id,
                entry_id=int(entry_id_text),
                original_text=description,
                pure_alcohol_ml=amount,
                llm_model=calculation_model,
                llm_result=result,
            )
    except LLMError as exc:
        logger.warning("LLM request failed while editing: %s", exc)
        await waiting.edit_text(
            "Не удалось пересчитать алкоголь. Попробуйте уточнить объёмы и крепость."
        )
        return
    except Exception:
        logger.exception("Failed to edit alcohol entry")
        await waiting.edit_text("Не удалось изменить запись. Попробуйте позже.")
        return

    if entry is None:
        await waiting.edit_text("Запись с таким ID не найдена среди ваших записей.")
        return
    await waiting.edit_text(
        f"Запись <code>#{entry.id}</code> обновлена: "
        f"<b>{ml(entry.pure_alcohol_ml)}</b> чистого алкоголя."
    )


@router.message(Command("delete"))
async def delete_handler(message: Message, db: Database) -> None:
    if message.from_user is None or await ensure_message_user(message, db) is None:
        return
    entry_id_text = command_argument(message)
    if not entry_id_text.isdigit():
        await message.answer(
            "Использование: <code>/delete ID</code>\n"
            "ID записи можно посмотреть через /history."
        )
        return
    async with db.session_factory() as session:
        entry = await delete_entry(session, message.from_user.id, int(entry_id_text))
    if entry is None:
        await message.answer("Запись с таким ID не найдена среди ваших записей.")
        return
    await message.answer(
        f"Запись <code>#{entry.id}</code> удалена: "
        f"{entry.consumed_on:%d.%m.%Y}, <b>{ml(entry.pure_alcohol_ml)}</b>."
    )


@router.message(Command("undo"))
async def undo_handler(message: Message, db: Database) -> None:
    if message.from_user is None or await ensure_message_user(message, db) is None:
        return
    async with db.session_factory() as session:
        entry = await undo_latest(session, message.from_user.id)
    if entry is None:
        await message.answer("Удалять нечего.")
        return
    await message.answer(
        f"Удалена последняя запись: {entry.consumed_on:%d.%m.%Y}, "
        f"<b>{ml(entry.pure_alcohol_ml)}</b>."
    )


@router.message(Command("admin"))
async def admin_handler(message: Message, settings: Settings) -> None:
    if await require_admin(message, settings):
        await message.answer(ADMIN_HELP_TEXT)


@router.message(Command("admin_config"))
async def admin_config_handler(
    message: Message, db: Database, settings: Settings
) -> None:
    if not await require_admin(message, settings):
        return
    async with db.session_factory() as session:
        values = await get_all_settings(session)
    defaults = {
        "timezone": settings.app_timezone,
        "llm_temperature": "0",
        "llm_max_tokens": "4000",
    }
    lines = ["🛠 <b>Runtime-настройки</b>"]
    for key, default in defaults.items():
        value = values.get(key, default)
        marker = "изменено" if key in values else "по умолчанию"
        lines.append(f"<code>{key}</code> = <code>{escape(value)}</code> ({marker})")
    drink_values = sorted(
        (key, value) for key, value in values.items() if key.startswith("drink.")
    )
    if drink_values:
        lines.append("\n<b>Изменённые напитки</b>")
        lines.extend(
            f"<code>{escape(key)}</code> = <code>{escape(value)}</code>"
            for key, value in drink_values
        )
    lines.append("\nКлючи напитков: " + ", ".join(drink.key for drink in DRINKS))
    await message.answer("\n".join(lines))


@router.message(Command("admin_set"))
async def admin_set_handler(message: Message, db: Database, settings: Settings) -> None:
    if not await require_admin(message, settings):
        return
    key, separator, value = command_argument(message).partition(" ")
    if not separator:
        await message.answer(
            "Использование: <code>/admin_set ключ значение</code>\n"
            + "\n".join(
                f"<code>{name}</code> — {description}"
                for name, description in SETTING_DESCRIPTIONS.items()
            )
        )
        return
    try:
        normalized = validate_setting(key, value, DRINK_KEYS)
    except ValueError as exc:
        await message.answer(f"Настройка не сохранена: {escape(str(exc))}.")
        return
    async with db.session_factory() as session:
        await set_setting(session, key, normalized, message.from_user.id)
    await message.answer(
        f"Сохранено без перезапуска: <code>{escape(key)}</code> = "
        f"<code>{escape(normalized)}</code>."
    )


@router.message(Command("admin_unset"))
async def admin_unset_handler(
    message: Message, db: Database, settings: Settings
) -> None:
    if not await require_admin(message, settings):
        return
    key = command_argument(message)
    if not key:
        await message.answer("Использование: <code>/admin_unset ключ</code>")
        return
    async with db.session_factory() as session:
        removed = await delete_setting(session, key)
    if removed:
        await message.answer(
            f"Настройка <code>{escape(key)}</code> удалена; действует значение по умолчанию."
        )
    else:
        await message.answer("Изменённая настройка с таким ключом не найдена.")


@router.message(Command("admin_reset_user"))
async def admin_reset_user_handler(
    message: Message, db: Database, settings: Settings
) -> None:
    if not await require_admin(message, settings):
        return
    user_id_text = command_argument(message)
    if not user_id_text.isdigit():
        await message.answer("Использование: <code>/admin_reset_user TELEGRAM_ID</code>")
        return
    async with db.session_factory() as session:
        count = await reset_user_entries(session, int(user_id_text))
    await message.answer(
        f"Удалено записей пользователя <code>{user_id_text}</code>: <b>{count}</b>."
    )


@router.message(Command("admin_delete_entry"))
async def admin_delete_entry_handler(
    message: Message, db: Database, settings: Settings
) -> None:
    if not await require_admin(message, settings):
        return
    entry_id_text = command_argument(message)
    if not entry_id_text.isdigit():
        await message.answer("Использование: <code>/admin_delete_entry ID</code>")
        return
    async with db.session_factory() as session:
        entry = await admin_delete_entry(session, int(entry_id_text))
    if entry is None:
        await message.answer("Запись не найдена.")
        return
    await message.answer(
        f"Запись <code>#{entry.id}</code> пользователя "
        f"<code>{entry.telegram_user_id}</code> удалена."
    )


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="help", description="Все команды и примеры"),
            BotCommand(command="username", description="Задать отображаемое имя"),
            BotCommand(command="add", description="Добавить выпитое сегодня"),
            BotCommand(command="stat", description="Показать статистику"),
            BotCommand(command="history", description="Последние записи"),
            BotCommand(command="edit", description="Исправить запись по ID"),
            BotCommand(command="delete", description="Удалить запись по ID"),
            BotCommand(command="undo", description="Удалить последнюю запись"),
        ]
    )
