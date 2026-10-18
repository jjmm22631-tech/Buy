import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from config import Config
from database import Database
from handlers.common import is_series_bot
from keyboards import main_menu, subscription_keyboard

router = Router(name="start")
logger = logging.getLogger(__name__)

DEFAULT_WELCOME = "Assalomu alaykum! 👋\nUzbek Kinolar Olami botiga xush kelibsiz! 🎬\n\nSevimli kinolaringizni topish uchun kino kodini yuboring."
DEFAULT_SUBSCRIPTION = "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling."


async def register_user(message: Message, db: Database) -> None:
    user = message.from_user
    await db.execute(
        "INSERT INTO users(telegram_id, full_name, username) VALUES(?, ?, ?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name, username=excluded.username, last_active_at=CURRENT_TIMESTAMP",
        (user.id, user.full_name[:255], user.username),
    )


async def subscription_status(bot: Bot, db: Database, user_id: int) -> tuple[bool, list[dict]]:
    enabled = await db.get_setting("subscription_enabled", "1") == "1"
    channels = [dict(row) for row in await db.fetchall("SELECT * FROM channels WHERE is_active=1 ORDER BY id")]
    if not enabled or not channels:
        return True, channels
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel["channel_id"], user_id)
            if member.status in {"left", "kicked"} or (member.status == "restricted" and not member.is_member):
                return False, channels
        except (TelegramBadRequest, TelegramForbiddenError) as error:
            logger.warning("Kanal a’zoligini tekshirib bo‘lmadi: channel_id=%s error=%s", channel["channel_id"], type(error).__name__)
            return False, channels
    return True, channels


async def show_subscription_gate(message: Message, channels: list[dict], db: Database) -> None:
    text = await db.get_setting("subscription_text", DEFAULT_SUBSCRIPTION)
    await message.answer(text, reply_markup=subscription_keyboard(channels))


@router.message(CommandStart())
async def start_handler(message: Message, bot: Bot, db: Database, config: Config) -> None:
    await register_user(message, db)
    user = message.from_user
    row = await db.fetchone("SELECT is_blocked FROM users WHERE telegram_id=?", (user.id,))
    if row and row["is_blocked"]:
        await message.answer("🚫 Botdan foydalanishingiz cheklangan. Admin bilan bog‘laning.")
        return
    allowed, channels = await subscription_status(bot, db, user.id)
    if not allowed:
        await show_subscription_gate(message, channels, db)
        return
    welcome = await db.get_setting("welcome_text", DEFAULT_WELCOME)
    await message.answer(
        welcome,
        reply_markup=main_menu(
            user.id in config.admin_ids,
            await db.get_setting("payments_enabled", "0") == "1",
            hide_keyboard=is_series_bot(bot, config),
        ),
    )


@router.callback_query(F.data == "subscription:check")
async def subscription_check(callback: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    allowed, channels = await subscription_status(bot, db, callback.from_user.id)
    if allowed:
        await callback.answer("Obuna tasdiqlandi!")
        await callback.message.answer(
            await db.get_setting("welcome_text", DEFAULT_WELCOME),
            reply_markup=main_menu(
                callback.from_user.id in config.admin_ids,
                await db.get_setting("payments_enabled", "0") == "1",
                hide_keyboard=is_series_bot(bot, config),
            ),
        )
    else:
        await callback.answer("Hali barcha kanallarga obuna bo‘lmagansiz.", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=subscription_keyboard(channels))


@router.callback_query(F.data == "noop")
async def ignore_noop(callback: CallbackQuery) -> None:
    await callback.answer()