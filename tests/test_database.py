import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from config import _load_env_file
from database import Database


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

    async def test_admin_permissions_and_audit_log(self) -> None:
        await self.db.add_admin(2002, "admin", ["movies"], 1001)
        admin = await self.db.get_admin(2002)
        self.assertEqual(admin["permissions"], ["movies"])
        await self.db.log_admin(1001, "admin_added", "2002")
        log = await self.db.fetchone("SELECT * FROM admin_logs WHERE admin_id=?", (1001,))
        self.assertEqual(log["action"], "admin_added")


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
        keys = ("BOT_TOKEN", "BOT_TOKEN_2", "BOT_TOKEN_3", "BOT_TOKENS", "OWNER_IDS")
        previous = {key: os.environ.get(key) for key in keys}
        try:
            os.environ["BOT_TOKEN"] = "primary-token"
            os.environ["BOT_TOKEN_2"] = "second-token"
            os.environ.pop("BOT_TOKEN_3", None)
            os.environ["BOT_TOKENS"] = "third-token,fourth-token"
            os.environ["OWNER_IDS"] = "100"
            from config import load_config

            config = load_config()
            self.assertEqual(config.bot_tokens, ("primary-token", "third-token", "fourth-token", "second-token"))
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()