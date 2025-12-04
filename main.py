import os
import json
import random
import pytz
from datetime import datetime
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
TOPLAYICI_KANAL = int(os.getenv("TOPLAYICI_KANAL"))
AKTARILAN_KANAL = int(os.getenv("AKTARILAN_KANAL"))

TIMEZONE = pytz.timezone("Europe/Istanbul")

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
    used = load_used()

    messages = await app.bot.get_chat_history(
        chat_id=TOPLAYICI_KANAL,
        limit=300
    )

    available = [m for m in messages if m.message_id not in used]

    if not available:
        return None, None

    msg = random.choice(available)
    return msg.message_id, msg


async def scheduled_send(context: ContextTypes.DEFAULT_TYPE):
    app = context.application

    now = datetime.now(TIMEZONE)
    hour = now.hour

    if not (12 <= hour < 19):
        return

    msg_id, msg = await choose_random_message(app)
    if msg is None:
        return

    await app.bot.copy_message(
        chat_id=AKTARILAN_KANAL,
        from_chat_id=TOPLAYICI_KANAL,
        message_id=msg_id
    )

    used = load_used()
    used.add(msg_id)
    save_used(used)


async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_id, msg = await choose_random_message(context.application)

    if msg_id is None:
        return await update.message.reply_text("Kullanılmamış içerik kalmadı.")

    await update.message.reply_text(
        f"Test modu: Seçilen mesaj ID: {msg_id}\n(Not: Gönderilmedi!)"
    )


async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("test", test))

    # Job queue → her dakika çalışır
    app.job_queue.run_repeating(scheduled_send, interval=60, first=5)

    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
