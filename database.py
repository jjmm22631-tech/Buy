import asyncio
import json
from pathlib import Path
from typing import Any

import aiosqlite


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = await aiosqlite.connect(self.path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA journal_mode=WAL")
        await self.connection.execute("PRAGMA foreign_keys=ON")
        await self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                username TEXT,
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_active_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_blocked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'admin',
                permissions TEXT NOT NULL DEFAULT '[]',
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                added_by INTEGER
            );
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'video',
                extra_text TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL UNIQUE,
                channel_username TEXT,
                invite_link TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL,
                proof_file_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TEXT,
                confirmed_by INTEGER
            );
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                message_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                total_users INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS movie_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                movie_code TEXT NOT NULL,
                found INTEGER NOT NULL DEFAULT 0,
                delivered INTEGER NOT NULL DEFAULT 0,
                requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_users_activity ON users(last_active_at);
            CREATE INDEX IF NOT EXISTS idx_requests_code ON movie_requests(movie_code);
            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
            """
        )
        await self.connection.commit()
        await self._migrate_movies()

    async def _migrate_movies(self) -> None:
        assert self.connection is not None
        cursor = await self.connection.execute("PRAGMA table_info(movies)")
        columns = {row["name"] for row in await cursor.fetchall()}
        if "file_type" not in columns:
            await self.connection.execute("ALTER TABLE movies ADD COLUMN file_type TEXT NOT NULL DEFAULT 'video'")
        if "is_active" not in columns:
            await self.connection.execute("ALTER TABLE movies ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        cursor = await self.connection.execute("PRAGMA table_info(movie_requests)")
        request_columns = {row["name"] for row in await cursor.fetchall()}
        if "delivered" not in request_columns:
            await self.connection.execute("ALTER TABLE movie_requests ADD COLUMN delivered INTEGER NOT NULL DEFAULT 0")
        await self.connection.commit()

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
            self.connection = None

    async def execute(self, query: str, params: tuple[Any, ...] = ()) -> int:
        if self.connection is None:
            raise RuntimeError("Ma’lumotlar bazasi ulanmagan")
        async with self.lock:
            cursor = await self.connection.execute(query, params)
            await self.connection.commit()
            return cursor.lastrowid or cursor.rowcount

    async def fetchone(self, query: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        if self.connection is None:
            raise RuntimeError("Ma’lumotlar bazasi ulanmagan")
        async with self.lock:
            cursor = await self.connection.execute(query, params)
            return await cursor.fetchone()

    async def fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        if self.connection is None:
            raise RuntimeError("Ma’lumotlar bazasi ulanmagan")
        async with self.lock:
            cursor = await self.connection.execute(query, params)
            return await cursor.fetchall()

    async def set_setting(self, key: str, value: str) -> None:
        await self.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP",
            (key, value),
        )

    async def get_setting(self, key: str, default: str = "") -> str:
        row = await self.fetchone("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    async def add_admin(self, telegram_id: int, role: str, permissions: list[str], added_by: int) -> None:
        await self.execute(
            "INSERT INTO admins(telegram_id, role, permissions, added_by) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET role=excluded.role, permissions=excluded.permissions",
            (telegram_id, role, json.dumps(permissions), added_by),
        )

    async def get_admin(self, telegram_id: int) -> dict[str, Any] | None:
        row = await self.fetchone("SELECT * FROM admins WHERE telegram_id=?", (telegram_id,))
        if row is None:
            return None
        result = dict(row)
        try:
            result["permissions"] = json.loads(result["permissions"])
        except (TypeError, json.JSONDecodeError):
            result["permissions"] = []
        return result

    async def log_admin(self, admin_id: int, action: str, details: str = "") -> None:
        await self.execute(
            "INSERT INTO admin_logs(admin_id, action, details) VALUES(?, ?, ?)",
            (admin_id, action, details[:1000]),
        )