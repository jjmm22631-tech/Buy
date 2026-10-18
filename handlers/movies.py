import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import Config
from database import Database
from handlers.common import can, deny_callback, deny_message, is_series_bot
from handlers.start import register_user, show_subscription_gate, subscription_status
from keyboards import (
    confirm_keyboard, movie_edit_keyboard, movie_menu, series_episodes_keyboard, series_seasons_keyboard,
)
from handlers.states import MovieAdd, MovieEdit, SeriesAdd, SeriesEpisodeAdd
from aiogram.fsm.context import FSMContext

router = Router(name="movies")
logger = logging.getLogger(__name__)


async def _send_movie(message: Message, movie: dict) -> None:
    caption_parts = []
    if movie.get("title"):
        caption_parts.append(f"🎬 {movie['title']}")
    if movie.get("description"):
        caption_parts.append(movie["description"])
    if movie.get("extra_text"):
        caption_parts.append(movie["extra_text"])
    caption = "\n\n".join(caption_parts)[:1024]
    kind = movie.get("file_type", "video")
    sender = {
        "video": message.answer_video,
        "document": message.answer_document,
        "animation": message.answer_animation,
        "audio": message.answer_audio,
        "photo": message.answer_photo,
    }.get(kind, message.answer_video)
    await sender(movie["file_id"], caption=caption or None)


async def _lookup_movie(message: Message, db: Database, code: str, bot: Bot, config: Config) -> None:
    user_row = await db.fetchone("SELECT id FROM users WHERE telegram_id=?", (message.from_user.id,))
    movie = await db.fetchone("SELECT * FROM movies WHERE code=? AND is_active=1", (code,))
    if movie is None and is_series_bot(bot, config):
        series = await db.fetchone("SELECT * FROM series WHERE code=? AND is_active=1", (code,))
        if series:
            seasons = await db.fetchall(
                "SELECT DISTINCT season_number FROM series_episodes WHERE series_id=? ORDER BY season_number",
                (series["id"],),
            )
            if seasons:
                request_id = await db.execute(
                    "INSERT INTO movie_requests(user_id,movie_code,found) VALUES(?,?,1)",
                    (user_row["id"], code),
                )
                await message.answer(
                    f"📺 {series['title']}\nBo‘limni tanlang:",
                    reply_markup=series_seasons_keyboard([dict(row) for row in seasons], request_id),
                )
                return
    request_id = await db.execute(
        "INSERT INTO movie_requests(user_id, movie_code, found) VALUES(?, ?, ?)",
        (user_row["id"], code, int(movie is not None)),
    )
    if movie is None:
        text = await db.get_setting("not_found_text", "❌ Bunday koddagi kino topilmadi.\n\nIltimos, kodni tekshirib qayta yuboring.")
        await message.answer(text)
        return
    try:
        movie_data = dict(movie)
        if not movie_data.get("extra_text"):
            movie_data["extra_text"] = await db.get_setting("advertisement_text", "")
        await _send_movie(message, movie_data)
        await db.execute("UPDATE movie_requests SET delivered=1 WHERE id=?", (request_id,))
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter) as error:
        logger.warning("Kino yuborilmadi: movie_id=%s error=%s", movie["id"], type(error).__name__)
        await message.answer("Kino yuborilmadi. Birozdan so‘ng qayta urinib ko‘ring.")


@router.message(F.text == "🔍 Kino qidirish")
async def search_prompt(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await can(db, message.from_user.id, "movies", config):
        await state.clear()
        await state.set_state(MovieEdit.code)
        await state.update_data(action="lookup")
        await message.answer("Kino kodi yoki ID raqamini yuboring:")
        return
    await message.answer("Kino kodini yuboring.")


@router.message(F.text == "ℹ️ Yordam")
async def help_handler(message: Message, db: Database) -> None:
    support = (await db.get_setting("support_username", "")).strip().lstrip("@")
    contact = f" Muammo bo‘lsa, @{support} ga murojaat qiling." if support else " Muammo bo‘lsa, bot administratoriga murojaat qiling."
    await message.answer("Kinoni topish uchun uning kodini yuboring." + contact)


@router.message(F.text == "📢 Kanalimiz")
async def channel_info(message: Message, db: Database) -> None:
    channels = await db.fetchall("SELECT channel_username, invite_link FROM channels WHERE is_active=1 ORDER BY id")
    links = [row["invite_link"] or (f"https://t.me/{row['channel_username'].lstrip('@')}" if row["channel_username"] else "") for row in channels]
    links = [link for link in links if link]
    await message.answer("📢 Kanalimiz:" + ("\n" + "\n".join(links) if links else "\nHozircha kanal havolasi sozlanmagan."))


@router.message(F.text == "🎬 Kinolar")
async def show_movie_menu(message: Message, db: Database, config: Config, bot: Bot) -> None:
    if await deny_message(message, db, "movies", config):
        return
    menu_text = "🎬 Kinolarni boshqarish"
    if is_series_bot(bot, config):
        menu_text += "\nSerial buyruqlari: /addseries, /addseriesepisode, /series"
    await message.answer(menu_text, reply_markup=movie_menu(hide_keyboard=is_series_bot(bot, config)))


@router.message(F.text == "🎬 Kino qo‘shish")
async def add_movie_start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        return
    await state.clear()
    await state.set_state(MovieAdd.code)
    await message.answer("Kino kodini yuboring:")


@router.message(MovieAdd.code)
async def add_movie_code(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        await state.clear()
        return
    code = (message.text or "").strip()
    if not code or len(code) > 64:
        await message.answer("Kod 1–64 belgidan iborat matn bo‘lishi kerak. Qayta kiriting:")
        return
    if await db.fetchone("SELECT id FROM movies WHERE code=?", (code,)):
        await message.answer("Bu kod band. Boshqa kod yuboring:")
        return
    await state.update_data(code=code)
    await state.set_state(MovieAdd.title)
    await message.answer("Kino nomini yuboring:")


@router.message(MovieAdd.title)
async def add_movie_title(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        await state.clear()
        return
    title = (message.text or "").strip()
    if not title or len(title) > 250:
        await message.answer("Kino nomi 1–250 belgidan iborat bo‘lsin. Qayta kiriting:")
        return
    await state.update_data(title=title)
    await state.set_state(MovieAdd.description)
    await message.answer("Tavsifni yuboring yoki /skip yozing:")


@router.message(MovieAdd.description)
async def add_movie_description(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        await state.clear()
        return
    description = "" if message.text == "/skip" else (message.text or "").strip()
    if len(description) > 3000:
        await message.answer("Tavsif 3000 belgidan oshmasin. Qayta kiriting:")
        return
    await state.update_data(description=description)
    await state.set_state(MovieAdd.media)
    await message.answer("Kinoning videosini yoki video faylini yuboring:")


def _media_details(message: Message) -> tuple[str, str] | None:
    if message.video:
        return message.video.file_id, "video"
    if message.document and (message.document.mime_type or "").startswith("video/"):
        return message.document.file_id, "document"
    if message.animation:
        return message.animation.file_id, "animation"
    if message.audio:
        return message.audio.file_id, "audio"
    if message.photo:
        return message.photo[-1].file_id, "photo"
    return None


@router.message(MovieAdd.media)
async def add_movie_media(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        await state.clear()
        return
    media = _media_details(message)
    if not media:
        await message.answer("Video yoki video fayl yuboring. Boshqa format hozircha qabul qilinmaydi:")
        return
    await state.update_data(file_id=media[0], file_type=media[1])
    await state.set_state(MovieAdd.extra_text)
    await message.answer("Qo‘shimcha matn yuboring yoki /skip yozing:")


@router.message(MovieAdd.extra_text)
async def add_movie_extra(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        await state.clear()
        return
    extra_text = "" if message.text == "/skip" else (message.text or "").strip()
    if len(extra_text) > 1000:
        await message.answer("Qo‘shimcha matn 1000 belgidan oshmasin. Qayta kiriting:")
        return
    data = await state.get_data()
    data["extra_text"] = extra_text
    await state.set_state(MovieAdd.confirm)
    await message.answer(
        f"Kino ma’lumotlari:\nKod: {data['code']}\nNomi: {data['title']}\nTavsif: {data['description'] or 'Yo‘q'}\nQo‘shimcha matn: {extra_text or 'Yo‘q'}",
        reply_markup=confirm_keyboard("movie:add:save"),
    )


@router.callback_query(F.data == "movie:add:save")
async def add_movie_save(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_callback(callback, db, "movies", config):
        return
    data = await state.get_data()
    if not data.get("file_id"):
        await callback.answer("Kino ma’lumotlari topilmadi. Jarayonni qayta boshlang.", show_alert=True)
        await state.clear()
        return
    try:
        await db.execute(
            "INSERT INTO movies(code,title,description,file_id,file_type,extra_text) VALUES(?,?,?,?,?,?)",
            (data["code"], data["title"], data["description"], data["file_id"], data["file_type"], data["extra_text"]),
        )
    except Exception as error:
        logger.warning("Kino saqlashda xato: %s", type(error).__name__)
        await callback.answer("Kino saqlanmadi. Kod band bo‘lishi mumkin.", show_alert=True)
        return
    await db.log_admin(callback.from_user.id, "movie_added", data["code"])
    await state.clear()
    await callback.message.edit_text(f"✅ Kino muvaffaqiyatli qo‘shildi!\n\nKod: {data['code']}\nNomi: {data['title']}")
    await callback.answer()


@router.message(Command("addseries"))
async def add_series_start(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config):
        await message.answer("Serial funksiyasi faqat ikkinchi botda mavjud.")
        return
    if await deny_message(message, db, "movies", config):
        return
    await state.clear()
    await state.set_state(SeriesAdd.code)
    await message.answer("Serial uchun yagona kodni yuboring:")


@router.message(SeriesAdd.code)
async def add_series_code(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    code = (message.text or "").strip()
    if not code or len(code) > 64:
        await message.answer("Kod 1–64 belgidan iborat bo‘lsin. Qayta yuboring:")
        return
    existing = await db.fetchone("SELECT code FROM movies WHERE code=? UNION ALL SELECT code FROM series WHERE code=? LIMIT 1", (code, code))
    if existing:
        await message.answer("Bu kod band. Boshqa kod yuboring:")
        return
    await state.update_data(code=code)
    await state.set_state(SeriesAdd.title)
    await message.answer("Serial nomini yuboring:")


@router.message(SeriesAdd.title)
async def add_series_title(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    title = (message.text or "").strip()
    if not title or len(title) > 250:
        await message.answer("Serial nomi 1–250 belgidan iborat bo‘lsin. Qayta yuboring:")
        return
    await state.update_data(title=title)
    await state.set_state(SeriesAdd.description)
    await message.answer("Serial tavsifini yuboring yoki /skip yozing:")


@router.message(SeriesAdd.description)
async def add_series_description(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    description = "" if message.text == "/skip" else (message.text or "").strip()
    if len(description) > 3000:
        await message.answer("Tavsif 3000 belgidan oshmasin. Qayta kiriting:")
        return
    await state.update_data(description=description, episodes=[])
    await state.set_state(SeriesAdd.episodes)
    await message.answer("Har bir qism uchun /part <bo‘lim> <qism> yuboring, keyin video yuboring. Tugatgach /done yozing:")


@router.message(SeriesAdd.episodes, Command("part"))
async def set_new_series_episode_numbers(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit() or int(parts[1]) < 1 or int(parts[2]) < 1:
        await message.answer("Format: /part <bo‘lim_raqami> <qism_raqami>, masalan /part 1 1")
        return
    season_number, episode_number = int(parts[1]), int(parts[2])
    data = await state.get_data()
    if any(
        episode["season_number"] == season_number and episode["episode_number"] == episode_number
        for episode in data.get("episodes", [])
    ):
        await message.answer("Bu bo‘lim va qism raqami kiritilgan. Boshqa raqamni kiriting:")
        return
    await state.update_data(pending_season=season_number, pending_episode=episode_number)
    await message.answer(f"{season_number}-bo‘lim {episode_number}-qism. Endi video faylini yuboring:")


@router.message(SeriesAdd.episodes, Command("done"))
async def finish_series_add(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    if not episodes:
        await message.answer("Serialni saqlash uchun kamida bitta qism yuboring:")
        return
    if data.get("pending_season"):
        await message.answer("Tanlangan qism videosi hali yuborilmadi. Videoni yuboring yoki /part bilan boshqa qism tanlang:")
        return
    try:
        series_id = await db.create_series(data["code"], data["title"], data["description"], episodes)
    except ValueError as error:
        await message.answer(f"Serial saqlanmadi: {error}")
        await state.clear()
        return
    except Exception as error:
        logger.warning("Serial saqlanmadi: %s", type(error).__name__)
        await message.answer("Serial saqlanmadi. Kod band bo‘lishi mumkin.")
        await state.clear()
        return
    await db.log_admin(message.from_user.id, "series_added", f"series_id={series_id} code={data['code']} episodes={len(episodes)}")
    await state.clear()
    await message.answer(f"✅ Serial qo‘shildi: {data['title']}\nKod: {data['code']}\nQismlar: {len(episodes)}")


@router.message(SeriesAdd.episodes)
async def collect_series_episode(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    data = await state.get_data()
    episodes = data.get("episodes", [])
    if len(episodes) >= 100:
        await message.answer("Bitta serialga 100 tagacha qism qo‘shish mumkin. Saqlash uchun /done yozing:")
        return
    media = _media_details(message)
    if not media:
        await message.answer("Avval /part <bo‘lim> <qism> kiriting, keyin qism videosini yuboring; yakunlash uchun /done:")
        return
    season_number = data.get("pending_season")
    episode_number = data.get("pending_episode")
    if not season_number or not episode_number:
        await message.answer("Videodan oldin /part <bo‘lim> <qism> kiriting, masalan /part 1 1:")
        return
    episodes.append({
        "season_number": season_number,
        "episode_number": episode_number,
        "file_id": media[0],
        "file_type": media[1],
    })
    await state.update_data(episodes=episodes)
    await state.update_data(pending_season=None, pending_episode=None)
    await message.answer(f"✅ {season_number}-bo‘lim {episode_number}-qism qabul qilindi. Keyingi qismga /part kiriting yoki /done:")


@router.message(Command("addseriesepisode"))
async def add_series_episode_start(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config):
        await message.answer("Serial funksiyasi faqat ikkinchi botda mavjud.")
        return
    if await deny_message(message, db, "movies", config):
        return
    await state.clear()
    await state.set_state(SeriesEpisodeAdd.code)
    await message.answer("Qism qo‘shiladigan serial kodini yuboring:")


@router.message(SeriesEpisodeAdd.code)
async def select_series_for_episode(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    code = (message.text or "").strip()
    series = await db.fetchone("SELECT id,title FROM series WHERE code=? AND is_active=1", (code,))
    if not series:
        await message.answer("Faol serial topilmadi. Kodni qayta yuboring:")
        return
    await state.update_data(series_id=series["id"], series_title=series["title"], added_count=0)
    await state.set_state(SeriesEpisodeAdd.episodes)
    await message.answer(f"{series['title']} uchun har bir qism oldidan /part <bo‘lim> <qism> yuboring, so‘ng video yuboring. Tugatgach /done:")


@router.message(SeriesEpisodeAdd.episodes, Command("part"))
async def set_existing_series_episode_numbers(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit() or int(parts[1]) < 1 or int(parts[2]) < 1:
        await message.answer("Format: /part <bo‘lim_raqami> <qism_raqami>, masalan /part 1 1")
        return
    season_number, episode_number = int(parts[1]), int(parts[2])
    await state.update_data(pending_season=season_number, pending_episode=episode_number)
    await message.answer(f"{season_number}-bo‘lim {episode_number}-qism. Endi video faylini yuboring:")


@router.message(SeriesEpisodeAdd.episodes, Command("done"))
async def finish_series_episode_add(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    data = await state.get_data()
    if not data.get("added_count"):
        await message.answer("Hali qism yuborilmadi. Qism yuboring yoki /cancel bilan bekor qiling:")
        return
    if data.get("pending_season"):
        await message.answer("Tanlangan qism videosi hali yuborilmadi. Videoni yuboring yoki /part bilan boshqasini tanlang:")
        return
    await state.clear()
    await message.answer(f"✅ {data['series_title']} serialiga {data['added_count']} ta qism qo‘shildi.")


@router.message(SeriesEpisodeAdd.episodes)
async def collect_existing_series_episode(message: Message, state: FSMContext, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config) or await deny_message(message, db, "movies", config):
        await state.clear()
        return
    media = _media_details(message)
    if not media:
        await message.answer("Avval /part <bo‘lim> <qism> kiriting, keyin qism videosini yuboring; yakunlash uchun /done:")
        return
    data = await state.get_data()
    season_number = data.get("pending_season")
    episode_number = data.get("pending_episode")
    if not season_number or not episode_number:
        await message.answer("Videodan oldin /part <bo‘lim> <qism> kiriting, masalan /part 1 1:")
        return
    try:
        await db.add_series_episode(data["series_id"], season_number, episode_number, media[0], media[1])
    except ValueError as error:
        await message.answer(f"Qism qo‘shilmadi: {error}")
        return
    await db.log_admin(message.from_user.id, "series_episode_added", f"series_id={data['series_id']} season={season_number} episode={episode_number}")
    added_count = data.get("added_count", 0) + 1
    await state.update_data(added_count=added_count, pending_season=None, pending_episode=None)
    await message.answer(f"✅ {season_number}-bo‘lim {episode_number}-qism qo‘shildi. Keyingisiga /part kiriting yoki /done:")


@router.message(Command("series"))
async def list_series(message: Message, db: Database, config: Config, bot: Bot) -> None:
    if not is_series_bot(bot, config):
        await message.answer("Serial funksiyasi faqat ikkinchi botda mavjud.")
        return
    if await deny_message(message, db, "movies", config):
        return
    rows = await db.fetchall(
        "SELECT s.code,s.title,COUNT(e.id) AS episode_count FROM series s "
        "LEFT JOIN series_episodes e ON e.series_id=s.id GROUP BY s.id ORDER BY s.id DESC"
    )
    if not rows:
        await message.answer("Hozircha serial qo‘shilmagan.")
        return
    await message.answer("📺 Seriallar:\n" + "\n".join(
        f"{row['code']} — {row['title']} ({row['episode_count']} qism)" for row in rows
    ))


@router.message(F.text == "✏️ Kinoni tahrirlash")
async def edit_movie_start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        return
    await state.clear()
    await state.set_state(MovieEdit.code)
    await message.answer("Tahrirlanadigan kinoning kodi yoki bazadagi ID raqamini yuboring:")


@router.message(MovieEdit.code)
async def edit_movie_select(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        await state.clear()
        return
    key = (message.text or "").strip()
    movie = await db.fetchone("SELECT * FROM movies WHERE code=? OR CAST(id AS TEXT)=?", (key, key))
    if not movie:
        await message.answer("Kino topilmadi. Kod yoki ID ni qayta yuboring:")
        return
    data = await state.get_data()
    if data.get("action") == "delete":
        await state.update_data(movie_id=movie["id"])
        await state.set_state(None)
        await message.answer(f"🗑 {movie['title']} (kod: {movie['code']}) kinoni o‘chirishni tasdiqlaysizmi?", reply_markup=confirm_keyboard(f"movie:delete:{movie['id']}"))
        return
    if data.get("action") == "lookup":
        await state.clear()
        await message.answer(f"ID: {movie['id']}\nKod: {movie['code']}\nNomi: {movie['title']}\nTavsif: {movie['description'] or 'Yo‘q'}\nHolati: {'Faol' if movie['is_active'] else 'O‘chirilgan'}")
        return
    await state.update_data(movie_id=movie["id"])
    await state.set_state(None)
    await message.answer(f"🎬 {movie['title']} (kod: {movie['code']})\nO‘zgartiriladigan maydonni tanlang:", reply_markup=movie_edit_keyboard(movie["id"]))


@router.callback_query(F.data.startswith("movie:edit:"))
async def edit_movie_field(callback: CallbackQuery, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_callback(callback, db, "movies", config):
        return
    parts = callback.data.split(":")
    if len(parts) != 4 or not parts[2].isdigit() or parts[3] not in {"code", "title", "description", "file", "extra_text"}:
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return
    movie_id, field = int(parts[2]), parts[3]
    if not await db.fetchone("SELECT id FROM movies WHERE id=?", (movie_id,)):
        await callback.answer("Kino topilmadi.", show_alert=True)
        return
    await state.clear()
    await state.update_data(movie_id=movie_id, field=field)
    await state.set_state(MovieEdit.value)
    await callback.message.answer("Yangi qiymatni yuboring:" if field != "file" else "Yangi video yoki video faylni yuboring:")
    await callback.answer()


@router.message(MovieEdit.value)
async def edit_movie_value(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        await state.clear()
        return
    data = await state.get_data()
    field = data.get("field")
    if field == "file":
        media = _media_details(message)
        if not media:
            await message.answer("Video yoki video fayl yuboring:")
            return
        column_values = (media[0], media[1])
        await db.execute("UPDATE movies SET file_id=?, file_type=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (*column_values, data["movie_id"]))
    else:
        value = (message.text or "").strip()
        if not value or len(value) > 3000:
            await message.answer("Matn bo‘sh bo‘lmasin va 3000 belgidan oshmasin. Qayta yuboring:")
            return
        if field == "code" and await db.fetchone("SELECT id FROM movies WHERE code=? AND id<>?", (value, data["movie_id"])):
            await message.answer("Bu kod band. Boshqa kod kiriting:")
            return
        if field not in {"code", "title", "description", "extra_text"}:
            await state.clear()
            return
        await db.execute(f"UPDATE movies SET {field}=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (value, data["movie_id"]))
    await db.log_admin(message.from_user.id, "movie_updated", f"movie_id={data['movie_id']} field={field}")
    await state.clear()
    await message.answer("✅ Kino ma’lumoti yangilandi.")


@router.message(F.text == "🗑 Kinoni o‘chirish")
async def delete_movie_start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        return
    await state.clear()
    await state.set_state(MovieEdit.code)
    await state.update_data(action="delete")
    await message.answer("O‘chiriladigan kinoning kodini yoki ID raqamini yuboring:")


@router.callback_query(F.data.startswith("movie:delete:"))
async def delete_movie_confirm(callback: CallbackQuery, db: Database, config: Config) -> None:
    if await deny_callback(callback, db, "movies", config):
        return
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return
    movie_id = int(parts[2])
    movie = await db.fetchone("SELECT code FROM movies WHERE id=?", (movie_id,))
    if not movie:
        await callback.answer("Kino topilmadi yoki oldin o‘chirilgan.", show_alert=True)
        return
    await db.execute("DELETE FROM movies WHERE id=?", (movie_id,))
    await db.log_admin(callback.from_user.id, "movie_deleted", f"movie_id={movie_id} code={movie['code']}")
    await callback.message.edit_text("✅ 🗑 Kino o‘chirildi.")
    await callback.answer()


@router.message(F.text == "📋 Barcha kinolar")
async def list_movies(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "movies", config):
        return
    movies = await db.fetchall("SELECT id, code, title FROM movies ORDER BY id DESC LIMIT 100")
    if not movies:
        await message.answer("Hozircha kino qo‘shilmagan.")
        return
    lines = [f"{movie['id']}. {movie['code']} — {movie['title']}" for movie in movies]
    for offset in range(0, len(lines), 40):
        await message.answer("📋 Kinolar:\n" + "\n".join(lines[offset:offset + 40]))


@router.message(F.text == "📊 Kinolar statistikasi")
async def movie_stats(message: Message, db: Database, config: Config) -> None:
    if await deny_message(message, db, "stats", config):
        return
    row = await db.fetchone("SELECT COUNT(*) AS total, SUM(date(created_at)=date('now')) AS today FROM movies")
    await message.answer(f"📊 Jami kinolar: {row['total']}\nBugun qo‘shilgan: {row['today'] or 0}")


@router.callback_query(F.data.startswith("series:season:"))
async def show_series_season_episodes(callback: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    if not is_series_bot(bot, config):
        await callback.answer("Serial funksiyasi faqat ikkinchi botda mavjud.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return
    request = await db.fetchone(
        "SELECT r.id,r.movie_code FROM movie_requests r JOIN users u ON u.id=r.user_id "
        "WHERE r.id=? AND u.telegram_id=? AND r.found=1",
        (int(parts[2]), callback.from_user.id),
    )
    if not request:
        await callback.answer("Bu so‘rov topilmadi. Serial kodini qayta yuboring.", show_alert=True)
        return
    series = await db.fetchone(
        "SELECT id,title FROM series WHERE code=? AND is_active=1",
        (request["movie_code"],),
    )
    season_number = int(parts[3])
    if not series:
        await callback.answer("Serial topilmadi.", show_alert=True)
        return
    episodes = await db.fetchall(
        "SELECT id,episode_number FROM series_episodes WHERE series_id=? AND season_number=? ORDER BY episode_number",
        (series["id"], season_number),
    )
    if not episodes:
        await callback.answer("Bu bo‘limda qismlar topilmadi.", show_alert=True)
        return
    await callback.message.edit_text(
        f"📺 {series['title']}\n{season_number}-bo‘limdan qismni tanlang:",
        reply_markup=series_episodes_keyboard([dict(row) for row in episodes], request["id"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("series:episode:"))
async def send_series_episode(callback: CallbackQuery, bot: Bot, db: Database, config: Config) -> None:
    if not is_series_bot(bot, config):
        await callback.answer("Bu qism faqat ikkinchi botda mavjud.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Noto‘g‘ri so‘rov.", show_alert=True)
        return
    request = await db.fetchone(
        "SELECT r.id,r.movie_code FROM movie_requests r JOIN users u ON u.id=r.user_id "
        "WHERE r.id=? AND u.telegram_id=? AND r.found=1",
        (int(parts[2]), callback.from_user.id),
    )
    if not request:
        await callback.answer("Bu so‘rov topilmadi. Serial kodini qayta yuboring.", show_alert=True)
        return
    episode = await db.fetchone(
        "SELECT e.id,e.season_number,e.episode_number,e.file_id,e.file_type,s.code,s.title,s.description,s.extra_text "
        "FROM series_episodes e JOIN series s ON s.id=e.series_id "
        "WHERE e.id=? AND s.is_active=1",
        (int(parts[3]),),
    )
    if not episode or episode["code"] != request["movie_code"]:
        await callback.answer("Serial qismi topilmadi.", show_alert=True)
        return
    allowed, channels = await subscription_status(bot, db, callback.from_user.id)
    if not allowed:
        await callback.answer("Avval kanallarga obuna bo‘ling.", show_alert=True)
        await show_subscription_gate(callback.message, channels, db)
        return
    movie_data = dict(episode)
    movie_data["title"] = f"{episode['title']} | {episode['season_number']}-bo‘lim {episode['episode_number']}-qism"
    if not movie_data.get("extra_text"):
        movie_data["extra_text"] = await db.get_setting("advertisement_text", "")
    try:
        await _send_movie(callback.message, movie_data)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter) as error:
        logger.warning("Serial qismi yuborilmadi: episode_id=%s error=%s", episode["id"], type(error).__name__)
        await callback.answer("Qism yuborilmadi. Keyinroq qayta urinib ko‘ring.", show_alert=True)
        return
    await db.execute("UPDATE movie_requests SET delivered=1 WHERE id=?", (request["id"],))
    await callback.answer("✅ Qism yuborildi.")


@router.message(F.text.regexp(r"^[^\s/]{1,64}$"))
async def movie_code_handler(message: Message, bot: Bot, db: Database, config: Config) -> None:
    await register_user(message, db)
    user = await db.fetchone("SELECT is_blocked FROM users WHERE telegram_id=?", (message.from_user.id,))
    if user and user["is_blocked"]:
        await message.answer("🚫 Botdan foydalanishingiz cheklangan.")
        return
    allowed, channels = await subscription_status(bot, db, message.from_user.id)
    if not allowed:
        await show_subscription_gate(message, channels, db)
        return
    await _lookup_movie(message, db, (message.text or "").strip(), bot, config)


@router.message(F.text)
async def unmatched_text_handler(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id not in config.admin_ids:
        await message.answer("Kino kodini matn ko‘rinishida yuboring.")


@router.message()
async def non_text_handler(message: Message, db: Database, config: Config) -> None:
    if message.from_user.id not in config.admin_ids:
        await message.answer("Kino kodini matn ko‘rinishida yuboring.")