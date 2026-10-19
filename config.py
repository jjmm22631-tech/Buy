import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    bot_token: str
    bot_tokens: tuple[str, ...]
    main_admin_id: int
    admin_ids: tuple[int, ...]
    database_path: str
    log_level: str
    access_group_id: int | None = None


def _load_env_file(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" in line:
            key, value = line.split("=", 1)
        else:
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            key, value = parts
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value)


def load_config() -> Config:
    _load_env_file()
    token_values = [os.getenv("BOT_TOKEN", "").strip()]
    token_values.extend(value.strip() for value in re.split(r"[,;\s]+", os.getenv("BOT_TOKENS", "")) if value.strip())
    numbered_tokens = sorted(
        ((int(match.group(1)), value.strip()) for key, value in os.environ.items()
         if (match := re.fullmatch(r"BOT_TOKEN_(\d+)", key)) and value.strip()),
        key=lambda item: item[0],
    )
    token_values.extend(value for _, value in numbered_tokens)
    bot_tokens = tuple(dict.fromkeys(token for token in token_values if token))
    if not bot_tokens:
        raise RuntimeError(".env faylida BOT_TOKEN ko‘rsatilmagan.")

    raw_admin_ids = os.getenv("OWNER_IDS", os.getenv("MAIN_ADMIN_ID", ""))
    try:
        admin_ids = tuple(dict.fromkeys(int(value) for value in raw_admin_ids.replace(";", ",").replace(" ", ",").split(",") if value.strip()))
    except ValueError as error:
        raise RuntimeError("OWNER_IDS yoki MAIN_ADMIN_ID faqat Telegram ID raqamlaridan iborat bo‘lishi kerak.") from error
    if not admin_ids or any(admin_id <= 0 for admin_id in admin_ids):
        raise RuntimeError(".env faylida kamida bitta musbat OWNER_IDS yoki MAIN_ADMIN_ID bo‘lishi kerak.")

    raw_access_group_id = os.getenv("ACCESS_GROUP_ID", "").strip()
    try:
        access_group_id = int(raw_access_group_id) if raw_access_group_id else None
    except ValueError as error:
        raise RuntimeError("ACCESS_GROUP_ID guruhning manfiy Telegram ID raqami bo‘lishi kerak.") from error
    if access_group_id is not None and access_group_id >= 0:
        raise RuntimeError("ACCESS_GROUP_ID guruhning manfiy Telegram ID raqami bo‘lishi kerak.")

    return Config(
        bot_token=bot_tokens[0],
        bot_tokens=bot_tokens,
        main_admin_id=admin_ids[0],
        admin_ids=admin_ids,
        database_path=os.getenv("DATABASE_PATH", "data/kino_bot.sqlite3"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        access_group_id=access_group_id,
    )