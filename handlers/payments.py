import json
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import Database
from handlers.start import register_user, show_subscription_gate, subscription_status
from handlers.states import PaymentProof
from keyboards import payment_methods_keyboard

router = Router(name="payments")
logger = logging.getLogger(__name__)


@router.message(F.text == "💳 To‘lov")
async def payment_start(message: Message, bot: Bot, db: Database) -> None:
    await register_user(message, db)
    user = await db.fetchone("SELECT is_blocked FROM users WHERE telegram_id=?", (message.from_user.id,))
    if user and user["is_blocked"]:
        await message.answer("🚫 Botdan foydalanishingiz cheklangan.")
        return
    allowed, channels = await subscription_status(bot, db, message.from_user.id)
    if not allowed:
        await show_subscription_gate(message, channels, db)
        return
    if await db.get_setting("payments_enabled", "0") != "1":
        await message.answer("To‘lov xizmati hozircha yoqilmagan.")
        return
    try:
        methods = json.loads(await db.get_setting("payment_methods", "[]"))
    except json.JSONDecodeError:
        methods = []
    if not methods:
        await message.answer("To‘lov usullari sozlanmagan. Admin bilan bog‘laning.")
        return
    amount = await db.get_setting("payment_amount", "0")
    await message.answer(f"💳 To‘lov summasi: {amount}\nUsulni tanlang:", reply_markup=payment_methods_keyboard(methods))


@router.callback_query(F.data.startswith("payment:method:"))
async def payment_method(callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot) -> None:
    if await db.get_setting("payments_enabled", "0") != "1":
        await callback.answer("To‘lov xizmati o‘chirilgan.", show_alert=True)
        return
    allowed, _ = await subscription_status(bot, db, callback.from_user.id)
    if not allowed:
        await callback.answer("Avval majburiy kanallarga obuna bo‘ling.", show_alert=True)
        return
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Noto‘g‘ri to‘lov usuli.", show_alert=True)
        return
    try:
        methods = json.loads(await db.get_setting("payment_methods", "[]"))
        method = methods[int(parts[2])]
    except (json.JSONDecodeError, IndexError, TypeError):
        await callback.answer("To‘lov usuli topilmadi.", show_alert=True)
        return
    await state.clear()
    await state.update_data(payment_method=method)
    await state.set_state(PaymentProof.proof)
    await callback.message.answer(await db.get_setting("payment_instructions", "To‘lovni amalga oshirib, chek yoki to‘lov dalilini yuboring."))
    await callback.message.answer(f"Tanlangan usul: {method}\nTo‘lov dalilini rasm, fayl yoki matn ko‘rinishida yuboring:")
    await callback.answer()


@router.message(PaymentProof.proof)
async def payment_proof(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    data = await state.get_data()
    method = data.get("payment_method")
    if not method:
        await state.clear()
        await message.answer("To‘lov jarayoni topilmadi. Qaytadan boshlang.")
        return
    proof_file_id = None
    if message.photo:
        proof_file_id = message.photo[-1].file_id
    elif message.document:
        proof_file_id = message.document.file_id
    elif message.video:
        proof_file_id = message.video.file_id
    elif message.text:
        proof_file_id = None
    else:
        await message.answer("To‘lov dalilini matn, rasm, video yoki fayl ko‘rinishida yuboring:")
        return
    amount_raw = await db.get_setting("payment_amount", "0")
    try:
        amount = max(0.0, float(amount_raw))
    except ValueError:
        amount = 0.0
    payment_id = await db.execute(
        "INSERT INTO payments(user_id,amount,payment_method,proof_file_id,status) VALUES(?,?,?,?, 'pending')",
        (message.from_user.id, amount, str(method)[:100], proof_file_id),
    )
    await state.clear()
    admins = await db.fetchall("SELECT telegram_id FROM admins")
    review_markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"payment:review:{payment_id}:approve"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"payment:review:{payment_id}:reject"),
    ]])
    delivered = 0
    for admin in admins:
        try:
            await bot.send_message(
                admin["telegram_id"],
                f"💳 Yangi to‘lov dalili\nTo‘lov ID: {payment_id}\nFoydalanuvchi: {message.from_user.id}\nSumma: {amount}\nUsul: {method}",
                reply_markup=review_markup,
            )
            if message.text:
                await bot.send_message(admin["telegram_id"], f"Dalil matni:\n{message.text[:3000]}")
            else:
                await bot.copy_message(admin["telegram_id"], message.chat.id, message.message_id)
            delivered += 1
        except (TelegramBadRequest, TelegramForbiddenError) as error:
            logger.info("To‘lov dalili adminga yetkazilmadi: admin_id=%s error=%s", admin["telegram_id"], type(error).__name__)
    if delivered == 0:
        await message.answer("⚠️ To‘lov saqlandi, lekin adminlarga xabar yetkazilmadi. Botni adminlar /start qilganini tekshiring.")
    else:
        await message.answer(f"✅ To‘lov dalili qabul qilindi. Admin tekshiruvidan so‘ng natijani yuboramiz. ID: {payment_id}")