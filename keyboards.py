from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def inline_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    style: Literal["primary", "success", "danger"] = "success",
) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data, url=url, style=style)


def main_menu(
    is_admin: bool,
    payments_enabled: bool = False,
    hide_keyboard: bool = False,
) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if hide_keyboard:
        return ReplyKeyboardRemove()
    rows = []
    if payments_enabled:
        rows.append([KeyboardButton(text="💳 To‘lov")])
    if is_admin:
        rows.append([KeyboardButton(text="🛠 Admin paneli")])
    if not rows:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def admin_menu(hide_keyboard: bool = False) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if hide_keyboard:
        return ReplyKeyboardRemove()
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


def movie_menu(hide_keyboard: bool = False) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if hide_keyboard:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Kino qo‘shish"), KeyboardButton(text="✏️ Kinoni tahrirlash")],
            [KeyboardButton(text="🗑 Kinoni o‘chirish"), KeyboardButton(text="🔍 Kino qidirish")],
            [KeyboardButton(text="📋 Barcha kinolar"), KeyboardButton(text="📊 Kinolar statistikasi")],
            [KeyboardButton(text="📺 Serial qo‘shish"), KeyboardButton(text="➕ Mavsum/qism qo‘shish")],
            [KeyboardButton(text="🗑 Serial qismini o‘chirish"), KeyboardButton(text="📋 Seriallar")],
            [KeyboardButton(text="🔙 Orqaga")],
        ],
        resize_keyboard=True,
    )


def series_seasons_keyboard(
    seasons: list[dict],
    request_id: int,
    series_id: int | None = None,
    is_favorite: bool = False,
    subscribed: bool = False,
) -> InlineKeyboardMarkup:
    rows = [
        [inline_button(text=f"📁 {season['season_number']}-mavsum", callback_data=f"series:season:{request_id}:{season['season_number']}")]
        for season in seasons
    ]
    if series_id is not None:
        rows.append([
            inline_button(
                text="⭐ Sevimlidan olib tashlash" if is_favorite else "⭐ Sevimlilarga qo‘shish",
                callback_data=f"series:favorite:{request_id}:{series_id}",
            ),
            inline_button(
                text="🔕 Bildirishnomani o‘chirish" if subscribed else "🔔 Yangi qismlarga obuna",
                callback_data=f"series:subscribe:{request_id}:{series_id}",
            ),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def series_episodes_keyboard(episodes: list[dict], request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text=f"▶️ {episode['episode_number']}-qism", callback_data=f"series:episode:{request_id}:{episode['id']}")]
        for episode in episodes
    ])


def title_search_keyboard(results: list[dict], request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(
            text=f"{'📺' if result['kind'] == 'series' else '🎬'} {result['title'][:50]}",
            callback_data=f"search:{result['kind']}:{request_id}:{result['id']}",
        )]
        for result in results
    ])


def series_delete_episodes_keyboard(episodes: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(
            text=f"🗑 {episode['season_number']}-mavsum {episode['episode_number']}-qism",
            callback_data=f"series:deleteepisode:{episode['id']}",
            style="danger",
        )]
        for episode in episodes
    ])


def series_library_keyboard(series: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(
            text=f"📺 {item['title'][:50]}",
            callback_data=f"library:open:{item['id']}",
        )]
        for item in series
    ])


def personal_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text="⭐ Sevimlilarim", callback_data="library:favorites")],
        [inline_button(text="🔔 Obunalarim", callback_data="library:subscriptions")],
        [inline_button(text="🔍 Kino yoki serial qidirish", callback_data="library:search")],
    ])


def cancel_menu(hide_keyboard: bool = False) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if hide_keyboard:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True,
    )


def confirm_keyboard(yes: str, no: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            inline_button(text="✅ Tasdiqlash", callback_data=yes),
            inline_button(text="❌ Bekor qilish", callback_data=no, style="danger"),
        ]]
    )


def subscription_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for index, channel in enumerate(channels, start=1):
        link = channel.get("invite_link") or (f"https://t.me/{channel['channel_username'].lstrip('@')}" if channel.get("channel_username") else "")
        if link:
            label = "kanal" if channel.get("chat_type", "channel") == "channel" else "guruh"
            icon = "📢" if label == "kanal" else "👥"
            rows.append([inline_button(text=f"{icon} {index}-{label}ga obuna bo‘lish", url=link)])
    rows.append([inline_button(text="✅ Obunani tekshirish", callback_data="subscription:check")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def access_invite_keyboard(invite_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text="✅ Guruhga so‘rov yuborish", url=invite_link)],
    ])


def channel_management_keyboard(
    channels: list[dict],
    enabled: bool,
) -> InlineKeyboardMarkup:
    rows = [
        [inline_button(
            text=f"🗑 {'📢' if channel.get('chat_type', 'channel') == 'channel' else '👥'} "
            f"{(channel.get('title') or channel.get('channel_username') or channel['channel_id'])[:40]}",
            callback_data=f"channel:delete:{channel['id']}",
            style="danger",
        )]
        for channel in channels[:40]
    ]
    if not channels:
        rows.append([inline_button(text="Ro‘yxat bo‘sh", callback_data="noop")])
    rows.extend([
        [
            inline_button(text="➕ Kanal qo‘shish", callback_data="channel:add:channel"),
            inline_button(text="➕ Guruh qo‘shish", callback_data="channel:add:group"),
        ],
        [inline_button(
            text=f"Majburiy obunani {'o‘chirish' if enabled else 'yoqish'}",
            callback_data="channel:toggle",
        )],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def movie_edit_keyboard(movie_id: int) -> InlineKeyboardMarkup:
    fields = [
        ("Kino kodi", "code"), ("Nomi", "title"), ("Tavsif", "description"),
        ("Video", "file"), ("Qo‘shimcha matn", "extra_text"),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text=label, callback_data=f"movie:edit:{movie_id}:{field}")]
        for label, field in fields
    ])


def payment_methods_keyboard(methods: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text=method, callback_data=f"payment:method:{index}")]
        for index, method in enumerate(methods)
    ])