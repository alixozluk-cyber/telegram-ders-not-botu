import logging
import os
import json
import random
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- 1. AYARLAR VE LOGLAMA ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SOURCE_CHANNEL_ID = os.environ.get("SOURCE_CHANNEL_ID")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID") 

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

SHARE_DB_FILE = "shared_messages.json"

# *** Kendi mesaj ID'lerinizi buraya ekleyin! ***
ALL_MESSAGE_IDS = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110] 

# --- 2. VERİTABANI İŞLEMLERİ (JSON) ---

def load_shared_messages():
    if not os.path.exists(SHARE_DB_FILE):
        return []
    with open(SHARE_DB_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_shared_message(message_id):
    shared_ids = load_shared_messages()
    if message_id not in shared_ids:
        shared_ids.append(message_id)
        with open(SHARE_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(shared_ids, f, indent=4)

# --- 3. İÇERİK TEMİZLEME FONKSİYONU ---

def get_cleaned_caption_text() -> str:
    """Temizlenmiş, sabit bir başlık döndürür."""
    # Orijinal metni kopyalayıp temizlemek teknik olarak zor olduğu için,
    # link/kullanıcı adı içermeyen yeni, sabit bir uyarı başlığı gönderiyoruz.
    return "✅ Temizlenmiş İçerik: Orijinal linkler ve kullanıcı adları kaldırıldı."


# --- 4. ANA İŞLEV: İÇERİK TRANSFERİ (Link Temizleme Eklendi) ---

async def transfer_content_simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /test komutu ile çağrıldığında, rastgele bir mesajı kopyalar ve başlığını temizler.
    """
    
    await update.message.reply_text("Test transferi başlatılıyor...")
    
    shared_ids = load_shared_messages()
    unshared_ids = [mid for mid in ALL_MESSAGE_IDS if mid not in shared_ids]

    if not unshared_ids:
        await update.message.reply_text("Paylaşılmamış içerik kalmadı!")
        return
        
    message_to_share_id = random.choice(unshared_ids)
    
    try:
        # Mesajı kopyalama ve yeni, temizlenmiş bir başlık gönderme
        await context.bot.copy_message(
            chat_id=TARGET_CHANNEL_ID,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_id=message_to_share_id,
            # *** LINK TEMİZLEME ÇÖZÜMÜ: Caption'ı yeni, temiz bir metinle geçersiz kılıyoruz. ***
            caption=get_cleaned_caption_text(), 
        )
        
        save_shared_message(message_to_share_id)
        logger.info("Mesaj ID %d, kanala başarıyla kopyalandı.", message_to_share_id)
        await update.message.reply_text(f"✅ Mesaj ID {message_to_share_id} başarıyla kopyalandı ve başlık temizlendi.")

    except Exception as e:
        logger.error("Mesaj kopyalanırken hata oluştu: %s", e)
        await update.message.reply_text(f"❌ Kopyalama hatası: {e}. Botun kanal admin yetkilerini kontrol edin.")


# --- 5. ANA ÇALIŞTIRMA FONKSİYONU ---

def main():
    """Botu çalıştırır."""
    if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_CHANNEL_ID:
        logger.error("❌ Ortam değişkenleri ayarlanmamış.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Komut işleyicileri
    application.add_handler(CommandHandler("test", transfer_content_simple))
    application.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text("Bot hazır. Transferi denemek ve link temizliğini test etmek için /test komutunu kullanın.")))

    logger.info("✅ Minimal Bot (Link Temizleme Aktif) çalışıyor...")
    application.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()
    
