import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import BotCommand, BotCommandScopeChat, Message, Update
from aiogram import BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage

from config import Config, load_config
from database import Database
from handlers import admin, movies, payments, start


class AvailabilityMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        db: Database = data["db"]
        message = event.message
        callback = event.callback_query
        user = callback.from_user if callback else message.from_user if message else None
        if user is None:
            return await handler(event, data)
        await db.execute(
            "INSERT INTO users(telegram_id,full_name,username) VALUES(?,?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name,username=excluded.username,last_active_at=CURRENT_TIMESTAMP",
            (user.id, user.full_name[:255], user.username),
        )
        admin_user = user.id in data["config"].admin_ids
        if not admin_user:
            status = await db.get_setting("bot_enabled", "1")
            if status != "1":
                if message:
                    await message.answer("Bot vaqtincha ishlamayapti. Keyinroq qayta urinib ko‘ring.")
                elif callback:
                    await callback.answer("Bot vaqtincha ishlamayapti.", show_alert=True)
                return None
            user_row = await db.fetchone("SELECT is_blocked FROM users WHERE telegram_id=?", (user.id,))
            if user_row and user_row["is_blocked"]:
                if message:
                    await message.answer("🚫 Botdan foydalanishingiz cheklangan. Admin bilan bog‘laning.")
                elif callback:
                    await callback.answer("Botdan foydalanishingiz cheklangan.", show_alert=True)
                return None
        return await handler(event, data)


async def configure_commands(bot: Bot, admin_ids: tuple[int, ...], series_enabled: bool = False) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="cancel", description="Joriy amalni bekor qilish"),
    ])
    admin_commands = [
        BotCommand(command="start", description="Botni boshlash"),
        BotCommand(command="admin", description="Admin paneli"),
        BotCommand(command="cancel", description="Joriy amalni bekor qilish"),
    ]
    if series_enabled:
        admin_commands.extend([
            BotCommand(command="addseries", description="Serial qo‘shish"),
            BotCommand(command="addseriesepisode", description="Serialga qism qo‘shish"),
            BotCommand(command="part", description="Bo‘lim va qism raqamini belgilash"),
            BotCommand(command="series", description="Seriallar ro‘yxati"),
        ])
    for admin_id in admin_ids:
        await bot.set_my_commands(
            admin_commands,
            scope=BotCommandScopeChat(chat_id=admin_id),
        )


async def main() -> None:
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("kino_bot")
    db = Database(config.database_path)
    bots = [Bot(token=token) for token in config.bot_tokens]
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.outer_middleware(AvailabilityMiddleware())
    dispatcher.include_router(admin.router)
    dispatcher.include_router(start.router)
    dispatcher.include_router(payments.router)
    dispatcher.include_router(movies.router)
    dispatcher.errors.register(handle_error)

    try:
        await db.connect()
        await admin.seed_admins(db, config)
        for index, bot in enumerate(bots):
            await configure_commands(bot, config.admin_ids, series_enabled=index == 1)
            identity = await bot.get_me()
            logger.info("Bot ishga tushdi: @%s", identity.username)
        logger.info("Ownerlar soni: %s; botlar soni: %s", len(config.admin_ids), len(bots))
        await dispatcher.start_polling(
            *bots,
            db=db,
            config=config,
            allowed_updates=dispatcher.resolve_used_update_types(),
            close_bot_session=False,
        )
    except TelegramAPIError as error:
        logger.error("Telegram API xatosi (%s). Token va internet ulanishini tekshiring.", type(error).__name__)
        raise
    finally:
        await db.close()
        await asyncio.gather(*(bot.session.close() for bot in bots), return_exceptions=True)


async def handle_error(event: Any) -> bool:
    update_id = event.update.update_id if getattr(event, "update", None) else "unknown"
    logging.getLogger("kino_bot.errors").error(
        "Kutilmagan xatolik: update_id=%s type=%s",
        update_id,
        type(event.exception).__name__,
    )
    return True


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (RuntimeError, TelegramAPIError) as error:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")
        logging.getLogger("kino_bot").error("Bot ishga tushmadi: %s", str(error).replace("BOT_TOKEN", "token"))