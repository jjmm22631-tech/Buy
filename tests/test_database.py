import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from config import Config, _load_env_file
from database import Database
from handlers.admin import (
    create_access_link,
    channel_list_view,
    private_chat_invite_link,
    public_chat_username,
    save_linked_channel_or_group,
)
from handlers.common import can
from handlers.movies import _notify_episode_subscribers, is_series_bot
from handlers.start import (
    DEFAULT_SUBSCRIPTION,
    chat_join_request_handler,
    start_handler,
    subscription_check,
    subscription_status,
)
from keyboards import (
    admin_menu, cancel_menu, channel_add_type_keyboard, channel_management_keyboard, confirm_keyboard,
    main_menu, movie_menu, private_chat_type_keyboard, series_delete_episodes_keyboard,
    series_episodes_keyboard, series_seasons_keyboard, subscription_keyboard, title_search_keyboard,
)
from aiogram.types import ReplyKeyboardRemove
from types import SimpleNamespace
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SetMyCommands
from telegram_commands import admin_commands, set_admin_commands


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.temp_dir.name) / "bot.sqlite3"))
        await self.db.connect()

    async def asyncTearDown(self) -> None:
        await self.db.close()
        self.temp_dir.cleanup()

    async def test_user_movie_request_and_setting_are_persistent(self) -> None:
        await self.db.execute(
            "INSERT INTO users(telegram_id,full_name) VALUES(?,?) ON CONFLICT(telegram_id) DO NOTHING",
            (1001, "Test User"),
        )
        await self.db.execute(
            "INSERT INTO users(telegram_id,full_name) VALUES(?,?) ON CONFLICT(telegram_id) DO UPDATE SET full_name=excluded.full_name",
            (1001, "Updated User"),
        )
        user = await self.db.fetchone("SELECT * FROM users WHERE telegram_id=?", (1001,))
        self.assertEqual(user["full_name"], "Updated User")

        await self.db.execute(
            "INSERT INTO movies(code,title,file_id) VALUES(?,?,?)",
            ("A1", "Test Kino", "telegram-file-id"),
        )
        movie = await self.db.fetchone("SELECT * FROM movies WHERE code=? AND is_active=1", ("A1",))
        self.assertEqual(movie["file_id"], "telegram-file-id")
        await self.db.execute(
            "INSERT INTO movie_requests(user_id,movie_code,found) VALUES(?,?,?)",
            (user["id"], "A1", 1),
        )
        await self.db.set_setting("welcome_text", "Salom")
        self.assertEqual(await self.db.get_setting("welcome_text"), "Salom")
        requests = await self.db.fetchone("SELECT COUNT(*) AS total FROM movie_requests")
        self.assertEqual(requests["total"], 1)

    async def test_series_episodes_use_season_and_episode_numbers(self) -> None:
        series_id = await self.db.create_series(
            "SER1",
            "Sinov serial",
            "Tavsif",
            [
                {"season_number": 1, "episode_number": 1, "file_id": "season-1-episode-1", "file_type": "video"},
                {"season_number": 2, "episode_number": 1, "file_id": "season-2-episode-1", "file_type": "video"},
            ],
        )
        await self.db.add_series_episode(series_id, 1, 2, "season-1-episode-2", "document")
        episodes = await self.db.fetchall(
            "SELECT season_number,episode_number,file_id,file_type FROM series_episodes "
            "WHERE series_id=? ORDER BY season_number,episode_number",
            (series_id,),
        )

        self.assertEqual(
            [(row["season_number"], row["episode_number"]) for row in episodes],
            [(1, 1), (1, 2), (2, 1)],
        )
        self.assertEqual(episodes[1]["file_id"], "season-1-episode-2")
        self.assertEqual(episodes[1]["file_type"], "document")
        with self.assertRaises(ValueError):
            await self.db.add_series_episode(series_id, 1, 2, "duplicate", "video")

        await self.db.execute("DELETE FROM series WHERE id=?", (series_id,))
        remaining = await self.db.fetchone("SELECT COUNT(*) AS total FROM series_episodes WHERE series_id=?", (series_id,))
        self.assertEqual(remaining["total"], 0)

    async def test_series_favorites_and_subscriptions_are_saved_per_user(self) -> None:
        series_id = await self.db.create_series(
            "FAV1",
            "Sevimli serial",
            "",
            [{"season_number": 1, "episode_number": 1, "file_id": "ep1", "file_type": "video"}],
        )
        user_id = await self.db.execute(
            "INSERT INTO users(telegram_id,full_name) VALUES(?,?)",
            (1002, "Viewer"),
        )
        await self.db.execute(
            "INSERT INTO series_favorites(user_id,series_id) VALUES(?,?)",
            (user_id, series_id),
        )
        await self.db.execute(
            "INSERT INTO series_subscriptions(user_id,series_id,bot_id) VALUES(?,?,?)",
            (user_id, series_id, 777),
        )

        favorite = await self.db.fetchone(
            "SELECT series_id FROM series_favorites WHERE user_id=?",
            (user_id,),
        )
        subscription = await self.db.fetchone(
            "SELECT series_id,bot_id FROM series_subscriptions WHERE user_id=?",
            (user_id,),
        )
        self.assertEqual(favorite["series_id"], series_id)
        self.assertEqual((subscription["series_id"], subscription["bot_id"]), (series_id, 777))

        sender = AsyncMock()
        await _notify_episode_subscribers(
            self.db,
            series_id,
            "Sevimli serial",
            2,
            1,
            AsyncMock(),
            {777: sender},
        )
        sender.send_message.assert_awaited_once_with(
            1002,
            "🔔 Yangi qism chiqdi!\nSevimli serial\n2-mavsum 1-qism",
        )

    async def test_legacy_series_episodes_migrate_to_first_season(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        with sqlite3.connect(legacy_path) as connection:
            connection.executescript(
                "CREATE TABLE series (id INTEGER PRIMARY KEY, code TEXT UNIQUE, title TEXT, description TEXT, "
                "extra_text TEXT DEFAULT '', is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, "
                "updated_at TEXT DEFAULT CURRENT_TIMESTAMP);"
                "CREATE TABLE series_episodes (id INTEGER PRIMARY KEY AUTOINCREMENT, series_id INTEGER NOT NULL, "
                "episode_number INTEGER NOT NULL, file_id TEXT NOT NULL, file_type TEXT DEFAULT 'video', "
                "created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(series_id, episode_number));"
                "INSERT INTO series(id,code,title) VALUES(1,'OLD','Old series');"
                "INSERT INTO series_episodes(id,series_id,episode_number,file_id,file_type) "
                "VALUES(5,1,3,'legacy-file','document');"
            )
        legacy_db = Database(str(legacy_path))
        await legacy_db.connect()
        episode = await legacy_db.fetchone("SELECT * FROM series_episodes WHERE id=5")
        await legacy_db.close()

        self.assertEqual(episode["season_number"], 1)
        self.assertEqual(episode["episode_number"], 3)
        self.assertEqual(episode["file_id"], "legacy-file")

    async def test_channel_table_migrates_with_chat_type_and_title(self) -> None:
        columns = {
            row["name"]
            for row in await self.db.fetchall("PRAGMA table_info(channels)")
        }
        self.assertIn("chat_type", columns)
        self.assertIn("title", columns)
        bot_columns = {
            row["name"]
            for row in await self.db.fetchall("PRAGMA table_info(bot_channels)")
        }
        self.assertIn("bot_id", bot_columns)

    async def test_legacy_channels_migrate_to_primary_bot_only(self) -> None:
        await self.db.execute(
            "INSERT INTO channels(channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?)",
            (-100123, "legacy_channel", "https://t.me/legacy_channel", "channel", "Legacy"),
        )

        await self.db.migrate_legacy_channels(1001)
        await self.db.initialize_bot_subscription_settings(1001, inherit_legacy=True)
        await self.db.initialize_bot_subscription_settings(2002, inherit_legacy=False)

        migrated = await self.db.fetchall("SELECT bot_id,channel_id FROM bot_channels")
        self.assertEqual([(row["bot_id"], row["channel_id"]) for row in migrated], [(1001, -100123)])
        await self.db.set_bot_setting("subscription_enabled", 1001, "0")
        self.assertEqual(await self.db.get_bot_setting("subscription_enabled", 1001, "1"), "0")
        self.assertEqual(await self.db.get_bot_setting("subscription_enabled", 2002, "1"), "1")

    async def test_legacy_channels_migrate_without_losing_rows(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy_channels.sqlite3"
        with sqlite3.connect(legacy_path) as connection:
            connection.executescript(
                "CREATE TABLE channels (id INTEGER PRIMARY KEY, channel_id INTEGER UNIQUE, "
                "channel_username TEXT, invite_link TEXT NOT NULL, is_active INTEGER DEFAULT 1);"
                "INSERT INTO channels(id,channel_id,channel_username,invite_link) "
                "VALUES(1,-100123,'old_channel','https://t.me/old_channel');"
            )
        legacy_db = Database(str(legacy_path))
        await legacy_db.connect()
        row = await legacy_db.fetchone("SELECT * FROM channels WHERE id=1")
        await legacy_db.close()

        self.assertEqual(row["chat_type"], "channel")
        self.assertEqual(row["title"], "")
        self.assertEqual(row["channel_username"], "old_channel")

    async def test_admin_permissions_and_audit_log(self) -> None:
        await self.db.add_admin(2002, "admin", ["movies"], 1001)
        admin = await self.db.get_admin(2002)
        self.assertEqual(admin["permissions"], ["movies"])
        await self.db.log_admin(1001, "admin_added", "2002")
        log = await self.db.fetchone("SELECT * FROM admin_logs WHERE admin_id=?", (1001,))
        self.assertEqual(log["action"], "admin_added")

    async def test_bot_access_requires_real_join_request_for_configured_group(self) -> None:
        config = Config("token", ("token",), 1001, (1001,), "db.sqlite3", "INFO", -100123)
        valid_request = SimpleNamespace(
            chat=SimpleNamespace(id=-100123),
            from_user=SimpleNamespace(id=2002),
            invite_link=SimpleNamespace(creates_join_request=True),
        )
        wrong_group_request = SimpleNamespace(
            chat=SimpleNamespace(id=-100999),
            from_user=SimpleNamespace(id=2003),
            invite_link=SimpleNamespace(creates_join_request=True),
        )
        non_request_invite = SimpleNamespace(
            chat=SimpleNamespace(id=-100123),
            from_user=SimpleNamespace(id=2004),
            invite_link=SimpleNamespace(creates_join_request=False),
        )
        missing_invite = SimpleNamespace(
            chat=SimpleNamespace(id=-100123),
            from_user=SimpleNamespace(id=2005),
            invite_link=None,
        )

        await chat_join_request_handler(wrong_group_request, self.db, config)
        await chat_join_request_handler(non_request_invite, self.db, config)
        await chat_join_request_handler(missing_invite, self.db, config)
        self.assertFalse(await self.db.has_bot_access(2003))
        self.assertFalse(await self.db.has_bot_access(2004))
        self.assertFalse(await self.db.has_bot_access(2005))

        await chat_join_request_handler(valid_request, self.db, config)

        self.assertTrue(await self.db.has_bot_access(2002))
        access = await self.db.fetchone("SELECT source_chat_id FROM bot_access WHERE telegram_id=?", (2002,))
        self.assertEqual(access["source_chat_id"], -100123)

    async def test_access_link_uses_join_request_invite_and_persists_it(self) -> None:
        await self.db.add_admin(1001, "owner", ["channels"], 1001)
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001),
            answer=AsyncMock(),
        )
        bot = SimpleNamespace(
            id=9001,
            get_chat=AsyncMock(return_value=SimpleNamespace(type="supergroup")),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
            create_chat_invite_link=AsyncMock(
                return_value=SimpleNamespace(
                    creates_join_request=True,
                    invite_link="https://t.me/+request-link",
                )
            ),
        )
        config = Config("token", ("token",), 1001, (1001,), "db.sqlite3", "INFO", -100123)

        await create_access_link(message, self.db, config, bot)

        bot.create_chat_invite_link.assert_awaited_once_with(
            chat_id=-100123,
            creates_join_request=True,
        )
        self.assertEqual(await self.db.get_setting("access_invite_link"), "https://t.me/+request-link")

    async def test_private_group_can_be_added_from_owner_panel(self) -> None:
        await self.db.add_admin(1001, "owner", ["channels"], 1001)
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001),
            text="-100123",
            forward_origin=None,
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"chat_type": "group", "visibility": "private"}),
            clear=AsyncMock(),
        )
        chat = SimpleNamespace(
            id=-100123,
            type="supergroup",
            username=None,
            title="Maxfiy guruh",
        )
        bot = SimpleNamespace(
            id=9001,
            get_chat=AsyncMock(return_value=chat),
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status="administrator", can_invite_users=True)
            ),
            create_chat_invite_link=AsyncMock(
                return_value=SimpleNamespace(
                    invite_link="https://t.me/+private-group",
                    creates_join_request=True,
                )
            ),
        )
        config = Config("token", ("token",), 1001, (1001,), "db.sqlite3", "INFO")

        await save_linked_channel_or_group(message, state, self.db, config, bot)

        channel = await self.db.fetchone(
            "SELECT * FROM bot_channels WHERE bot_id=9001 AND channel_id=-100123"
        )
        self.assertEqual(channel["chat_type"], "group")
        self.assertEqual(channel["channel_id"], -100123)
        self.assertEqual(channel["invite_link"], "https://t.me/+private-group")
        bot.create_chat_invite_link.assert_awaited_once_with(
            chat_id=-100123,
            creates_join_request=True,
        )
        state.clear.assert_awaited_once()

    async def test_private_group_requires_invite_permission_to_generate_request_link(self) -> None:
        await self.db.add_admin(1001, "owner", ["channels"], 1001)
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001),
            text="-100123",
            forward_origin=None,
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"chat_type": "group", "visibility": "private"}),
            clear=AsyncMock(),
        )
        bot = SimpleNamespace(
            id=9001,
            get_chat=AsyncMock(
                return_value=SimpleNamespace(
                    id=-100123,
                    type="supergroup",
                    username=None,
                    title="Maxfiy guruh",
                )
            ),
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status="administrator", can_invite_users=False)
            ),
            create_chat_invite_link=AsyncMock(),
        )
        config = Config("token", ("token",), 1001, (1001,), "db.sqlite3", "INFO")

        await save_linked_channel_or_group(message, state, self.db, config, bot)

        bot.create_chat_invite_link.assert_not_awaited()
        self.assertIsNone(
            await self.db.fetchone(
                "SELECT channel_id FROM bot_channels WHERE bot_id=9001 AND channel_id=-100123"
            )
        )
        message.answer.assert_awaited()
        self.assertIn("Foydalanuvchilarni taklif qilish", message.answer.await_args.args[0])

    async def test_private_group_keeps_supplied_request_link_separate_from_chat_id(self) -> None:
        await self.db.add_admin(1001, "owner", ["channels"], 1001)
        request_link = "https://t.me/+group-request"
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001),
            text=f"-100123 | {request_link}",
            forward_origin=None,
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"chat_type": "group", "visibility": "private"}),
            clear=AsyncMock(),
        )
        bot = SimpleNamespace(
            id=9001,
            get_chat=AsyncMock(
                return_value=SimpleNamespace(
                    id=-100123,
                    type="supergroup",
                    username=None,
                    title="Maxfiy guruh",
                )
            ),
            get_chat_member=AsyncMock(
                return_value=SimpleNamespace(status="administrator", can_invite_users=False)
            ),
            create_chat_invite_link=AsyncMock(),
        )
        config = Config("token", ("token",), 1001, (1001,), "db.sqlite3", "INFO")

        await save_linked_channel_or_group(message, state, self.db, config, bot)

        channel = await self.db.fetchone(
            "SELECT channel_id,invite_link FROM bot_channels WHERE bot_id=9001 AND channel_id=-100123"
        )
        self.assertEqual(channel["channel_id"], -100123)
        self.assertEqual(channel["invite_link"], request_link)
        bot.create_chat_invite_link.assert_not_awaited()

    async def test_custom_join_request_invite_is_preserved_for_public_chat(self) -> None:
        await self.db.add_admin(1001, "owner", ["channels"], 1001)
        request_link = "https://t.me/+join-request-invite"
        message = SimpleNamespace(
            from_user=SimpleNamespace(id=1001),
            text=f"@public_channel | {request_link}",
            forward_origin=None,
            answer=AsyncMock(),
        )
        state = SimpleNamespace(
            get_data=AsyncMock(return_value={"chat_type": "channel", "visibility": "public"}),
            clear=AsyncMock(),
        )
        chat = SimpleNamespace(
            id=-100123,
            type="channel",
            username="public_channel",
            title="Ommaviy kanal",
        )
        bot = SimpleNamespace(
            id=9001,
            get_chat=AsyncMock(return_value=chat),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
            create_chat_invite_link=AsyncMock(),
        )
        config = Config("token", ("token",), 1001, (1001,), "db.sqlite3", "INFO")

        await save_linked_channel_or_group(message, state, self.db, config, bot)

        channel = await self.db.fetchone(
            "SELECT * FROM bot_channels WHERE bot_id=9001 AND channel_id=-100123"
        )
        self.assertEqual(channel["invite_link"], request_link)
        bot.create_chat_invite_link.assert_not_awaited()

        bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(status="left", is_member=False))
        allowed, missing = await subscription_status(bot, self.db, 1002)

        self.assertFalse(allowed)
        self.assertEqual(missing[0]["invite_link"], request_link)

    async def test_mandatory_subscription_requires_membership_in_every_chat(self) -> None:
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?,?)",
            (9002, -100123, None, "https://t.me/+private-channel", "channel", "Private channel"),
        )
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?,?)",
            (9002, -100456, None, "https://t.me/+private-group", "group", "Private group"),
        )
        bot = SimpleNamespace(
            id=9002,
            get_chat_member=AsyncMock(
                side_effect=[
                    SimpleNamespace(status="member", is_member=True),
                    SimpleNamespace(status="left", is_member=False),
                ]
            )
        )

        allowed, channels = await subscription_status(bot, self.db, 2020)

        self.assertFalse(allowed)
        self.assertEqual(len(channels), 1)
        self.assertEqual(channels[0]["channel_id"], -100456)
        self.assertEqual(
            [call.args for call in bot.get_chat_member.await_args_list],
            [(-100123, 2020), (-100456, 2020)],
        )

        bot.get_chat_member = AsyncMock(
            return_value=SimpleNamespace(status="member", is_member=True),
        )
        allowed, _ = await subscription_status(bot, self.db, 2020)

        self.assertTrue(allowed)
        self.assertEqual(bot.get_chat_member.await_count, 2)

    async def test_two_bots_use_independent_required_channels(self) -> None:
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) "
            "VALUES(?,?,?,?,?,?)",
            (9101, -100101, "bot_one_channel", "https://t.me/bot_one_channel", "channel", "Bot one"),
        )
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) "
            "VALUES(?,?,?,?,?,?)",
            (9102, -100202, "bot_two_channel", "https://t.me/bot_two_channel", "channel", "Bot two"),
        )
        await self.db.initialize_bot_subscription_settings(9101, inherit_legacy=False)
        await self.db.initialize_bot_subscription_settings(9102, inherit_legacy=False)
        bot_one = SimpleNamespace(
            id=9101,
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left", is_member=False)),
        )
        bot_two = SimpleNamespace(
            id=9102,
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member", is_member=True)),
        )

        one_allowed, one_missing = await subscription_status(bot_one, self.db, 3001)
        two_allowed, two_missing = await subscription_status(bot_two, self.db, 3001)

        self.assertFalse(one_allowed)
        self.assertEqual([chat["channel_id"] for chat in one_missing], [-100101])
        self.assertTrue(two_allowed)
        self.assertEqual(two_missing, [])
        bot_one.get_chat_member.assert_awaited_once_with(-100101, 3001)
        bot_two.get_chat_member.assert_awaited_once_with(-100202, 3001)

    async def test_channel_list_includes_details_and_separate_delete_buttons(self) -> None:
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?,?)",
            (9003, -100123, "public_channel", "https://t.me/public_channel", "channel", "Ommaviy kanal"),
        )
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?,?)",
            (9003, -100456, None, "https://t.me/+private-group", "group", "Yopiq guruh"),
        )

        text, keyboard = await channel_list_view(self.db, 9003)

        self.assertIn("Ommaviy kanal", text)
        self.assertIn("@public_channel", text)
        self.assertIn("Kanal", text)
        self.assertIn("Yopiq guruh", text)
        self.assertIn("-100456", text)
        self.assertIn("Guruh", text)
        delete_buttons = [
            button.callback_data
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("channel:remove:")
        ]
        self.assertEqual(delete_buttons, ["channel:remove:1:0", "channel:remove:2:0"])

    async def test_subscription_check_refreshes_only_missing_chat_buttons(self) -> None:
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?,?)",
            (9004, -100123, None, "https://t.me/+private-channel", "channel", "Private channel"),
        )
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?,?)",
            (9004, -100456, None, "https://t.me/+private-group", "group", "Private group"),
        )
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=2022),
            message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()),
            answer=AsyncMock(),
        )
        bot = SimpleNamespace(
            id=9004,
            get_chat_member=AsyncMock(
                side_effect=[
                    SimpleNamespace(status="member", is_member=True),
                    SimpleNamespace(status="left", is_member=False),
                ]
            )
        )
        config = Config("token", ("token",), 1001, (1001,), "db.sqlite3", "INFO")

        await subscription_check(callback, bot, self.db, config)

        markup = callback.message.edit_text.await_args.kwargs["reply_markup"]
        self.assertEqual(len(markup.inline_keyboard), 2)
        self.assertEqual(markup.inline_keyboard[0][0].url, "https://t.me/+private-group")
        self.assertEqual(markup.inline_keyboard[0][0].text, "👥 1-guruhga qo‘shilish")

    async def test_start_shows_subscription_gate_until_user_joins_required_chat(self) -> None:
        await self.db.execute(
            "INSERT INTO bot_channels(bot_id,channel_id,channel_username,invite_link,chat_type,title) VALUES(?,?,?,?,?,?)",
            (9005, -100123, None, "https://t.me/+private-channel", "channel", "Private channel"),
        )
        user = SimpleNamespace(id=2021, full_name="Test User", username=None)
        message = SimpleNamespace(from_user=user, answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())
        bot = SimpleNamespace(
            id=9005,
            token="test-token",
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left", is_member=False)),
        )
        config = Config("test-token", ("test-token",), 1001, (1001,), "db.sqlite3", "INFO")

        await start_handler(message, state, bot, self.db, config)

        self.assertEqual(message.answer.await_args.args[0], DEFAULT_SUBSCRIPTION)
        self.assertEqual(message.answer.await_args.kwargs["reply_markup"].inline_keyboard[0][0].url, "https://t.me/+private-channel")
        self.assertEqual(message.answer.await_count, 1)

        message.answer.reset_mock()
        bot.get_chat_member = AsyncMock(return_value=SimpleNamespace(status="member", is_member=True))
        await start_handler(message, state, bot, self.db, config)

        self.assertEqual(message.answer.await_count, 2)
        self.assertIn("xush kelibsiz", message.answer.await_args_list[0].args[0].casefold())
        self.assertEqual(message.answer.await_args_list[1].args[0], "Kerakli bo‘limni tanlang:")

    async def test_admin_access_requires_configured_telegram_id(self) -> None:
        config = Config("token", ("token",), 1001, (1001, 3003, 4004), "db.sqlite3", "INFO")
        await self.db.add_admin(2002, "admin", ["movies"], 1001)
        await self.db.add_admin(1001, "owner", ["movies"], 1001)

        self.assertFalse(await can(self.db, 2002, "movies", config))
        self.assertTrue(await can(self.db, 1001, "movies", config))


class MainMenuTests(unittest.TestCase):
    def test_public_menu_removes_keyboard_when_no_actions_are_enabled(self) -> None:
        self.assertIsInstance(main_menu(False), ReplyKeyboardRemove)

    def test_bot_two_can_remove_all_reply_keyboards(self) -> None:
        self.assertIsInstance(main_menu(True, payments_enabled=True, hide_keyboard=True), ReplyKeyboardRemove)
        self.assertIsInstance(admin_menu(hide_keyboard=True), ReplyKeyboardRemove)
        self.assertIsInstance(movie_menu(hide_keyboard=True), ReplyKeyboardRemove)
        self.assertIsInstance(cancel_menu(hide_keyboard=True), ReplyKeyboardRemove)

    def test_public_menu_hides_search_channel_help_and_admin(self) -> None:
        menu = main_menu(False, payments_enabled=True)
        labels = {button.text for row in menu.keyboard for button in row}

        self.assertEqual(labels, {"💳 To‘lov"})

    def test_admin_menu_entry_is_only_added_for_admin(self) -> None:
        menu = main_menu(True)
        labels = {button.text for row in menu.keyboard for button in row}

        self.assertEqual(labels, {"🛠 Admin paneli"})

    def test_series_controls_are_available_in_movie_menu(self) -> None:
        labels = {button.text for row in movie_menu().keyboard for button in row}

        self.assertIn("📺 Serial qo‘shish", labels)
        self.assertIn("➕ Mavsum/qism qo‘shish", labels)
        self.assertIn("🗑 Serial qismini o‘chirish", labels)
        self.assertIn("📋 Seriallar", labels)

    def test_series_features_are_enabled_for_each_configured_bot(self) -> None:
        config = Config("token-1", ("token-1", "token-2"), 1001, (1001,), "db.sqlite3", "INFO")

        self.assertTrue(is_series_bot(SimpleNamespace(token="token-1"), config))
        self.assertTrue(is_series_bot(SimpleNamespace(token="token-2"), config))

    def test_episode_button_is_bound_to_lookup_request(self) -> None:
        keyboard = series_episodes_keyboard([{"id": 8, "episode_number": 2}], request_id=42)

        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "series:episode:42:8")

    def test_season_button_leads_to_episode_selection(self) -> None:
        keyboard = series_seasons_keyboard([{"season_number": 2}], request_id=42)

        self.assertEqual(keyboard.inline_keyboard[0][0].text, "📁 2-mavsum")
        self.assertEqual(keyboard.inline_keyboard[0][0].callback_data, "series:season:42:2")
        self.assertEqual(keyboard.inline_keyboard[0][0].style, "primary")

    def test_inline_confirmation_uses_success_and_danger_styles(self) -> None:
        buttons = confirm_keyboard("yes").inline_keyboard[0]

        self.assertEqual(buttons[0].style, "success")
        self.assertEqual(buttons[1].style, "danger")

    def test_public_chat_link_parser_accepts_public_links_only(self) -> None:
        self.assertEqual(public_chat_username("https://t.me/coder_company"), "coder_company")
        self.assertEqual(public_chat_username("@coder_company"), "coder_company")
        self.assertIsNone(public_chat_username("https://t.me/+privateinvite"))
        self.assertIsNone(public_chat_username("https://example.com/channel"))
        self.assertEqual(private_chat_invite_link("https://t.me/+privateinvite"), "https://t.me/+privateinvite")
        self.assertEqual(private_chat_invite_link("t.me/joinchat/Invite_code"), "https://t.me/joinchat/Invite_code")
        self.assertIsNone(private_chat_invite_link("https://example.com/+privateinvite"))

    def test_channel_management_lists_entries_and_add_actions(self) -> None:
        keyboard = channel_management_keyboard(
            enabled=True,
            channel_count=1,
        )
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        callbacks = {button.callback_data for button in buttons}
        labels = {button.text for button in buttons}

        self.assertIn("channel:add", callbacks)
        self.assertIn("channels:list:0", callbacks)
        self.assertIn("channels:check", callbacks)
        self.assertIn("channels:back", callbacks)
        self.assertTrue(any("Majburiy obunani o‘chirish" in label for label in labels))

    def test_channel_add_flow_offers_public_and_private_chat_types(self) -> None:
        public_labels = {
            button.text
            for row in channel_add_type_keyboard().inline_keyboard
            for button in row
        }
        private_labels = {
            button.text
            for row in private_chat_type_keyboard().inline_keyboard
            for button in row
        }

        self.assertIn("📢 Ommaviy kanal", public_labels)
        self.assertIn("👥 Ommaviy guruh", public_labels)
        self.assertIn("🔒 Yopiq kanal/guruh", public_labels)
        self.assertIn("📢 Yopiq kanal", private_labels)
        self.assertIn("👥 Yopiq guruh", private_labels)

    def test_subscription_keyboard_displays_channel_and_group_invites(self) -> None:
        keyboard = subscription_keyboard([
            {"invite_link": "https://t.me/+channel", "chat_type": "channel"},
            {"invite_link": "https://t.me/+group", "chat_type": "group"},
        ])

        self.assertEqual(keyboard.inline_keyboard[0][0].url, "https://t.me/+channel")
        self.assertIn("kanalga", keyboard.inline_keyboard[0][0].text)
        self.assertEqual(keyboard.inline_keyboard[1][0].url, "https://t.me/+group")
        self.assertIn("guruhga", keyboard.inline_keyboard[1][0].text)

    def test_series_actions_and_title_search_use_scoped_callbacks(self) -> None:
        seasons = series_seasons_keyboard(
            [{"season_number": 1}],
            request_id=42,
            series_id=8,
            is_favorite=False,
            subscribed=True,
        )
        self.assertEqual(seasons.inline_keyboard[0][0].callback_data, "series:season:42:1")
        self.assertEqual(seasons.inline_keyboard[1][0].callback_data, "series:favorite:42:8")
        self.assertEqual(seasons.inline_keyboard[1][1].callback_data, "series:subscribe:42:8")

        search = title_search_keyboard([{"kind": "movie", "id": 3, "title": "Film"}], request_id=51)
        self.assertEqual(search.inline_keyboard[0][0].callback_data, "search:movie:51:3")

        delete = series_delete_episodes_keyboard([{"id": 9, "season_number": 2, "episode_number": 4}])
        self.assertEqual(delete.inline_keyboard[0][0].callback_data, "series:deleteepisode:9")


class ConfigTests(unittest.TestCase):
    def test_whitespace_env_file_and_existing_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("BOT_TOKEN example-token\nOWNER_IDS 100, 200\n", encoding="utf-8")
            previous_token = os.environ.get("BOT_TOKEN")
            previous_owners = os.environ.get("OWNER_IDS")
            try:
                os.environ.pop("BOT_TOKEN", None)
                os.environ.pop("OWNER_IDS", None)
                _load_env_file(path)
                self.assertEqual(os.environ["BOT_TOKEN"], "example-token")
                self.assertEqual(os.environ["OWNER_IDS"], "100, 200")
            finally:
                if previous_token is None:
                    os.environ.pop("BOT_TOKEN", None)
                else:
                    os.environ["BOT_TOKEN"] = previous_token
                if previous_owners is None:
                    os.environ.pop("OWNER_IDS", None)
                else:
                    os.environ["OWNER_IDS"] = previous_owners

    def test_load_config_supports_multiple_bot_tokens(self) -> None:
        keys = ("BOT_TOKEN", "BOT_TOKEN_2", "BOT_TOKEN_3", "BOT_TOKENS", "OWNER_IDS", "ACCESS_GROUP_ID")
        previous = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["BOT_TOKEN"] = "primary-token"
            os.environ["BOT_TOKEN_2"] = "second-token"
            os.environ.pop("BOT_TOKEN_3", None)
            os.environ["BOT_TOKENS"] = "third-token,fourth-token"
            os.environ["OWNER_IDS"] = "100"
            os.environ["ACCESS_GROUP_ID"] = "-1001234567890"
            from config import load_config

            config = load_config()
            self.assertEqual(config.bot_tokens, ("primary-token", "third-token", "fourth-token", "second-token"))
            self.assertEqual(config.access_group_id, -1001234567890)
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class TelegramCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_series_and_user_commands_are_available_for_every_bot(self) -> None:
        commands = {command.command for command in admin_commands(series_enabled=False)}

        self.assertTrue({"addseries", "addseriesepisode", "deleteseriesepisode", "part", "series"} <= commands)
        self.assertTrue({"search", "favorites", "subscriptions"} <= commands)

    async def test_missing_admin_chat_does_not_abort_command_setup(self) -> None:
        bot = SimpleNamespace(
            set_my_commands=AsyncMock(
                side_effect=TelegramBadRequest(
                    method=SetMyCommands(commands=[]),
                    message="Bad Request: chat not found",
                )
            )
        )

        with self.assertLogs("telegram_commands", level="WARNING"):
            await set_admin_commands(bot, admin_id=12345, series_enabled=True)

        bot.set_my_commands.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()