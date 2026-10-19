import logging

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatJoinRequest, Message
from aiogram.exceptions import TelegramAPIError

from config import Config
from database import Database
from handlers.common import is_second_bot, is_series_bot
from keyboards import empty_subscription_keyboard, main_menu, personal_menu, subscription_keyboard
from telegram_commands import set_admin_commands

router = Router(name="start")
logger = logging.getLogger(__name__)

DEFAULT_WELCOME = "Assalomu alaykum! 👋\nUzbek Kinolar Olami botiga xush kelibsiz! 🎬\n\nSevimli kinolaringizni topish uchun kino kodini yuboring."
DEFAULT_SERIES_WELCOME = (
    "Assalomu alaykum! 👋\n"
    "Uzbek Tarjima Serialar Olami botiga xush kelibsiz! 🎬\n\n"
    "Sevimli serialaringizni topish uchun serial kodini yuboring."
)
DEFAULT_SUBSCRIPTION = "👋 Botdan foydalanish uchun quyidagi kanal va guruhlarga obuna bo‘ling!"


async def register_user(message: Message, db: Database) -> None:
    user = message.from_user
    await db.execute(
        "INSERT INTO users(telegram_id, full_name, username) VALUES(?, ?, ?) "
        "ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name, username=excluded.username, last_active_at=CURRENT_TIMESTAMP",
        (user.id, user.full_name[:255], user.username),
    )


async def subscription_status(bot: Bot, db: Database, user_id: int) -> tuple[bool, list[dict]]:
    enabled = await db.get_bot_setting("subscription_enabled", bot.id, "1") == "1"
    channels = [
        dict(row)
        for row in await db.fetchall(
            "SELECT * FROM bot_channels WHERE bot_id=? AND is_active=1 ORDER BY id",
            (bot.id,),
        )
    ]
    if not enabled or not channels:
        return True, []
    missing = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(channel["channel_id"], user_id)
            if member.status in {"left", "kicked"} or (member.status == "restricted" and not member.is_member):
                missing.append(channel)
        except TelegramAPIError as error:
            logger.warning(
                "Kanal/guruh a’zoligini tekshirib bo‘lmadi: chat_id=%s error=%s",
                channel["channel_id"],
                type(error).__name__,
            )
            missing.append(channel)
    return not missing, missing


async def show_subscription_gate(message: Message, channels: list[dict], db: Database, bot_id: int) -> None:
    text = await db.get_bot_setting("subscription_text", bot_id, DEFAULT_SUBSCRIPTION)
    await message.answer(text, reply_markup=subscription_keyboard(channels))


def welcome_with_code_prompt(welcome: str, code_name: str = "kino") -> str:
    normalized = " ".join(welcome.casefold().split())
    if f"{code_name} kodini yuboring" in normalized:
        return welcome
    return f"{welcome.rstrip()}\n\n🎬 {code_name.capitalize()} kodini yuboring."


async def get_welcome(bot: Bot, db: Database, config: Config) -> str:
    if is_second_bot(bot, config):
        welcome = await db.get_setting("series_welcome_text", DEFAULT_SERIES_WELCOME)
        return welcome_with_code_prompt(welcome, "serial")
    else:
        welcome = await db.get_setting("welcome_text", DEFAULT_WELCOME)
    return welcome_with_code_prompt(welcome)


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext, bot: Bot, db: Database, config: Config) -> None:
    await state.clear()
    await register_user(message, db)
    user = message.from_user
    if user.id in config.admin_ids:
        await set_admin_commands(bot, user.id, is_series_bot(bot, config))
    row = await db.fetchone("SELECT is_blocked FROM users WHERE telegram_id=?", (user.id,))
    if row and row["is_blocked"]:
        await message.answer("🚫 Botdan foydalanishingiz cheklangan. Admin bilan bog‘laning.")
        return
    allowed, channels = await subscription_status(bot, db, user.id)
    if not allowed:
        await show_subscription_gate(message, channels, db, bot.id)
        return
    welcome = await get_welcome(bot, db, config)
    payments_enabled = await db.get_setting("payments_enabled", "0") == "1"
    await message.answer(
        welcome,
        reply_markup=main_menu(
            user.id in config.admin_ids,
            payments_enabled,
            hide_keyboard=user.id not in config.admin_ids and not payments_enabled,
        ),
    )
    await message.answer("Kerakli bo‘limni tanlang:", reply_markup=personal_menu())


@router.chat_join_request()
async def chat_join_request_handler(
    request: ChatJoinRequest,
    db: Database,
    config: Config,
) -> None:
    invite_link = request.invite_link
    if (
        config.access_group_id is None
        or request.chat.id != config.access_group_id
        or invite_link is None
        or invite_link.creates_join_request is not True
    ):
        logger.warning(
            "Bot ruxsat so‘rovi rad etildi: user_id=%s chat_id=%s",
            request.from_user.id,
            request.chat.id,
        )
        return
    await db.grant_bot_access(request.from_user.id, request.chat.id)
    logger.info("Botdan foydalanish ruxsati berildi: user_id=%s chat_id=%s", request.from_user.id, request.chat.id)


@router.callback_query(F.data == "subscription:check")
async def subscription_check(callback: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    allowed, channels = await subscription_status(bot, db, callback.from_user.id)
    if allowed:
        await callback.message.edit_text("✅ Barcha kanal va guruhlarga a’zolik tasdiqlandi.")
        await callback.answer("Obuna tasdiqlandi!")
        payments_enabled = await db.get_setting("payments_enabled", "0") == "1"
        await callback.message.answer(
            await get_welcome(bot, db, config),
            reply_markup=main_menu(
                callback.from_user.id in config.admin_ids,
                payments_enabled,
                hide_keyboard=callback.from_user.id not in config.admin_ids and not payments_enabled,
            ),
        )
        await callback.message.answer("Kerakli bo‘limni tanlang:", reply_markup=personal_menu())
    else:
        await callback.answer("A’zolik hali barcha chatlarda tasdiqlanmadi.", show_alert=True)
        await callback.message.edit_text(
            await db.get_bot_setting("subscription_text", bot.id, DEFAULT_SUBSCRIPTION),
            reply_markup=subscription_keyboard(channels) if channels else empty_subscription_keyboard(),
        )


@router.callback_query(F.data == "noop")
async def ignore_noop(callback: CallbackQuery) -> None:
    await callback.answer()