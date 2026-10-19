import asyncio
import fcntl
import hashlib
import logging
import os
import tempfile
from typing import Any, Awaitable, Callable

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiogram import BaseMiddleware
from aiogram.fsm.storage.memory import MemoryStorage

from config import Config, load_config
from database import Database
from handlers import admin, movies, payments, start
from keyboards import access_invite_keyboard
from telegram_commands import admin_commands, public_commands, set_admin_commands


def healthcheck_response(request_line: bytes) -> tuple[int, bytes]:
    parts = request_line.decode("ascii", errors="replace").split()
    if len(parts) >= 2 and parts[0] == "GET" and parts[1].split("?", 1)[0] in {"/", "/health"}:
        return 200, b"ok\n"
    return 404, b"not found\n"


async def _handle_healthcheck(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    status, body = healthcheck_response(await reader.readline())
    reason = "OK" if status == 200 else "Not Found"
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "Connection: close\r\n\r\n".encode("ascii") + body
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def start_health_server(logger: logging.Logger) -> asyncio.Server | None:
    port_value = os.getenv("PORT")
    if port_value is None:
        return None
    try:
        port = int(port_value)
    except ValueError as error:
        raise RuntimeError("PORT musbat port raqami bo‘lishi kerak.") from error
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT 1 dan 65535 gacha bo‘lishi kerak.")
    server = await asyncio.start_server(_handle_healthcheck, host="0.0.0.0", port=port)
    logger.info("Health endpoint tinglamoqda: 0.0.0.0:%s", port)
    return server


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
        join_request = event.chat_join_request
        if join_request is not None:
            return await handler(event, data)
        if message and message.chat.type != "private":
            return None
        if callback and callback.message and callback.message.chat.type != "private":
            return None
        user = (
            callback.from_user if callback else
            message.from_user if message else None
        )
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
            if (
                data["config"].access_group_id is not None
                and not join_request
                and not await db.has_bot_access(user.id)
            ):
                invite_link = await db.get_setting("access_invite_link")
                text = (
                    "🔐 Botdan foydalanish uchun ulangan guruhga qo‘shilish so‘rovini yuboring. "
                    "Guruhga a’zo bo‘lish shart emas; so‘rov botga ruxsat beradi."
                )
                if invite_link:
                    markup = access_invite_keyboard(invite_link)
                else:
                    text += "\nTaklif havolasini olish uchun bot adminiga murojaat qiling."
                    markup = None
                if message:
                    await message.answer(text, reply_markup=markup)
                elif callback:
                    await callback.answer("Botdan foydalanish uchun avval guruhga so‘rov yuboring.", show_alert=True)
                    await callback.message.answer(text, reply_markup=markup)
                return None
        return await handler(event, data)


class PollingInstanceLock:
    def __init__(self, tokens: tuple[str, ...]) -> None:
        self.tokens = tokens
        self._handles: list[Any] = []

    def acquire(self) -> None:
        try:
            for token in self.tokens:
                token_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
                path = os.path.join(tempfile.gettempdir(), f"kino-bot-polling-{token_id}.lock")
                handle = open(path, "a", encoding="ascii")
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    handle.close()
                    raise RuntimeError(
                        "Bu serverda bot tokeni bilan polling jarayoni allaqachon ishlayapti. "
                        "Bitta bot tokeni uchun Render’da faqat bitta faol servis/instance qoldiring."
                    ) from error
                self._handles.append(handle)
        except Exception:
            self.release()
            raise

    def release(self) -> None:
        while self._handles:
            handle = self._handles.pop()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


async def configure_commands(bot: Bot, admin_ids: tuple[int, ...], series_enabled: bool = False) -> None:
    await bot.set_my_commands(public_commands())
    for admin_id in admin_ids:
        await set_admin_commands(bot, admin_id, series_enabled)


async def main() -> None:
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("kino_bot")
    db = Database(config.database_path)
    bots = [Bot(token=token) for token in config.bot_tokens]
    polling_lock = PollingInstanceLock(config.bot_tokens)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.outer_middleware(AvailabilityMiddleware())
    dispatcher.include_router(start.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(payments.router)
    dispatcher.include_router(movies.router)
    dispatcher.errors.register(handle_error)
    health_server = None

    try:
        polling_lock.acquire()
        await db.connect()
        await admin.seed_admins(db, config)
        bot_registry = {}
        for bot in bots:
            await configure_commands(bot, config.admin_ids, series_enabled=True)
            identity = await bot.get_me()
            if not bot_registry:
                await db.migrate_legacy_channels(identity.id)
            await db.initialize_bot_subscription_settings(
                identity.id,
                inherit_legacy=not bot_registry,
            )
            bot_registry[identity.id] = bot
            logger.info("Bot ishga tushdi: @%s", identity.username)
        logger.info("Ownerlar soni: %s; botlar soni: %s", len(config.admin_ids), len(bots))
        health_server = await start_health_server(logger)
        await dispatcher.start_polling(
            *bots,
            db=db,
            config=config,
            bot_registry=bot_registry,
            allowed_updates=dispatcher.resolve_used_update_types(),
            close_bot_session=False,
        )
    except TelegramAPIError as error:
        logger.error("Telegram API xatosi (%s). Token va internet ulanishini tekshiring.", type(error).__name__)
        raise
    finally:
        if health_server is not None:
            health_server.close()
            await health_server.wait_closed()
        polling_lock.release()
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