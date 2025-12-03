import logging
import os
import json
import random
import re
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError

# --- 1. SABİTLER VE ORTAM DEĞİŞKENLERİ ---
# Railway'den bu değişkenleri okuyacak. (Lütfen ayarlayın!)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Kaynak Kanal ID'si (Örn: -1001234567890)
SOURCE_CHANNEL_ID = os.environ.get("SOURCE_CHANNEL_ID")
# Hedef Kanal ID'si (Örn: -1009876543210)
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID") 

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Paylaşılan mesaj ID'lerinin tutulduğu dosya
SHARE_DB_FILE = "shared_messages.json"

# *** ÖNEMLİ: Bu liste, kaynak kanalınızdaki çekilebilecek mesaj ID'lerini temsil eder. ***
# Botunuzun doğru çalışması için, bu listeyi kendi kanalınızdaki mesaj ID'leri ile doldurmalısınız.
# Bot, bu ID'ler arasından rastgele seçim yapacaktır.
ALL_MESSAGE_IDS = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110] # ÖRNEK ID'ler

# --- 2. VERİTABANI İŞLEMLERİ (JSON) ---

def load_shared_messages():
    """Paylaşılan mesaj ID'lerini dosyadan yükler."""
    if not os.path.exists(SHARE_DB_FILE):
        return []
    with open(SHARE_DB_FILE, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return [] # Dosya boş veya bozuksa boş liste döndür

def save_shared_message(message_id):
    """Yeni paylaşılan mesaj ID'sini dosyaya kaydeder."""
    shared_ids = load_shared_messages()
    if message_id not in shared_ids:
        shared_ids.append(message_id)
        with open(SHARE_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(shared_ids, f, indent=4)

# --- 3. İÇERİK TEMİZLEME FONKSİYONU ---

def clean_caption_text(text: str) -> str:
    """Metindeki linkleri ve kullanıcı adlarını siler."""
    if not text:
        return ""

    # 1. Linkler: http/https ile başlayan, www ile başlayan veya basit alan adları
    url_pattern = r'https?://\S+|www\.\S+|\w+\.(com|net|org|io|me|co|tr)'
    # 2. Telegram Kullanıcı Adları: @ işaretiyle başlayanlar
    username_pattern = r'@\w+'

    # Metinden linkleri ve kullanıcı adlarını boşlukla değiştirerek sil
    cleaned_text = re.sub(url_pattern, '', text, flags=re.IGNORECASE)
    cleaned_text = re.sub(username_pattern, '', cleaned_text)
    
    # Birden fazla boşluğu tek boşluğa indir ve baştaki/sondaki boşlukları temizle
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

    return cleaned_text

# --- 4. ANA İŞLEV: İÇERİK TRANSFERİ (Zamanlayıcı Tarafından Çağrılır) ---

# Bu fonksiyon artık ContextTypes yerine sadece Application objesi alacak
# Bu sayede APScheduler ile sorunsuz çalışabilir.
async def transfer_content(application: Application, is_test=False):
    """
    Kaynak kanaldan bir mesajı rastgele seçer, temizler ve hedef kanala gönderir.
    """
    
    # 1. Saat Kontrolü (Test Modu Değilse)
    current_hour = datetime.now().hour
    if not is_test and not (12 <= current_hour < 19):
        logger.info("Şu an saat %d. Paylaşım aralığı (12:00-19:00) dışında. İşlem atlanıyor.", current_hour)
        return

    bot = application.bot
    shared_ids = load_shared_messages()
    
    logger.info("Saat kontrolü başarılı. Mesaj aranıyor...")
    
    unshared_ids = [mid for mid in ALL_MESSAGE_IDS if mid not in shared_ids]

    if not unshared_ids:
        logger.warning("Paylaşılmamış içerik kalmadı!")
        return
        
    # 2. Rastgele Seçim
    message_to_share_id = random.choice(unshared_ids)
    
    try:
        # 3. Mesajı Kopyalama ve Temizleme
        
        # copy_message kullanmak, formatı (resim/video) korur ancak metin temizliği yapmaz.
        # Temizliği yapmak için, ya Telethon gibi daha gelişmiş bir kütüphane kullanılmalı 
        # ya da copy_message'ın 'caption' parametresi kullanılmalıdır.
        
        # Burada BASİT bir temizlik yaklaşımı izliyoruz:
        # Mesajı direkt kopyalayıp, KOPYALADIĞIMIZ metni temizleyip yeniden gönderemeyiz.
        # Bu nedenle, mesajın sadece metnini alıp temizleme ihtimali olmadığı için, 
        # 'caption' metnini geçici bir metinle değiştiriyoruz.
        
        # EN İYİ ÇÖZÜM: Kaynak kanaldan mesajı çekin (get_message), caption'ı temizleyin, sonra gönderin.
        # Ancak python-telegram-bot, 'get_message' metodunu kolayca sağlamaz.
        # Bu nedenle, mesajı 'copy_message' ile kopyalıyoruz ve caption'a manuel temiz bir metin ekliyoruz.
        
        # Gerçek metin temizliği için, kaynak kanala admin olarak eklediğiniz 
        # bu bot ile mesajı çekip metnini temizleyip yeniden göndermek gerekir.
        
        # Basitleştirilmiş kopyalama:
        await bot.copy_message(
            chat_id=TARGET_CHANNEL_ID,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_id=message_to_share_id,
            # Link ve kullanıcı adlarını temizlemek için caption'ı varsayılan bir metinle geçersiz kılıyoruz.
            # *NOT: Bu, orijinal caption'ı kaybeder ancak linklerin geçmesini engeller.*
            caption="Yeni bir içerik paylaşıldı!", 
        )
        
        # 4. Başarılı İşlem Sonrası Kayıt
        save_shared_message(message_to_share_id)
        logger.info("Mesaj ID %d, kanala başarıyla kopyalandı.", message_to_share_id)

    except Exception as e:
        logger.error("Mesaj ID %d kopyalanırken hata oluştu: %s", message_to_share_id, e)
        # Hata kodu 400 (Bad Request) alırsanız, ya mesaj silinmiştir ya da botun yetkisi yoktur.


# --- 5. TELEGRAM KOMUTLARI (TEST MODU) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bota /start komutu ile ilk mesajı gönderir."""
    await update.message.reply_text(
        "🤖 Bot başlatıldı ve zamanlayıcı kuruldu.\n"
        "⏰ Paylaşım saatleri: **12:00 - 19:00** arası.\n"
        "🧪 Test modu için: `/test_paylasim`"
    )

async def test_paylasim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/test_paylasim komutu ile hemen bir paylaşım denemesi yapar."""
    await update.message.reply_text("Test paylaşımı başlatılıyor. Lütfen hedef kanalı kontrol edin...")
    
    # Test Modunda, is_test=True olarak ana fonksiyonu çağır
    await transfer_content(context.application, is_test=True)
    
    await update.message.reply_text("Test paylaşım işlemi tamamlandı.")


# --- 6. ZAMANLAYICI BAŞLATMA ---

def start_scheduler(application: Application):
    """APScheduler'ı kurar ve paylaşım görevini ekler."""
    
    # Daha önce kurulan bir zamanlayıcı varsa kaldır (Railway'de tekrar dağıtımda sorun yaşanmasını önler)
    if not hasattr(application, 'scheduler'):
        application.scheduler = AsyncIOScheduler()
    else:
        # Mevcut işleri temizle
        application.scheduler.remove_all_jobs() 

    # Her saat başı (örneğin .00'da) çalışacak görevi ekle.
    application.scheduler.add_job(
        transfer_content, 
        'cron', 
        hour='12-18', # Saat 12:00'dan başlayıp, 18:00'da son kez çalışacak
        minute=0, 
        # application objesini argüman olarak geçiyoruz.
        args=[application], 
        id='hourly_transfer', # İş için benzersiz bir ID tanımlıyoruz
        replace_existing=True
    )
    
    logger.info("Zamanlayıcı başlatıldı. Görev her saat başı 12:00-18:00 arasında çalışacak.")
    if not application.scheduler.running:
        application.scheduler.start()


# --- 7. ANA ÇALIŞTIRMA FONKSİYONU ---

def main():
    """Botu çalıştırır."""
    if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_CHANNEL_ID:
        logger.error("❌ Ortam değişkenleri (BOT_TOKEN, SOURCE_CHANNEL_ID, TARGET_CHANNEL_ID) ayarlanmamış.")
        logger.error("Lütfen Railway/Ortam Değişkenleri bölümünde bu değerleri ayarlayın.")
        return

    # Uygulama oluşturma
    application = Application.builder().token(BOT_TOKEN).build()

    # Komut işleyicileri
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("test_paylasim", test_paylasim_command))

    # Zamanlayıcıyı başlat
    start_scheduler(application)

    # Botu sürekli çalıştır (Railway için bu gereklidir)
    logger.info("✅ Bot çalışıyor...")
    application.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()
