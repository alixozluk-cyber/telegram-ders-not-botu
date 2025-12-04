import os
import json
import random
import pytz
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

# ------------ ENV DEĞERLERİ ------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
TOPLAYICI_KANAL = int(os.getenv("TOPLAYICI_KANAL"))
AKTARILAN_KANAL = int(os.getenv("AKTARILAN_KANAL"))
TIMEZONE = pytz.timezone("Europe/Istanbul")
# ----------------------------------------

USED_FILE = "data/used_messages.json"

def load_used():
    """Kullanılmış mesaj ID’lerini yükler."""
    try:
        with open(USED_FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_used(used):
    """Kullanılmış mesajları kaydeder."""
    with open(USED_FILE, "w") as f:
        json.dump(list(used), f)


async def choose_random_message(app):
    """Toplayıcı kanaldan rastgele kullanılmamış bir mesaj seç."""
    used = load_used()

    # Kanal geçmişini çek
    messages = await app.bot.get_chat_history(
        chat_id=TOPLAYICI_KANAL,
        limit=300
    )

    # Kullanılmamış mesajları filtrele
    available = [m for m in messages if m.message_id not in used]

    if not available:
        return None, None

    msg = random.choice(available)
    return msg.message_id, msg


async def send_random_content(app):
    """Saat 12–19 arasında içerik gönder."""
    now = datetime.now(TIMEZONE)
    hour = now.hour

    # Saat kontrolü
    if hour < 12 or hour >= 19:
        return

    msg_id, msg = await choose_random_message(app)
    if msg is None:
        return

    # Mesajı hedef kanala kopyala
    await app.bot.copy_message(
        chat_id=AKTARILAN_KANAL,
        from_chat_id=TOPLAYICI_KANAL,
        message_id=msg_id
    )

    # Kullanıldı olarak işaretle
    used = load_used()
    used.add(msg_id)
    save_used(used)


# ------------ KOMUT: TEST ------------

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test modu → içerik seçer ama göndermeden ID’yi gösterir."""
    msg_id, _ = await choose_random_message(context.application)

    if msg_id is None:
        return await update.message.reply_text("Kullanılmamış içerik kalmadı.")

    await update.message.reply_text(f"Test → rastgele seçilen mesaj ID: {msg_id}\n(Not: Kanala gönderilmedi.)")


# ------------ ANA ÇALIŞMA ------------

async def scheduler(app):
    """Railway sürekli çalıştığı için burada döngü ile kontrol sağlıyoruz."""
    import asyncio
    while True:
        await send_random_content(app)
        await asyncio.sleep(60)  # her 1 dakikada bir kontrol


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Komut handler
    app.add_handler(CommandHandler("test", test))

    # Arka plan görevini başlat
    import asyncio
    asyncio.create_task(scheduler(app))

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
