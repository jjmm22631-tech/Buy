from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove


def inline_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    style: Literal["primary", "success", "danger"] = "primary",
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
            inline_button(text="✅ Tasdiqlash", callback_data=yes, style="success"),
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
            action = "obuna bo‘lish" if label == "kanal" else "qo‘shilish"
            rows.append([inline_button(text=f"{icon} {index}-{label}ga {action}", url=link, style="success")])
    rows.append([inline_button(text="✅ Obunani tekshirish", callback_data="subscription:check", style="success")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def access_invite_keyboard(invite_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text="✅ Guruhga so‘rov yuborish", url=invite_link, style="success")],
    ])


def channel_management_keyboard(
    enabled: bool,
    channel_count: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text="➕ Kanal/guruh qo‘shish", callback_data="channel:add", style="success")],
        [inline_button(text=f"📋 Ulangan kanallar/guruhlar ({channel_count})", callback_data="channels:list:0")],
        [inline_button(text="🗑 Kanal/guruhni o‘chirish", callback_data="channels:list:0")],
        [inline_button(text="🔄 Obunani tekshirish", callback_data="channels:check", style="success")],
        [inline_button(
            text=f"Majburiy obunani {'o‘chirish' if enabled else 'yoqish'}",
            callback_data="channel:toggle",
            style="danger" if enabled else "success",
        )],
        [inline_button(text="🔙 Orqaga", callback_data="channels:back", style="primary")],
    ])


def channel_add_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            inline_button(text="📢 Ommaviy kanal", callback_data="channel:add:public:channel"),
            inline_button(text="👥 Ommaviy guruh", callback_data="channel:add:public:group"),
        ],
        [inline_button(text="🔒 Yopiq kanal/guruh", callback_data="channel:add:private")],
        [inline_button(text="🔙 Orqaga", callback_data="channels:menu", style="primary")],
    ])


def private_chat_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            inline_button(text="📢 Yopiq kanal", callback_data="channel:add:private:channel"),
            inline_button(text="👥 Yopiq guruh", callback_data="channel:add:private:group"),
        ],
        [inline_button(text="🔙 Orqaga", callback_data="channel:add", style="primary")],
    ])


def channel_list_keyboard(channels: list[dict], page: int, total: int) -> InlineKeyboardMarkup:
    page_size = 20
    rows = [
        [inline_button(
            text=f"🗑 {(channel.get('title') or channel.get('channel_username') or channel['channel_id'])[:45]}",
            callback_data=f"channel:remove:{channel['id']}:{page}",
            style="danger",
        )]
        for channel in channels
    ]
    navigation = []
    if page > 0:
        navigation.append(inline_button(text="⬅️ Oldingi", callback_data=f"channels:list:{page - 1}"))
    if (page + 1) * page_size < total:
        navigation.append(inline_button(text="Keyingi ➡️", callback_data=f"channels:list:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([inline_button(text="🔙 Obuna menyusi", callback_data="channels:menu", style="primary")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def empty_subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [inline_button(text="✅ Obunani tekshirish", callback_data="subscription:check")],
    ])


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