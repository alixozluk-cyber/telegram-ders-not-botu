import logging
import os
import json
import random
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- 1. AYARLAR VE LOGLAMA ---
# Railway'den ortam değişkenlerini oku
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SOURCE_CHANNEL_ID = os.environ.get("SOURCE_CHANNEL_ID")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID") 

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

SHARE_DB_FILE = "shared_messages.json"

# *** ÇÖZÜM: Global zamanlayıcı tek bir yerde tanımlanır. (AttributeError'ı çözer) ***
global_scheduler = AsyncIOScheduler()

# *** Lütfen burayı kendi kanalınızdaki mesaj ID'leriyle doldurun! ***
# Bot, bu ID'ler arasından rastgele seçecektir.
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

# --- 3. İÇERİK TEMİZLEME FONKSİYONU ---
# Bu fonksiyon, basitlik ve çalışma önceliği için şu an sadece uyarı amaçlı kullanılacaktır.

def get_cleaned_caption(original_caption: str) -> str:
    """Metindeki linkleri ve kullanıcı adlarını siler ve yeni caption oluşturur."""
    if not original_caption:
        return "Yeni bir içerik paylaşıldı."

    # Linkleri ve kullanıcı adlarını tespit eden Regex
    url_pattern = r'https?://\S+|www\.\S+|\w+\.(com|net|org|io|me|co|tr)'
    username_pattern = r'@\w+'

    # Linkleri ve kullanıcı adlarını temizle (boşlukla değiştir)
    cleaned_text = re.sub(url_pattern, '', original_caption, flags=re.IGNORECASE)
    cleaned_text = re.sub(username_pattern, '', cleaned_text)
    
    # Fazla boşlukları temizle ve bir uyarı ekle
    final_caption = re.sub(r'\s+', ' ', cleaned_text).strip()
    return final_caption + "\n\n(Bu içerik, bot tarafından temizlenerek yeniden paylaşıldı.)"

# --- 4. ANA İŞLEV: İÇERİK TRANSFERİ ---

async def transfer_content(application: Application, is_test=False):
    """
    Kaynak kanaldan bir mesajı rastgele seçer, temizler ve hedef kanala gönderir.
    """
    current_hour = datetime.now().hour
    # Saati 12:00'dan 18:59'a kadar kontrol eder
    if not is_test and not (12 <= current_hour < 19):
        logger.info("Saat kontrolü: %d. Paylaşım aralığı (12:00-19:00) dışında.", current_hour)
        return

    bot = application.bot
    shared_ids = load_shared_messages()
    logger.info("Mesaj aranıyor... Test modu: %s", is_test)
    
    unshared_ids = [mid for mid in ALL_MESSAGE_IDS if mid not in shared_ids]

    if not unshared_ids:
        logger.warning("Paylaşılmamış içerik kalmadı!")
        return
        
    message_to_share_id = random.choice(unshared_ids)
    
    try:
        # Mesaj detaylarını alma (copy_message metni temizlemek için yeterli değil)
        # Bu kısım, kopyalanan mesajın metnini/başlığını *elde edemediğimiz* için 
        # sadece temizlenmiş bir *yeni* başlık göndermeye odaklanıyor.
        
        # Orijinal mesaj başlığını (caption/text) çekmek için daha karmaşık yöntemler
        # gerektiğinden, botun çalışırlığını sağlamak için basit bir caption gönderiyoruz.
        
        await bot.copy_message(
            chat_id=TARGET_CHANNEL_ID,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_id=message_to_share_id,
            caption="Yeni bir içerik paylaşıldı! (Linkler ve kullanıcı adları silinmiştir)", 
        )
        
        save_shared_message(message_to_share_id)
        logger.info("Mesaj ID %d, kanala başarıyla kopyalandı.", message_to_share_id)

    except Exception as e:
        logger.error("Mesaj ID %d kopyalanırken hata oluştu: %s", message_to_share_id, e)

# --- 5. TELEGRAM KOMUTLARI (TEST MODU) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot başlatıldı ve zamanlayıcı kuruldu.\n"
        "⏰ Paylaşım saatleri: **12:00 - 19:00** arası.\n"
        "🧪 Test modu için: `/test_paylasim`"
    )

async def test_paylasim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Test paylaşımı başlatılıyor. Lütfen hedef kanalı kontrol edin...")
    await transfer_content(context.application, is_test=True)
    await update.message.reply_text("Test paylaşım işlemi tamamlandı.")


# --- 6. ZAMANLAYICI BAŞLATMA ---

def start_scheduler(application: Application):
    """APScheduler'ı kurar ve paylaşım görevini global zamanlayıcıya ekler."""
    
    # Önceki işleri temizle (Yeniden başlatma döngüsü ve RuntimeError çözümü için)
    global_scheduler.remove_all_jobs() 

    # *** SyntaxError'ı önlemek için add_job çağrısı en sade şekilde. ***
    global_scheduler.add_job(
        transfer_content, 
        'cron', 
        hour='12-18', 
        minute=0, 
        args=[application], 
        id='hourly_transfer', 
        replace_existing=True
    )
    
    logger.info("Zamanlayıcı görev eklendi: Her saat başı 12:00-18:00 arası.")
    
    # Zamanlayıcıyı başlat
    if not global_scheduler.running:
        global_scheduler.start()
        logger.info("Zamanlayıcı başlatıldı.")


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
    start_scheduler(application)

    logger.info("✅ Bot çalışıyor ve Polling başlıyor...")
    # Polling başlatılıyor. Bu, asyncio event loop'unu çalıştırır (RuntimeError'ı çözer).
    application.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()
        
