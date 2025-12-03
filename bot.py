import logging
import os
import json
import random
import re
from datetime import datetime, time
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, JobQueue

# --- 1. AYARLAR VE LOGLAMA ---
# Railway'den ortam değişkenlerini oku (Değerler atanmış olmalı!)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SOURCE_CHANNEL_ID = os.environ.get("SOURCE_CHANNEL_ID")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID") 

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

SHARE_DB_FILE = "shared_messages.json"

# *** ÖNEMLİ: Kendi mesaj ID'lerinizle doldurun! ***
ALL_MESSAGE_IDS = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110] 

# --- 2. VERİTABANI İŞLEMLERİ (JSON) ---

def load_shared_messages():
    """Paylaşılan mesaj ID'lerini yükler."""
    if not os.path.exists(SHARE_DB_FILE):
        return []
    with open(SHARE_DB_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_shared_message(message_id):
    """Yeni paylaşılan mesaj ID'sini kaydeder."""
    shared_ids = load_shared_messages()
    if message_id not in shared_ids:
        shared_ids.append(message_id)
        with open(SHARE_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(shared_ids, f, indent=4)

# --- 3. İÇERİK TEMİZLEME FONKSİYONU (Basit hali) ---

def clean_caption_text(text: str) -> str:
    """Metindeki linkleri ve kullanıcı adlarını siler ve yeni caption oluşturur."""
    if not text:
        return "Yeni bir içerik paylaşıldı."

    url_pattern = r'https?://\S+|www\.\S+|\w+\.(com|net|org|io|me|co|tr)'
    username_pattern = r'@\w+'

    cleaned_text = re.sub(url_pattern, '', text, flags=re.IGNORECASE)
    cleaned_text = re.sub(username_pattern, '', cleaned_text)
    
    final_caption = re.sub(r'\s+', ' ', cleaned_text).strip()
    return final_caption + "\n\n(Bot tarafından temizlenmiştir.)"


# --- 4. ANA İŞLEV: İÇERİK TRANSFERİ ---

async def transfer_content(context: ContextTypes.DEFAULT_TYPE, is_test=False):
    """
    Kaynak kanaldan bir mesajı rastgele seçer, temizler ve hedef kanala gönderir.
    Bu fonksiyon artık hem zamanlayıcı hem de test modu tarafından çağrılabilir.
    """
    
    # Zamanlayıcıdan geliyorsa ve test modu değilse saat kontrolü yap
    if not is_test:
        current_time = datetime.now().time()
        # 12:00:00 ile 18:59:59 arası kontrol
        if not (time(12, 0) <= current_time < time(19, 0)):
            logger.info("Saat kontrolü: %s. Paylaşım aralığı (12:00-19:00) dışında.", current_time.strftime('%H:%M'))
            return

    bot = context.bot
    shared_ids = load_shared_messages()
    logger.info("Mesaj aranıyor... Test modu: %s", is_test)
    
    unshared_ids = [mid for mid in ALL_MESSAGE_IDS if mid not in shared_ids]

    if not unshared_ids:
        logger.warning("Paylaşılmamış içerik kalmadı!")
        return
        
    message_to_share_id = random.choice(unshared_ids)
    
    try:
        # copy_message, orijinal mesajın metnini/başlığını *elde etmemize* izin vermez.
        # Bu nedenle, sadece temizlenmiş bir *yeni* başlık gönderiyoruz.
        
        await bot.copy_message(
            chat_id=TARGET_CHANNEL_ID,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_id=message_to_share_id,
            # NOT: Temizleme, orijinal metin yerine yeni, statik bir caption göndererek garanti altına alınır.
            caption="Yeni bir içerik paylaşıldı! (Linkler ve kullanıcı adları silinmiştir)", 
        )
        
        save_shared_message(message_to_share_id)
        logger.info("Mesaj ID %d, kanala başarıyla kopyalandı.", message_to_share_id)

    except Exception as e:
        logger.error("Mesaj ID %d kopyalanırken hata oluştu: %s", message_to_share_id, e)

# --- 5. TELEGRAM KOMUTLARI (TEST MODU) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot başlatıldı ve zamanlayıcı (dakikalık kontrol) kuruldu.\n"
        "⏰ Paylaşım saatleri: **12:00 - 19:00** arası.\n"
        "🧪 Test modu için: `/test_paylasim`"
    )

async def test_paylasim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Test paylaşımı başlatılıyor. Lütfen hedef kanalı kontrol edin...")
    # is_test=True olarak ana fonksiyonu çağır
    await transfer_content(context, is_test=True)
    await update.message.reply_text("Test paylaşım işlemi tamamlandı.")


# --- 6. ZAMANLAYICI BAŞLATMA (JobQueue ile) ---

def start_job_queue(application: Application):
    """Her dakika çalışacak işi (JobQueue) kurar."""
    
    job_queue: JobQueue = application.job_queue
    
    # 1. Önceki işi kaldır (Yeniden dağıtımda hata vermesini engeller)
    if job_queue.get_jobs_by_name("hourly_transfer_checker"):
        job_queue.get_jobs_by_name("hourly_transfer_checker")[0].schedule_removal()

    # 2. Her dakika çalışacak işi ekle
    job_queue.run_repeating(
        callback=transfer_content, 
        interval=60, # 60 saniyede (1 dakikada) bir çalıştır
        first=0, # Bot başlar başlamaz çalıştır
        name="hourly_transfer_checker",
    )
    
    logger.info("Dakikalık zamanlayıcı (JobQueue) kuruldu. Her dakika saat kontrolü yapılacak.")


# --- 7. ANA ÇALIŞTIRMA FONKSİYONU ---

def main():
    """Botu çalıştırır."""
    if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_CHANNEL_ID:
        logger.error("❌ Ortam değişkenleri ayarlanmamış.")
        return

    # Uygulama oluşturma
    application = Application.builder().token(BOT_TOKEN).build()

    # Komut işleyicileri
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("test_paylasim", test_paylasim_command))

    # Zamanlayıcıyı başlat
    start_job_queue(application)

    logger.info("✅ Bot çalışıyor ve Polling başlıyor...")
    # Polling başlatılıyor. Bu, botun sürekli çalışmasını ve JobQueue'nun tetiklenmesini sağlar.
    application.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()
                  
