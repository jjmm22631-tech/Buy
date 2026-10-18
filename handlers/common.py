from aiogram.types import CallbackQuery, Message
from aiogram import Bot

from config import Config
from database import Database


def is_series_bot(bot: Bot, config: Config) -> bool:
    return len(config.bot_tokens) > 1 and bot.token == config.bot_tokens[1]


async def is_admin(db: Database, telegram_id: int, config: Config) -> bool:
    return telegram_id in config.admin_ids and await db.get_admin(telegram_id) is not None


async def can(db: Database, telegram_id: int, permission: str, config: Config) -> bool:
    if telegram_id not in config.admin_ids:
        return False
    admin = await db.get_admin(telegram_id)
    if not admin:
        return False
    return admin["role"] == "owner" or permission in admin["permissions"]


async def deny_message(message: Message, db: Database, permission: str, config: Config) -> bool:
    if await can(db, message.from_user.id, permission, config):
        return False
    await message.answer("⛔ Bu amal uchun ruxsatingiz yo‘q.")
    return True


async def deny_callback(callback: CallbackQuery, db: Database, permission: str, config: Config) -> bool:
    if await can(db, callback.from_user.id, permission, config):
        return False
    await callback.answer("Bu amal uchun ruxsatingiz yo‘q.", show_alert=True)
    return True
