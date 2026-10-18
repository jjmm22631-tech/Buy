# Uzbek Kinolar Olami

Python 3.11 va aiogram 3 asosidagi Telegram kino bot. Foydalanuvchilar kino kodini yuborib Telegram `file_id` orqali media oladi. Bot SQLite bazasidan foydalanadi; baza fayli qayta ishga tushirishlarda saqlanadi.

## Talablar

- Python 3.11 yoki undan yangi 3.x versiya
- BotFather orqali yaratilgan Telegram bot
- Majburiy obuna kanallarida botga a’zolarni tekshirish uchun administrator huquqi

## O‘rnatish

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

BotFather’da `/newbot` yuborib bot yarating va tokenni oling. `.env` faylini tahrirlang:

```dotenv
BOT_TOKEN=BotFather_bergan_token
BOT_TOKEN_2=ikkinchi_bot_tokeni_ixtiyoriy
OWNER_IDS=Telegram_ID
DATABASE_PATH=data/kino_bot.sqlite3
LOG_LEVEL=INFO
```

Bir nechta asosiy admin ID’sini vergul yoki bo‘sh joy bilan ajrating. `MAIN_ADMIN_ID` eski sozlama nomi sifatida ham qo‘llanadi. `.env` maxfiy ma’lumot saqlaydi; uni ommaviy repoga yubormang.

Ikki Telegram botini bitta jarayonda ishga tushirish uchun Render Environment’da `BOT_TOKEN` va `BOT_TOKEN_2` ni kiriting. Qo‘shimcha tokenlarga `BOT_TOKEN_3` kabi nom berish yoki vergul bilan ajratilgan `BOT_TOKENS` qiymatidan foydalanish mumkin. Barcha botlar bir xil kino bazasi, adminlar va sozlamalarni ishlatadi; har bir botni BotFather’dan alohida yarating.

## Ishga tushirish

```bash
python bot.py
```

Bot long polling ishlatadi. Bir token bilan bir vaqtda faqat bitta polling jarayonini ishga tushiring. Adminlar `/admin` buyrug‘i orqali panelni ochadi. Kinolarni boshqarish menyusida qo‘shish, tahrirlash, qidirish, o‘chirish va ro‘yxat amallari mavjud. Kanal va foydalanuvchi boshqaruvi, broadcast, to‘lov va sozlamalar bo‘limlarida ko‘rsatilgan slash-buyruqlardan foydalaning.

## Majburiy obuna

Botni kanalga administrator qilib qo‘shing. Admin sifatida:

```text
/addchannel -1001234567890 | kanal_username | https://t.me/kanal_username
/channels
/subscription_toggle
```

Kanal havolasi ommaviy yoki taklif havolasi bo‘lishi mumkin. Bot `getChatMember` bilan tekshiradi; kanalga kira olmasa a’zolikni tasdiqlamaydi va xatoni logga yozadi.

## Admin huquqlari va to‘lov

`.env` dagi owner ID’lari dastlabki ishga tushishda bazaga yoziladi. Asosiy admin `/addadmin`, `/removeadmin`, `/admins` va `/findadmin` buyruqlaridan foydalanishi mumkin. Qo‘lda to‘lov uchun admin panelidagi `💳 To‘lov sozlamalari` ko‘rsatmalaridan foydalaning; foydalanuvchining to‘lov dalili adminlarga keladi va admin tasdiqlamaguncha holat `pending` bo‘lib qoladi. Bot uchinchi tomon to‘lovini avtomatik amalga oshirmaydi.

## Hosting va zaxira

Render’da **Background Worker** yarating, repository’ni ulang, Build Command sifatida `pip install -r requirements.txt`, Start Command sifatida `python bot.py` kiriting. Environment Variables bo‘limiga `BOT_TOKEN`, kerak bo‘lsa `BOT_TOKEN_2`, `OWNER_IDS`, `DATABASE_PATH=/var/data/kino_bot.sqlite3` va boshqa sozlamalarni kiriting. SQLite ma’lumotlari deploylar orasida saqlanishi uchun Render Persistent Disk ulang va mount path’ni `/var/data` qiling. Bepul yoki ephemeral disk restart/deploy vaqtida bazani yo‘qotishi mumkin. 24/7 ishlash hosting rejasiga bog‘liq.

Zaxira nusxa olishdan oldin botni to‘xtating yoki SQLite’ning zaxira API’sidan foydalaning. Zaxirani alohida, himoyalangan joyda saqlang.

## Tekshiruv va muammolar

```bash
python -m unittest discover -s tests -v
```

Token yoki owner ID noto‘g‘ri bo‘lsa, `.env` kalitlarini tekshiring. `TelegramConflictError` bo‘lsa, shu token bilan ishlayotgan boshqa polling jarayonini to‘xtating. A’zolik tekshiruvi ishlamasa, botning kanal administratorligi, kanal ID’si va havolasini tekshiring.

FSM bosqichlari hozircha xotirada saqlanadi va qayta ishga tushganda tozalanadi; saqlangan kinolar, adminlar, foydalanuvchilar va sozlamalar SQLite’da qoladi.