import asyncio
import json
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

TOKEN = os.getenv("BOT_TOKEN", "BU_YERGA_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # o'zingizning Telegram ID'ingiz
CHANNEL = "@zcsel_cfg"  # majburiy obuna kanali (bot kanalda ADMIN bo'lishi shart)
CHANNEL_URL = "https://t.me/zcsel_cfg"
DB_FILE = "files.json"

# kalit: (tugma matni, tugma rangi)
# rang: "primary" (ko'k), "success" (yashil), "danger" (qizil)
SECTIONS = {
    "skin": ("🎭 SKIN CHANGER", "primary"),
    "esp": ("🎯 ESP LINE", "success"),
    "walhack": ("🔥 WALHACK", "danger"),
    "heat": ("⚡ HEAT", "primary"),
    "xcode": ("💀 XCODE", "danger"),
}

logging.basicConfig(level=logging.INFO)
bot = Bot(TOKEN)
dp = Dispatcher()


DB: dict = {}
LAST_DB_MSG = None  # adminga yuborilgan "zaxira" xabar ID'si


def load_db() -> dict:
    return DB


async def restore_db() -> None:
    """Bot yonganda fayllar ro'yxatini adminning bot bilan chatidagi
    qadalgan (pinned) xabardan tiklaydi - Render restart bo'lsa ham yo'qolmaydi."""
    global LAST_DB_MSG
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                DB.update(json.load(f))
        except Exception:
            pass
    try:
        chat = await bot.get_chat(ADMIN_ID)
        pm = chat.pinned_message
        if pm and pm.text and pm.text.startswith("DB:"):
            DB.clear()
            DB.update(json.loads(pm.text[3:]))
            LAST_DB_MSG = pm.message_id
            logging.info("Fayllar tiklandi: %s", list(DB))
    except Exception as e:
        logging.warning("Zaxiradan tiklab bo'lmadi: %s", e)


async def persist_db() -> None:
    """Fayllar ro'yxatini saqlaydi va adminga qadalgan xabar sifatida zaxiralaydi."""
    global LAST_DB_MSG
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(DB, f, ensure_ascii=False)
    try:
        msg = await bot.send_message(ADMIN_ID, "DB:" + json.dumps(DB, ensure_ascii=False),
                                     disable_notification=True)
        await bot.unpin_all_chat_messages(ADMIN_ID)
        await bot.pin_chat_message(ADMIN_ID, msg.message_id, disable_notification=True)
        if LAST_DB_MSG:
            try:
                await bot.delete_message(ADMIN_ID, LAST_DB_MSG)
            except Exception:
                pass
        LAST_DB_MSG = msg.message_id
    except Exception as e:
        logging.warning("Zaxiralab bo'lmadi: %s", e)


async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.warning("Obunani tekshirib bo'lmadi: %s", e)
        return False


def sub_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Kanalga obuna bo‘lish", url=CHANNEL_URL,
                                  style="primary")],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check",
                                  style="success")],
        ]
    )


def btn(key: str) -> InlineKeyboardButton:
    text, style = SECTIONS[key]
    # "style" - Telegram'ning rangli tugma maydoni (aiogram extra maydonni o'tkazadi)
    return InlineKeyboardButton(text=text, callback_data=f"sec:{key}", style=style)


def menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [btn("skin"), btn("esp")],
            [btn("walhack"), btn("heat")],
            [btn("xcode")],
        ]
    )


SUB_TEXT = (
    "❗ Botdan foydalanish uchun avval kanalimizga obuna bo‘ling:\n"
    f"👉 {CHANNEL}\n\nObuna bo‘lgach «✅ Tekshirish» tugmasini bosing."
)
MENU_TEXT = "🔥 <b>ZCSEL CFG BOT</b>\n\nKerakli bo‘limni tanlang:"


@dp.message(CommandStart())
async def start(m: Message):
    if not await is_subscribed(m.from_user.id):
        return await m.answer(SUB_TEXT, reply_markup=sub_kb())
    await m.answer(MENU_TEXT, reply_markup=menu(), parse_mode="HTML")


@dp.callback_query(F.data == "check")
async def check(c: CallbackQuery):
    if not await is_subscribed(c.from_user.id):
        return await c.answer("Siz hali obuna bo‘lmagansiz ❌", show_alert=True)
    await c.answer("Rahmat! ✅")
    try:
        await c.message.delete()
    except Exception:
        pass
    await c.message.answer(MENU_TEXT, reply_markup=menu(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("sec:"))
async def section(c: CallbackQuery):
    if not await is_subscribed(c.from_user.id):
        await c.answer("Avval kanalga obuna bo‘ling ❌", show_alert=True)
        return await c.message.answer(SUB_TEXT, reply_markup=sub_kb())
    key = c.data.split(":", 1)[1]
    if key not in SECTIONS:
        return await c.answer()
    caption = f"{SECTIONS[key][0]}\n\n✅ Fayl tayyor!"

    # 1) Repo ichidagi papka: files/<kalit>/ (Render'da o'chib ketmaydi)
    folder = os.path.join("files", key)
    local = []
    if os.path.isdir(folder):
        local = sorted(
            os.path.join(folder, f) for f in os.listdir(folder)
            if os.path.isfile(os.path.join(folder, f)) and not f.startswith(".")
        )
    if local:
        await c.answer()
        for path in local:
            await c.message.answer_document(FSInputFile(path), caption=caption)
        return

    # 2) /setfile orqali yuklangan fayl
    file_id = load_db().get(key)
    if not file_id:
        return await c.answer("Bu bo‘lim uchun fayl hali yuklanmagan ❌", show_alert=True)
    await c.answer()
    await c.message.answer_document(file_id, caption=caption)


# ---------------- ADMIN ----------------
# Faylni botga yuboring va caption'ga yozing:  /setfile xcode
@dp.message(F.document, F.from_user.id == ADMIN_ID)
async def set_file(m: Message):
    cap = (m.caption or "").strip().split()
    if len(cap) != 2 or cap[0] != "/setfile" or cap[1] not in SECTIONS:
        return await m.answer(
            "Caption: <code>/setfile kalit</code>\nKalitlar: "
            + ", ".join(f"<code>{k}</code>" for k in SECTIONS),
            parse_mode="HTML",
        )
    DB[cap[1]] = m.document.file_id  # eski fayl o'rniga yangisi yoziladi
    await persist_db()
    await m.answer(f"✅ {SECTIONS[cap[1]][0]} uchun fayl yangilandi.")


@dp.message(Command("delfile"), F.from_user.id == ADMIN_ID)
async def del_file(m: Message):
    parts = (m.text or "").split()
    if len(parts) != 2 or (parts[1] not in SECTIONS and parts[1] != "all"):
        return await m.answer("Misol: <code>/delfile xcode</code> yoki "
                              "<code>/delfile all</code>", parse_mode="HTML")
    if parts[1] == "all":
        DB.clear()
    else:
        DB.pop(parts[1], None)
    await persist_db()
    await m.answer("🗑 O‘chirildi.")


@dp.message(Command("files"), F.from_user.id == ADMIN_ID)
async def files_status(m: Message):
    db = load_db()
    await m.answer("\n".join(
        f"{'✅' if k in db else '❌'} {k}" for k in SECTIONS))


async def run_web():
    # Render (Web Service) port ochiq bo'lishini talab qiladi + UptimeRobot uchun
    from aiohttp import web

    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot ishlayapti ✅"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "10000"))).start()


async def main():
    await run_web()
    await restore_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
