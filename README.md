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
OWNER_IDS=Telegram_ID_1,Telegram_ID_2,Telegram_ID_3
DATABASE_PATH=data/kino_bot.sqlite3
LOG_LEVEL=INFO
```

Admin paneliga kira oladigan Telegram ID’larini vergul yoki bo‘sh joy bilan ajrating; bu ro‘yxatda bo‘lmagan, hatto bazada admin sifatida yozilgan ID’lar ham admin buyruqlarini ishlata olmaydi. `MAIN_ADMIN_ID` eski sozlama nomi sifatida ham qo‘llanadi. `.env` maxfiy ma’lumot saqlaydi; uni ommaviy repoga yubormang.

Ikki Telegram botini bitta jarayonda ishga tushirish uchun Render Environment’da `BOT_TOKEN` va `BOT_TOKEN_2` ni kiriting. Qo‘shimcha tokenlarga `BOT_TOKEN_3` kabi nom berish yoki vergul bilan ajratilgan `BOT_TOKENS` qiymatidan foydalanish mumkin. Barcha botlar bir xil kino bazasi, adminlar va sozlamalarni ishlatadi; har bir botni BotFather’dan alohida yarating.

Har bir admin bot buyruqlar ro‘yxatini olish uchun tegishli botga bir marta `/start` yuborishi kerak. Admin botni hali boshlamagan bo‘lsa, uning shaxsiy buyruqlari keyingi `/start` vaqtida o‘rnatiladi; bu holat botning ishga tushishini to‘xtatmaydi.

## Seriallar, qidiruv va obunalar

Serial funksiyalari barcha sozlangan botlarda ishlaydi va bitta SQLite bazasidan foydalanadi. Admin panelidagi **🎬 Kinolar** bo‘limidan serial qo‘shish, mavsum/qism qo‘shish, qism o‘chirish va seriallar ro‘yxati tugmalariga kiring; mos slash-buyruqlar ham ishlaydi. Har bir qism videosidan oldin `/part <mavsum> <qism>` yuboring (masalan, `/part 1 1`); yangi mavsum birinchi qismi qo‘shilganda avtomatik yaratiladi. Qismlar mavsum va qism raqami bo‘yicha tartiblanadi. Eski serial qismlari avtomatik ravishda 1-mavsumga o‘tkaziladi.

Foydalanuvchi kino yoki serial kodini yoxud nomini yuborib qidiradi. Serial sahifasida ⭐ sevimlilarga saqlash va 🔔 yangi qismlar haqida bildirishnoma olish tugmalari mavjud. `/favorites` va `/subscriptions` saqlangan seriallarni ko‘rsatadi; `/search` qidiruvni boshlaydi. `/start` dagi inline menyu ham shu amallarni ochadi. Foydalanuvchilar uchun pastki reply paneli yashiriladi; to‘lov yoqilgan bo‘lsa, zarur `💳 To‘lov` tugmasi ko‘rsatiladi.

`/start` har safar joriy suhbat jarayonini bekor qilib, kod yuborishni qayta so‘raydi. Birinchi bot kino salomlashuvini, ikkinchi bot serial salomlashuvini ko‘rsatadi. Admin `/set_welcome_text` va `/set_series_welcome_text` orqali ularni alohida o‘zgartirishi mumkin.

## Ishga tushirish

```bash
python bot.py
```

Bot long polling ishlatadi. Har bir bot tokeni uchun faqat bitta Render service/instance ishlating. Bir serverda tasodifan takroriy jarayon ishga tushsa, lokal lock uni to‘xtatadi. Bir nechta Render service alohida serverlarda ishlayotgan bo‘lsa, eski yoki takroriy service/instance’ni Render Dashboard’dan to‘xtating. Aks holda Telegram `TelegramConflictError` qaytarib, yangilanishlarni ikki jarayon o‘rtasida bo‘lib yuboradi. Har safar `/start` bosilganda oldingi suhbat bosqichi bekor qilinib, kino yoki serial kodi qayta so‘raladi. Adminlar `/admin` orqali panelni ochadi; panelda bot va majburiy obuna holati 🟢/🟡/🔴 belgilar bilan ko‘rsatiladi. Kinolar menyusida qo‘shish, tahrirlash, qidirish, o‘chirish va ro‘yxat amallari mavjud. Kanal va foydalanuvchi boshqaruvi, xabar yuborish, to‘lov va sozlamalar bo‘limlarida ko‘rsatilgan slash-buyruqlardan foydalaning.

## Majburiy obuna

Admin panelidagi **📢 Majburiy obuna** bo‘limida sozlamalar inline tugmalar bilan boshqariladi va har bir botning kanal/guruh ro‘yxati hamda yoqish holati alohida saqlanadi. Eski `channels` ro‘yxati birinchi sozlangan botga ko‘chadi; ikkinchi bot alohida bo‘sh ro‘yxatdan boshlanadi. **➕ Kanal/guruh qo‘shish** orqali ommaviy kanal/guruhni `@username` yoki `https://t.me/username` bilan qo‘shing. Yopiq kanal/guruh qo‘shishda chat ID’ni yuboring yoki o‘sha chatdagi xabarni botga forward qiling; taklif havolasini bot avtomatik yaratadi. Mavjud maxfiy taklif havolasi bilan ulashda `chat_id | https://t.me/+...` formatini ishlating. Telegram Bot API maxfiy taklif havolasining o‘zidan chat ID’ni aniqlay olmaydi, shuning uchun ID yoki forward qilingan chat xabari zarur. Bot chatni tekshiradi va faqat administrator bo‘lsa saqlaydi. **📋 Ulangan kanallar/guruhlar** ro‘yxatda nom, turi, username yoki chat ID hamda holatni ko‘rsatadi; chatlar ko‘p bo‘lsa sahifalanadi, har birini alohida o‘chirish mumkin. **🔄 Obunani tekshirish** botning ulangan chatlardagi admin holatini tekshiradi. Majburiy obunani yoqish/o‘chirish ham shu menyuda.

Botni tekshiriladigan har bir kanal yoki guruhga administrator qilib qo‘shing; bot a’zolikni tekshira olishi va maxfiy taklif havolasini yaratishi uchun administrator bo‘lishi kerak. Bot `/start` bosilganda barcha ulangan chatlardagi a’zolikni tekshiradi. Birortasiga a’zo bo‘lmasa, obuna havolalari va **✅ Obunani tekshirish** tugmasini ko‘rsatadi; barcha chatlarda a’zoligi tasdiqlangach, bot menyusini ochadi.

Bot guruhdagi xabar, kino kodi yoki buyruqlarga javob bermaydi; bot bilan faqat shaxsiy chatda ishlanadi. Guruhda bot faqat Telegram yuborgan join-request yangilanishini kuzatib, foydalanuvchiga botdan foydalanish ruxsatini yozadi. Bot join request’ni qabul qilmaydi va rad ham etmaydi — guruh admini o‘zi boshqaradi.

Buyruqlar orqali boshqarish ham mumkin:

```text
/addchannel -1001234567890 | kanal_username | https://t.me/kanal_username
/channels
/subscription_toggle
```

## Botdan foydalanish uchun guruh so‘rovi

Ixtiyoriy ravishda `ACCESS_GROUP_ID` sozlamasiga botdan foydalanish ruxsatini beradigan aniq guruhning manfiy Telegram ID’sini kiriting. Botni shu guruhga administrator qilib qo‘shing. Admin `/accesslink` buyrug‘i bilan `creates_join_request=True` taklif havolasi yaratib, foydalanuvchilarga tarqatadi. Sozlama bo‘lmaganda, bu qo‘shimcha ruxsat tekshiruvi ishlamaydi va avvalgi bot xatti-harakati saqlanadi.

Faqat `ACCESS_GROUP_ID` bilan mos kelgan guruhdan botga kelgan haqiqiy join-request yangilanishi foydalanuvchining Telegram ID’sini ruxsatlar bazasiga yozadi. Bot `/start` va boshqa foydalanuvchi amallarida shu ruxsatni tekshiradi. Bu ruxsat guruhga a’zo bo‘lishni tasdiqlamaydi yoki foydalanuvchini guruhga avtomatik qo‘shmaydi; guruh admini so‘rovni rad qilgan taqdirda ham bot ruxsati saqlanadi.

Inline tugmalar qo‘llab-quvvatlaydigan Telegram mijozlarida muvaffaqiyatli amallar `success`, bekor qilish/rad etish/o‘chirish amallari esa `danger` uslubida ko‘rinadi.

## Admin huquqlari va to‘lov

`.env` dagi owner ID’lari dastlabki ishga tushishda bazaga yoziladi. Asosiy admin `/addadmin`, `/removeadmin`, `/admins` va `/findadmin` buyruqlaridan foydalanishi mumkin. Qo‘lda to‘lov uchun admin panelidagi `💳 To‘lov sozlamalari` ko‘rsatmalaridan foydalaning; foydalanuvchining to‘lov dalili adminlarga keladi va admin tasdiqlamaguncha holat `pending` bo‘lib qoladi. Bot uchinchi tomon to‘lovini avtomatik amalga oshirmaydi.

## Hosting va zaxira

Render’da **Background Worker** yarating, repository’ni ulang, Build Command sifatida `pip install -r requirements.txt`, Start Command sifatida `python bot.py` kiriting. Environment Variables bo‘limiga `BOT_TOKEN`, kerak bo‘lsa `BOT_TOKEN_2`, `OWNER_IDS`, `DATABASE_PATH=/var/data/kino_bot.sqlite3` va boshqa sozlamalarni kiriting. SQLite ma’lumotlari deploylar orasida saqlanishi uchun Render Persistent Disk ulang va mount path’ni `/var/data` qiling. Bepul yoki ephemeral disk restart/deploy vaqtida bazani yo‘qotishi mumkin. 24/7 ishlash hosting rejasiga bog‘liq.

Bot long polling sababli odatda **Background Worker** bo‘lishi kerak; Worker logidagi `No open ports detected` xabari xato emas, chunki Worker port tinglashi shart emas. Agar Render **Web Service** sifatida joylashtirsangiz, servis bergan `PORT` o‘zgaruvchisi avtomatik tinglanadi; Render sozlamalarida health-check path sifatida `/health` ni belgilang.

Zaxira nusxa olishdan oldin botni to‘xtating yoki SQLite’ning zaxira API’sidan foydalaning. Zaxirani alohida, himoyalangan joyda saqlang.

## Tekshiruv va muammolar

```bash
python -m unittest discover -s tests -v
```

Token yoki owner ID noto‘g‘ri bo‘lsa, `.env` kalitlarini tekshiring. `TelegramConflictError` bo‘lsa, shu token bilan ishlayotgan boshqa polling jarayonini to‘xtating. A’zolik tekshiruvi ishlamasa, botning kanal administratorligi, kanal ID’si va havolasini tekshiring.

FSM bosqichlari hozircha xotirada saqlanadi va qayta ishga tushganda tozalanadi; saqlangan kinolar, adminlar, foydalanuvchilar va sozlamalar SQLite’da qoladi.