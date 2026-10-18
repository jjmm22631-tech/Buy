import asyncio
import json
import logging

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from database import Database
from handlers.common import can, deny_callback, deny_message
from handlers.states import (
    AdminManage, Broadcast, ChannelManage, PaymentSetup, SettingEdit, UserManage,
)
from keyboards import admin_menu, cancel_menu, confirm_keyboard, main_menu

router = Router(name="admin")
logger = logging.getLogger(__name__)
ADMIN_PERMISSIONS = ["movies", "users", "broadcast", "channels", "payments", "settings", "stats", "logs"]
EDITABLE_SETTINGS = {
    "welcome_text": "Kutib olish xabari",
    "not_found_text": "Kino topilmagandagi xabar",
    "subscription_text": "Majburiy obuna matni",
    "support_username": "Qo‘llab-quvvatlash username'i",
    "advertisement_text": "Reklama matni",
}


class AdminAccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        config: Config = data["config"]
        if user and user.id not in config.admin_ids:
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Bu bo‘lim faqat adminlar uchun.", show_alert=True)
            elif isinstance(event, Message):
                text = (event.text or "").split(maxsplit=1)[0].split("@", 1)[0]
                if event.text != "❌ Bekor qilish" and text != "/cancel":
                    await event.answer("⛔ Bu bo‘lim faqat adminlar uchun.")
                else:
                    return await handler(event, data)
            return None
        return await handler(event, data)


admin_access = AdminAccessMiddleware()
router.message.outer_middleware(admin_access)
router.callback_query.outer_middleware(admin_access)


async def seed_admins(db: Database, config: Config) -> None:
    for owner_id in config.admin_ids:
        await db.add_admin(owner_id, "owner", ADMIN_PERMISSIONS, owner_id)
    defaults = {
        "welcome_text": "Assalomu alaykum! 👋\nUzbek Kinolar Olami botiga xush kelibsiz! 🎬\n\nSevimli kinolaringizni topish uchun kino kodini yuboring.",
        "not_found_text": "❌ Bunday koddagi kino topilmadi.\n\nIltimos, kodni tekshirib qayta yuboring.",
        "subscription_text": "❗ Botdan foydalanish uchun quyidagi kanallarga obuna bo‘ling.",
        "subscription_enabled": "1",
        "bot_enabled": "1",
        "payments_enabled": "0",
        "payment_amount": "0",
        "payment_methods": "[]",
        "payment_instructions": "To‘lovni amalga oshirib, chek yoki to‘lov dalilini shu yerga yuboring.",
        "support_username": "",
        "advertisement_text": "",
    }
    for key, value in defaults.items():
        if await db.fetchone("SELECT id FROM settings WHERE key=?", (key,)) is None:
            await db.set_setting(key, value)


@router.message(Command("admin"))
@router.message(F.text == "🛠 Admin paneli")
async def open_admin(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id not in config.admin_ids:
        await message.answer("⛔ Admin paneli faqat adminlar uchun.")
        return
    await message.answer("🛠 Boshqaruv paneli", reply_markup=admin_menu())


@router.message(F.text == "🔙 Orqaga")
async def back_to_main(message: Message, db: Database, config: Config) -> None:
    await message.answer(
        "Asosiy menyu",
        reply_markup=main_menu(
            message.from_user.id in config.admin_ids,
            await db.get_setting("payments_enabled", "0") == "1",
            hide_keyboard=message.from_user.id not in config.admin_ids,
        ),
    )


@router.message(Command("cancel"))
@router.message(F.text == "❌ Bekor qilish")
async def cancel_state(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    current = await state.get_state()
    await state.clear()
    if message.from_user.id in config.admin_ids:
        await message.answer("❌ Jarayon bekor qilindi.", reply_markup=admin_menu())
    elif current:
        await message.answer("Jarayon bekor qilindi.")


@router.message(F.text == "👑 Adminlar")
async def admin_management_menu(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id not in config.admin_ids:
        await message.answer("⛔ Adminlarni faqat asosiy admin boshqaradi.")
        return
    await message.answer(
        "👑 Adminlarni boshqarish\n\n➕ Admin qo‘shish: /addadmin\n➖ Admin o‘chirish: /removeadmin\n📋 Ro‘yxat: /admins\n🔍 ID orqali qidirish: /findadmin <ID>",
        reply_markup=admin_menu(),
    )


async def is_owner(db: Database, config: Config, telegram_id: int) -> bool:
    return telegram_id in config.admin_ids


@router.message(Command("addadmin"))
async def add_admin_start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await message.answer("⛔ Faqat asosiy admin admin qo‘sha oladi.")
        return
    await state.clear()
    await state.set_state(AdminManage.add_id)
    await message.answer("Yangi adminning Telegram ID raqamini yuboring:", reply_markup=cancel_menu())


@router.message(AdminManage.add_id)
async def add_admin_id(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await state.clear()
        await message.answer("⛔ Ruxsat bekor qilingan.")
        return
    value = (message.text or "").strip()
    if not value.isdigit() or int(value) <= 0:
        await message.answer("ID faqat musbat raqamlardan iborat bo‘lsin. Qayta yuboring:")
        return
    telegram_id = int(value)
    if telegram_id in config.admin_ids:
        await message.answer("Bu foydalanuvchi .env faylida asosiy admin sifatida belgilangan.")
        return
    await state.update_data(target_id=telegram_id)
    await state.set_state(AdminManage.add_confirm)
    await message.answer(f"{telegram_id} ID raqamli foydalanuvchini admin qilishni tasdiqlaysizmi?", reply_markup=confirm_keyboard("admin:add:confirm"))


@router.callback_query(F.data == "admin:add:confirm")
async def add_admin_confirm(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    if not await is_owner(db, config, callback.from_user.id):
        await callback.answer("Faqat asosiy admin.", show_alert=True)
        return
    data = await state.get_data()
    telegram_id = data.get("target_id")
    if not isinstance(telegram_id, int) or telegram_id <= 0:
        await callback.answer("Admin ma’lumoti eskirgan. Jarayonni qayta boshlang.", show_alert=True)
        await state.clear()
        return
    await db.add_admin(telegram_id, "admin", ADMIN_PERMISSIONS, callback.from_user.id)
    await db.log_admin(callback.from_user.id, "admin_added", str(telegram_id))
    await state.clear()
    await callback.message.edit_text(f"✅ {telegram_id} admin sifatida qo‘shildi.")
    await callback.answer()


@router.message(Command("removeadmin"))
async def remove_admin_start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await message.answer("⛔ Faqat asosiy admin admin o‘chira oladi.")
        return
    await state.clear()
    await state.set_state(AdminManage.remove_id)
    await message.answer("O‘chiriladigan adminning Telegram ID raqamini yuboring:", reply_markup=cancel_menu())


@router.message(AdminManage.remove_id)
async def remove_admin_id(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await state.clear()
        return
    value = (message.text or "").strip()
    if not value.isdigit() or int(value) <= 0:
        await message.answer("ID faqat musbat raqamlardan iborat bo‘lsin:")
        return
    telegram_id = int(value)
    admin = await db.get_admin(telegram_id)
    if telegram_id in config.admin_ids or (admin and admin["role"] == "owner"):
        await message.answer("Asosiy adminni o‘chirib bo‘lmaydi.")
        return
    if not admin:
        await message.answer("Bu ID bo‘yicha admin topilmadi.")
        return
    await state.update_data(target_id=telegram_id)
    await state.set_state(AdminManage.remove_confirm)
    await message.answer(f"Admin ID: {telegram_id}\nO‘chirishni tasdiqlaysizmi?", reply_markup=confirm_keyboard("admin:remove:confirm"))


@router.callback_query(F.data == "admin:remove:confirm")
async def remove_admin_confirm(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    if not await is_owner(db, config, callback.from_user.id):
        await callback.answer("Faqat asosiy admin.", show_alert=True)
        return
    data = await state.get_data()
    target = data.get("target_id")
    if not isinstance(target, int) or target in config.admin_ids:
        await callback.answer("Asosiy adminni o‘chirib bo‘lmaydi.", show_alert=True)
        await state.clear()
        return
    admin = await db.get_admin(target)
    if admin and admin["role"] != "owner":
        await db.execute("DELETE FROM admins WHERE telegram_id=?", (target,))
        await db.log_admin(callback.from_user.id, "admin_removed", str(target))
        await callback.message.edit_text(f"✅ {target} adminlikdan olindi.")
    else:
        await callback.message.edit_text("Admin topilmadi yoki uni o‘chirish mumkin emas.")
    await state.clear()
    await callback.answer()


@router.message(Command("admins"))
async def admins_list(message: Message, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await message.answer("⛔ Adminlar ro‘yxati faqat asosiy admin uchun.")
        return
    rows = await db.fetchall("SELECT telegram_id, role, permissions FROM admins ORDER BY role, telegram_id")
    if not rows:
        await message.answer("Adminlar ro‘yxati bo‘sh.")
        return
    lines = []
    for row in rows:
        role = "Asosiy admin" if row["role"] == "owner" else "Admin"
        permissions = "barchasi" if row["role"] == "owner" else ", ".join(json.loads(row["permissions"]))
        lines.append(f"{row['telegram_id']} — {role} ({permissions})")
    await message.answer("📋 Adminlar:\n" + "\n".join(lines))


@router.message(Command("findadmin"))
async def find_admin(message: Message, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await message.answer("⛔ Ruxsat yo‘q.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /findadmin <Telegram_ID>")
        return
    admin = await db.get_admin(int(parts[1]))
    await message.answer(f"Admin: {parts[1]}\nHolati: {'mavjud' if admin else 'topilmadi'}" + (f"\nHuquqlari: {', '.join(admin['permissions'])}" if admin else ""))


@router.message(Command("permissions"))
async def set_admin_permissions(message: Message, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await message.answer("⛔ Admin huquqlarini faqat asosiy admin o‘zgartiradi.")
        return
    parts = (message.text or "").split(maxsplit=2)
    allowed = set(ADMIN_PERMISSIONS)
    if len(parts) != 3 or not parts[1].isdigit():
        await message.answer("Format: /permissions <admin_ID> <movies,users,broadcast,channels,payments,settings,stats,logs>\nHuquqlarni olib tashlash uchun: /permissions <ID> none")
        return
    target_id = int(parts[1])
    target = await db.get_admin(target_id)
    if not target or target["role"] == "owner" or target_id in config.admin_ids:
        await message.answer("Admin topilmadi yoki asosiy admin huquqlarini o‘zgartirib bo‘lmaydi.")
        return
    values = [] if parts[2].strip().lower() == "none" else list(dict.fromkeys(item.strip() for item in parts[2].split(",") if item.strip()))
    unknown = set(values) - allowed
    if unknown:
        await message.answer("Noma’lum huquq. Ruxsatlar: " + ", ".join(ADMIN_PERMISSIONS))
        return
    await db.add_admin(target_id, "admin", values, target["added_by"] or message.from_user.id)
    await db.log_admin(message.from_user.id, "admin_permissions_changed", f"target={target_id} permissions={','.join(values)}")
    await message.answer(f"✅ {target_id} admin huquqlari yangilandi: {', '.join(values) or 'hech biri'}")


@router.callback_query(F.data == "cancel")
async def cancel_inline(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer("Bekor qilindi.")
    try:
        await callback.message.edit_text("❌ Jarayon bekor qilindi.")
    except TelegramBadRequest:
        pass


@router.message(F.text == "📢 Majburiy obuna")
async def channels_menu(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "channels", config):
        return
    enabled = await db.get_setting("subscription_enabled", "1") == "1"
    await message.answer(
        f"📢 Majburiy obuna: {'yoqilgan' if enabled else 'o‘chirilgan'}\n\n"
        "Kanal qo‘shish: /addchannel <ID> | <username> | <havola>\n"
        "Kanallar: /channels\nObunani yoqish/o‘chirish: /subscription_toggle",
    )


@router.message(Command("addchannel"))
async def add_channel(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "channels", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    fields = [part.strip() for part in parts[1].split("|")] if len(parts) == 2 else []
    if len(fields) != 3 or not fields[0].lstrip("-").isdigit() or not fields[2].startswith(("https://t.me/", "http://t.me/")):
        await message.answer("Format: /addchannel <kanal_ID> | <@username yoki username> | <https://t.me/...>")
        return
    channel_id, username, link = int(fields[0]), fields[1].lstrip("@") or None, fields[2]
    try:
        await db.execute(
            "INSERT INTO channels(channel_id,channel_username,invite_link) VALUES(?,?,?) "
            "ON CONFLICT(channel_id) DO UPDATE SET channel_username=excluded.channel_username, invite_link=excluded.invite_link, is_active=1",
            (channel_id, username, link),
        )
    except Exception as error:
        logger.warning("Kanal qo‘shilmadi: %s", type(error).__name__)
        await message.answer("Kanalni saqlab bo‘lmadi. Kanal ID va havolani tekshiring.")
        return
    await db.log_admin(message.from_user.id, "channel_added", str(channel_id))
    await message.answer("✅ Kanal majburiy obunaga qo‘shildi. A’zolikni tekshirish uchun bot kanal administratori bo‘lishi kerak.")


@router.message(Command("channels"))
async def channel_list(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "channels", config):
        return
    channels = await db.fetchall("SELECT * FROM channels ORDER BY id")
    if not channels:
        await message.answer("Kanallar ro‘yxati bo‘sh.")
        return
    lines = [f"{row['id']}. {row['channel_id']} @{row['channel_username'] or 'username yo‘q'} — {row['invite_link']}" for row in channels]
    await message.answer("📋 Kanallar:\n" + "\n".join(lines) + "\nO‘chirish: /delchannel <ID>")


@router.message(Command("delchannel"))
async def delete_channel(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "channels", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /delchannel <ro‘yxatdagi_ID>")
        return
    result = await db.execute("DELETE FROM channels WHERE id=?", (int(parts[1]),))
    if not result:
        await message.answer("Kanal topilmadi.")
        return
    await db.log_admin(message.from_user.id, "channel_removed", parts[1])
    await message.answer("✅ Kanal o‘chirildi.")


@router.message(Command("subscription_toggle"))
async def toggle_subscription(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "channels", config):
        return
    current = await db.get_setting("subscription_enabled", "1") == "1"
    value = "0" if current else "1"
    await db.set_setting("subscription_enabled", value)
    await db.log_admin(message.from_user.id, "subscription_toggled", value)
    await message.answer(f"✅ Majburiy obuna {'yoqildi' if value == '1' else 'o‘chirildi'}.")


@router.message(F.text == "👥 Foydalanuvchilar")
async def users_menu(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "users", config):
        return
    await message.answer("👥 Foydalanuvchilar\nJami: /userstats\nRo‘yxat: /users\nID bo‘yicha qidirish: /user <ID>\nBloklash: /blockuser <ID>\nBlokdan chiqarish: /unblockuser <ID>")


@router.message(Command("userstats"))
async def user_stats(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "users", config):
        return
    row = await db.fetchone("SELECT COUNT(*) total, SUM(is_blocked=0) active, SUM(is_blocked=1) blocked FROM users")
    await message.answer(f"Jami foydalanuvchilar: {row['total']}\n🟢 Faol: {row['active'] or 0}\n🚫 Bloklangan: {row['blocked'] or 0}")


@router.message(Command("users"))
async def user_list(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "users", config):
        return
    rows = await db.fetchall("SELECT telegram_id,full_name,username,is_blocked FROM users ORDER BY id DESC LIMIT 50")
    if not rows:
        await message.answer("Foydalanuvchilar yo‘q.")
        return
    await message.answer("📋 So‘nggi foydalanuvchilar:\n" + "\n".join(
        f"{row['telegram_id']} — {row['full_name'][:40]} @{row['username'] or 'username yo‘q'} {'(bloklangan)' if row['is_blocked'] else ''}"
        for row in rows
    ))


@router.message(Command("user"))
async def find_user(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "users", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /user <Telegram_ID>")
        return
    row = await db.fetchone("SELECT * FROM users WHERE telegram_id=?", (int(parts[1]),))
    if not row:
        await message.answer("Foydalanuvchi topilmadi.")
        return
    await message.answer(f"ID: {row['telegram_id']}\nIsmi: {row['full_name']}\nUsername: @{row['username'] or 'yo‘q'}\nQo‘shilgan: {row['joined_at']}\nFaollik: {row['last_active_at']}\nHolati: {'bloklangan' if row['is_blocked'] else 'faol'}")


@router.message(Command("blockuser"))
async def block_user_start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "users", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /blockuser <Telegram_ID>")
        return
    target_id = int(parts[1])
    row = await db.fetchone("SELECT telegram_id, full_name FROM users WHERE telegram_id=?", (target_id,))
    if not row:
        await message.answer("Foydalanuvchi topilmadi.")
        return
    await state.set_state(UserManage.block_confirm)
    await state.update_data(target_id=target_id)
    await message.answer(f"{row['full_name']} ({target_id}) foydalanuvchisini bloklashni tasdiqlaysizmi?", reply_markup=confirm_keyboard("user:block:confirm"))


@router.callback_query(F.data == "user:block:confirm")
async def block_user_confirm(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_callback(callback, db, "users", config):
        return
    data = await state.get_data()
    target_id = data.get("target_id")
    if not isinstance(target_id, int) or target_id == callback.from_user.id:
        await callback.answer("Noto‘g‘ri foydalanuvchi.", show_alert=True)
        await state.clear()
        return
    await db.execute("UPDATE users SET is_blocked=1 WHERE telegram_id=?", (target_id,))
    await db.log_admin(callback.from_user.id, "user_blocked", str(target_id))
    await state.clear()
    await callback.message.edit_text("✅ Foydalanuvchi bloklandi.")
    await callback.answer()


@router.message(Command("unblockuser"))
async def unblock_user(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "users", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /unblockuser <Telegram_ID>")
        return
    target_id = int(parts[1])
    updated = await db.execute("UPDATE users SET is_blocked=0 WHERE telegram_id=? AND is_blocked=1", (target_id,))
    if not updated:
        await message.answer("Bloklangan foydalanuvchi topilmadi.")
        return
    await db.log_admin(message.from_user.id, "user_unblocked", str(target_id))
    await message.answer("✅ Foydalanuvchi blokdan chiqarildi.")


@router.message(F.text == "📨 Xabar yuborish")
async def broadcast_start(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if await deny_message(message, db, "broadcast", config):
        return
    await state.clear()
    await state.set_state(Broadcast.message)
    await message.answer(
        "Barcha foydalanuvchilarga yuboriladigan xabarni (matn, rasm, video yoki boshqa media) yuboring:",
        reply_markup=cancel_menu(),
    )


@router.message(Broadcast.message)
async def broadcast_preview(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "broadcast", config):
        await state.clear()
        return
    await state.update_data(message_id=message.message_id, chat_id=message.chat.id, message_type=(message.content_type or "unknown"))
    await state.set_state(Broadcast.confirm)
    await message.answer("Yuqoridagi xabar barcha faol foydalanuvchilarga yuborilsinmi?", reply_markup=confirm_keyboard("broadcast:send"))


@router.callback_query(F.data == "broadcast:send")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, bot: Bot, db: Database, config: Config) -> None:
    if await deny_callback(callback, db, "broadcast", config):
        return
    data = await state.get_data()
    if not data.get("message_id") or not data.get("chat_id"):
        await callback.answer("Xabar topilmadi. Jarayonni qayta boshlang.", show_alert=True)
        await state.clear()
        return
    users = await db.fetchall("SELECT telegram_id FROM users WHERE is_blocked=0")
    broadcast_id = await db.execute(
        "INSERT INTO broadcasts(admin_id,message_type,status,total_users) VALUES(?,?,?,?)",
        (callback.from_user.id, data.get("message_type", "unknown"), "sending", len(users)),
    )
    await state.clear()
    await callback.answer("Yuborish boshlandi.")
    sent = failed = 0
    progress = await callback.message.edit_text(f"📨 Yuborilmoqda... 0/{len(users)}")
    for index, user in enumerate(users, start=1):
        try:
            await bot.copy_message(user["telegram_id"], data["chat_id"], data["message_id"])
            sent += 1
        except TelegramRetryAfter as error:
            await asyncio.sleep(error.retry_after + 0.5)
            try:
                await bot.copy_message(user["telegram_id"], data["chat_id"], data["message_id"])
                sent += 1
            except TelegramAPIError:
                failed += 1
        except TelegramAPIError:
            failed += 1
        if index % 25 == 0:
            await db.execute("UPDATE broadcasts SET sent_count=?,failed_count=? WHERE id=?", (sent, failed, broadcast_id))
            try:
                await progress.edit_text(f"📨 Yuborilmoqda... {index}/{len(users)}\n✅ {sent} | ❌ {failed}")
            except TelegramAPIError:
                pass
        await asyncio.sleep(0.04)
    await db.execute(
        "UPDATE broadcasts SET status='completed',sent_count=?,failed_count=?,completed_at=CURRENT_TIMESTAMP WHERE id=?",
        (sent, failed, broadcast_id),
    )
    await db.log_admin(callback.from_user.id, "broadcast_sent", f"id={broadcast_id} sent={sent} failed={failed}")
    await progress.edit_text(f"✅ Yuborish yakunlandi.\nYuborildi: {sent}\nXatolik: {failed}\nJami: {len(users)}")


@router.message(F.text == "⚙️ Bot sozlamalari")
async def settings_menu(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "settings", config):
        return
    bot_enabled = await db.get_setting("bot_enabled", "1") == "1"
    await message.answer(
        "⚙️ Bot sozlamalari\n" + "\n".join(f"/set_{key} — {label}" for key, label in EDITABLE_SETTINGS.items())
        + f"\n/bot_toggle — Bot holati ({'yoqilgan' if bot_enabled else 'o‘chirilgan'})\n/set_advertisement_text — Reklama matni",
    )


@router.message(F.text.startswith("/set_"))
async def set_text_setting(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "settings", config):
        return
    command = (message.text or "").split(maxsplit=1)[0][5:]
    key = command
    if key not in EDITABLE_SETTINGS:
        await message.answer("Bu sozlama topilmadi.")
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        await message.answer(f"Yangi qiymatni yuboring: /set_{key} <matn>\nBo‘sh qiymat uchun /set_{key} clear")
        return
    value = "" if parts[1].strip().lower() == "clear" else parts[1].strip()
    if len(value) > 3000:
        await message.answer("Matn 3000 belgidan oshmasin.")
        return
    await db.set_setting(key, value)
    await db.log_admin(message.from_user.id, "setting_changed", key)
    await message.answer("✅ Sozlama yangilandi.")


@router.message(Command("bot_toggle"))
async def toggle_bot(message: Message, db: Database, config: Config) -> None:
    if not await is_owner(db, config, message.from_user.id):
        await message.answer("⛔ Botni faqat asosiy admin yoqib/o‘chira oladi.")
        return
    current = await db.get_setting("bot_enabled", "1") == "1"
    value = "0" if current else "1"
    await db.set_setting("bot_enabled", value)
    await db.log_admin(message.from_user.id, "bot_status_changed", value)
    await message.answer(f"✅ Bot {'yoqildi' if value == '1' else 'foydalanuvchilar uchun o‘chirildi'}.")


@router.message(F.text == "💳 To‘lov sozlamalari")
async def payment_admin_menu(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "payments", config):
        return
    enabled = await db.get_setting("payments_enabled", "0") == "1"
    methods = json.loads(await db.get_setting("payment_methods", "[]"))
    amount = await db.get_setting("payment_amount", "0")
    await message.answer(
        f"💳 To‘lov sozlamalari\nHolati: {'yoqilgan' if enabled else 'o‘chirilgan'}\nNarx: {amount}\nUsullar: {', '.join(methods) if methods else 'kiritilmagan'}\n\n"
        "/payment_toggle — yoqish/o‘chirish\n/payment_price <summa>\n/payment_methods <usul1, usul2>\n/payment_instructions <matn>\n/payments — to‘lovlar tarixi"
    )


@router.message(Command("payment_toggle"))
async def payment_toggle(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "payments", config):
        return
    enabled = await db.get_setting("payments_enabled", "0") != "1"
    await db.set_setting("payments_enabled", "1" if enabled else "0")
    await db.log_admin(message.from_user.id, "payment_setting_changed", f"enabled={enabled}")
    await message.answer(f"✅ To‘lovlar {'yoqildi' if enabled else 'o‘chirildi'}.")


@router.message(Command("payment_price"))
async def payment_price(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "payments", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    try:
        amount = float(parts[1])
        if amount < 0 or amount > 1_000_000_000:
            raise ValueError
    except (IndexError, ValueError):
        await message.answer("Narxni musbat son bilan kiriting: /payment_price 25000")
        return
    await db.set_setting("payment_amount", str(amount))
    await db.log_admin(message.from_user.id, "payment_price_changed", str(amount))
    await message.answer("✅ Narx saqlandi.")


@router.message(Command("payment_methods"))
async def payment_methods(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "payments", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    methods = [item.strip()[:60] for item in parts[1].split(",") if item.strip()] if len(parts) > 1 else []
    if not methods or len(methods) > 10:
        await message.answer("To‘lov usullarini vergul bilan ajratib kiriting. Masalan: /payment_methods Bank o‘tkazmasi, Payme")
        return
    await db.set_setting("payment_methods", json.dumps(methods, ensure_ascii=False))
    await db.log_admin(message.from_user.id, "payment_methods_changed", ", ".join(methods))
    await message.answer("✅ To‘lov usullari saqlandi. Faqat qonuniy, amalda mavjud usullarni kiriting.")


@router.message(Command("payment_instructions"))
async def payment_instructions(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "payments", config):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2 or len(parts[1]) > 2500:
        await message.answer("Ko‘rsatmani kiriting: /payment_instructions To‘lovni amalga oshirib, chekni yuboring.")
        return
    await db.set_setting("payment_instructions", parts[1])
    await db.log_admin(message.from_user.id, "payment_instructions_changed")
    await message.answer("✅ Ko‘rsatmalar saqlandi.")


@router.message(Command("payments"))
async def payment_history(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "payments", config):
        return
    rows = await db.fetchall("SELECT id,user_id,amount,payment_method,status,created_at FROM payments ORDER BY id DESC LIMIT 30")
    if not rows:
        await message.answer("To‘lovlar tarixi bo‘sh.")
        return
    await message.answer("💳 So‘nggi to‘lovlar:\n" + "\n".join(f"#{row['id']} | user {row['user_id']} | {row['amount']} | {row['payment_method']} | {row['status']} | {row['created_at']}" for row in rows))


@router.callback_query(F.data.startswith("payment:review:"))
async def review_payment(callback: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    if await deny_callback(callback, db, "payments", config):
        return
    parts = callback.data.split(":")
    if len(parts) != 4 or not parts[2].isdigit() or parts[3] not in {"approve", "reject"}:
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return
    payment_id = int(parts[2])
    status = "confirmed" if parts[3] == "approve" else "rejected"
    row = await db.fetchone("SELECT user_id,status FROM payments WHERE id=?", (payment_id,))
    if not row or row["status"] != "pending":
        await callback.answer("Bu to‘lov oldin ko‘rib chiqilgan yoki topilmadi.", show_alert=True)
        return
    changed = await db.execute(
        "UPDATE payments SET status=?,confirmed_at=CURRENT_TIMESTAMP,confirmed_by=? WHERE id=? AND status='pending'",
        (status, callback.from_user.id, payment_id),
    )
    if not changed:
        await callback.answer("To‘lov boshqa admin tomonidan ko‘rib chiqilgan.", show_alert=True)
        return
    await db.log_admin(callback.from_user.id, f"payment_{status}", str(payment_id))
    result_text = "✅ To‘lov tasdiqlandi." if status == "confirmed" else "❌ To‘lov rad etildi."
    try:
        await bot.send_message(row["user_id"], result_text)
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.info("To‘lov natijasini foydalanuvchiga yetkazib bo‘lmadi: payment_id=%s", payment_id)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"{result_text} To‘lov #{payment_id}")
    await callback.answer("✅ Saqlandi.")


@router.message(F.text == "📊 Statistika")
async def statistics(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "stats", config):
        return
    stats = await db.fetchone(
        "SELECT (SELECT COUNT(*) FROM users) users_total, "
        "(SELECT COUNT(*) FROM users WHERE date(joined_at)=date('now')) users_today, "
        "(SELECT COUNT(*) FROM movies WHERE is_active=1) movies_total, "
        "(SELECT COUNT(*) FROM movies WHERE date(created_at)=date('now')) movies_today, "
        "(SELECT COUNT(*) FROM movie_requests) requests_total, "
        "(SELECT COUNT(*) FROM movie_requests WHERE delivered=1) sent_total, "
        "(SELECT COUNT(*) FROM users WHERE is_blocked=1) blocked_total, "
        "(SELECT COUNT(*) FROM payments) payments_total, "
        "(SELECT COUNT(*) FROM payments WHERE status='confirmed') payments_confirmed"
    )
    popular = await db.fetchall("SELECT movie_code,COUNT(*) AS hits FROM movie_requests WHERE found=1 GROUP BY movie_code ORDER BY hits DESC LIMIT 5")
    text = (
        "📊 Statistika\n"
        f"Foydalanuvchilar: {stats['users_total']} (bugun +{stats['users_today']})\n"
        f"Kinolar: {stats['movies_total']} (bugun +{stats['movies_today']})\n"
        f"Kino so‘rovlari: {stats['requests_total']}\nMuvaffaqiyatli yuborishlar: {stats['sent_total']}\n"
        f"Bloklangan foydalanuvchilar: {stats['blocked_total']}\n"
        f"To‘lovlar: {stats['payments_total']} (tasdiqlangan: {stats['payments_confirmed']})"
    )
    if popular:
        text += "\n🔥 Ko‘p so‘ralgan kodlar:\n" + "\n".join(f"{row['movie_code']} — {row['hits']} marta" for row in popular)
    await message.answer(text)


@router.message(F.text == "📝 Harakatlar tarixi")
async def admin_history(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "logs", config):
        return
    rows = await db.fetchall("SELECT admin_id,action,details,created_at FROM admin_logs ORDER BY id DESC LIMIT 30")
    if not rows:
        await message.answer("Admin harakatlari tarixi hozircha bo‘sh.")
        return
    await message.answer("📝 So‘nggi amallar:\n" + "\n".join(f"{row['created_at']} | {row['admin_id']} | {row['action']} | {row['details']}" for row in rows))
