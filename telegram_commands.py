import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BotCommand, BotCommandScopeChat

logger = logging.getLogger(__name__)


def public_commands() -> list[BotCommand]:
    return [
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="cancel", description="Joriy amalni bekor qilish"),
    ]


def admin_commands(series_enabled: bool) -> list[BotCommand]:
    commands = [
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="admin", description="Admin paneli"),
        BotCommand(command="cancel", description="Joriy amalni bekor qilish"),
    ]
    if series_enabled:
        commands.extend([
            BotCommand(command="addseries", description="Serial qo‘shish"),
            BotCommand(command="addseriesepisode", description="Serialga qism qo‘shish"),
            BotCommand(command="part", description="Bo‘lim va qism raqamini belgilash"),
            BotCommand(command="series", description="Seriallar ro‘yxati"),
        ])
    return commands


async def set_admin_commands(bot: Bot, admin_id: int, series_enabled: bool) -> None:
    try:
        await bot.set_my_commands(
            admin_commands(series_enabled),
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
    except TelegramBadRequest as error:
        if "chat not found" not in str(error).lower():
            raise
        logger.warning(
            "Admin buyruqlari chat ochilmagani uchun hozircha o‘rnatilmadi: admin_id=%s",
            admin_id,
        )