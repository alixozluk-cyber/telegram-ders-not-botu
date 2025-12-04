import json
import random
import pytz
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

# ------------ AYARLAR ------------
BOT_TOKEN = "BURAYA_TOKEN"
TOPLAYICI_KANAL = -100123456789   # içeriklerin olduğu kanal
AKTARILAN_KANAL = -100987654321   # botun göndereceği kanal
TIMEZONE = pytz.timezone("Europe/Istanbul")
# ---------------------------------

USED_FILE = "data/used_messages.json"

def load_used():
    try:
        with open(USED_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_used(used):
    with open(USED_FILE, "w") as f:
        json.dump(list(used), f)


async def choose_random_message(app):
    """Toplayıcı kanaldan rastgele kullanılmamış mesaj getirir."""
    used = load_used()

    # Kanal mesajlarını getir
    messages = await app.bot.get_chat_history(
        chat_id=TOPLAYICI_KANAL,
        limit=300
    )

    available = [m for m in messages if m.message_id not in used]

    if not available:
        return None, None

    msg = random.choice(available)
    return msg.message_id, msg


async def send_random_content(app):
    """Saat uygunsa rastgele 1 içerik gönderir."""
    now = datetime.now(TIMEZONE)
    hour = now.hour

    if hour < 12 or hour >= 19:
        return  # gönderme

    msg_id, msg = await choose_random_message(app)
    if msg is None:
        return

    # Mesajı hedef kanala kopyala
    await app.bot.copy_message(
        chat_id=AKTARILAN_KANAL,
        from_chat_id=TOPLAYICI_KANAL,
        message_id=msg_id
    )

    used = load_used()
    used.add(msg_id)
    save_used(used)


# ------------ KOMUTLAR ------------

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test modu → rastgele içerik getirir ama göndermeden sana gösterir."""
    msg_id, msg = await choose_random_message(context.application)

    if msg is None:
        return await update.message.reply_text("Kullanılmamış içerik kalmadı.")

    await update.message.reply_text(f"Test: Seçilen mesaj ID = {msg_id}\n(gerçek kanala gönderilmedi)")


# ------------ MAIN ------------

async def scheduler(app):
    """Railway sürekli çalıştırdığı için burada döngü kuruyoruz."""
    import asyncio
    while True:
        await send_random_content(app)
        await asyncio.sleep(60)   # Her 1 dakikada bir kontrol


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("test", test))

    # Arka planda planlayıcı çalışsın
    import asyncio
    asyncio.create_task(scheduler(app))

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
