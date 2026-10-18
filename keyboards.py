from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu(is_admin: bool, payments_enabled: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="🔍 Kino qidirish"), KeyboardButton(text="📢 Kanalimiz")],
        [KeyboardButton(text="ℹ️ Yordam")],
    ]
    if payments_enabled:
        rows.append([KeyboardButton(text="💳 To‘lov")])
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Admin paneli")])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kinolar"), KeyboardButton(text="📢 Majburiy obuna")],
            [KeyboardButton(text="👥 Foydalanuvchilar"), KeyboardButton(text="📨 Xabar yuborish")],
            [KeyboardButton(text="👑 Adminlar"), KeyboardButton(text="💳 To‘lov sozlamalari")],
            [KeyboardButton(text="⚙️ Bot sozlamalari"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="📝 Harakatlar tarixi"), KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


def movie_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kino qo‘shish"), KeyboardButton(text="✏️ Kinoni tahrirlash")],
            [KeyboardButton(text="🗑 Kinoni o‘chirish"), KeyboardButton(text="🔍 Kino qidirish")],
            [KeyboardButton(text="📋 Barcha kinolar"), KeyboardButton(text="📊 Kinolar statistikasi")],
            [KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True,
    )


def confirm_keyboard(yes: str, no: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=yes),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data=no),
        ]]
    )


def subscription_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for index, channel in enumerate(channels, start=1):
        link = channel.get("invite_link") or (f"https://t.me/{channel['channel_username'].lstrip('@')}" if channel.get("channel_username") else "")
        if link:
            rows.append([InlineKeyboardButton(text=f"📢 {index}-kanalga obuna bo‘lish", url=link)])
    rows.append([InlineKeyboardButton(text="✅ Obunani tekshirish", callback_data="subscription:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_list_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"➖ O‘chirish: {channel['channel_id']}", callback_data=f"channel:delete:{channel['id']}")]
        for channel in channels
    ] or [[InlineKeyboardButton(text="Ro‘yxat bo‘sh", callback_data="noop")]])


def movie_edit_keyboard(movie_id: int) -> InlineKeyboardMarkup:
    fields = [
        ("Kino kodi", "code"), ("Nomi", "title"), ("Tavsif", "description"),
        ("Video", "file"), ("Qo‘shimcha matn", "extra_text"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"movie:edit:{movie_id}:{field}")]
        for label, field in fields
    ])


def payment_methods_keyboard(methods: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=method, callback_data=f"payment:method:{index}")]
        for index, method in enumerate(methods)
    ])