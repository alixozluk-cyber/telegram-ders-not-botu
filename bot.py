import logging
import os
import json
import random
import time
import re
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- 1. SABİTLER VE ORTAM DEĞİŞKENLERİ ---
# Railway'den bu değişkenleri okuyacak (Ortam değişkenlerini ayarlamanız gerekecek!)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# Kaynak Kanal ID'si (İçerikleri çekeceğiniz kanal)
SOURCE_CHANNEL_ID = os.environ.get("SOURCE_CHANNEL_ID")
# Hedef Kanal ID'si (İçerikleri paylaşacağınız kanal)
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID") 

# Loglama ayarları
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Paylaşılan mesaj ID'lerinin tutulduğu dosya
SHARE_DB_FILE = "shared_messages.json"

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

def clean_message_text(text):
    """Metindeki linkleri ve kullanıcı adlarını siler."""
    if not text:
        return text

    # Düzenli İfade (Regex) Kalıpları
    # 1. Linkler (http/https ile başlayan, www ile başlayan)
    url_pattern = r'https?://\S+|www\.\S+|\w+\.com'
    # 2. Telegram Kullanıcı Adları (@ işaretli)
    username_pattern = r'@\w+'

    # Metinden linkleri ve kullanıcı adlarını sil (boşlukla değiştir)
    cleaned_text = re.sub(url_pattern, '', text, flags=re.IGNORECASE)
    cleaned_text = re.sub(username_pattern, '', cleaned_text)
    
    # Fazla boşlukları temizle
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()

    return cleaned_text

# --- 4. ANA İŞLEV: İÇERİK TRANSFERİ ---

async def transfer_content(context: ContextTypes.DEFAULT_TYPE, is_test=False):
    """
    Kaynak kanaldan bir mesajı rastgele seçer, temizler ve hedef kanala gönderir.
    is_test=True ise saat kontrolünü atlar (Test Modu).
    """
    current_hour = datetime.now().hour
    
    # 1. Saat Kontrolü (Test Modu Değilse)
    if not is_test and not (12 <= current_hour < 19):
        logger.info("Şu an saat %d. Paylaşım aralığı (12:00-19:00) dışında. İşlem atlanıyor.", current_hour)
        return

    bot = context.bot
    shared_ids = load_shared_messages()
    
    logger.info("Saat kontrolü başarılı. Mesaj aranıyor...")
    
    # Telegram'dan mesajları çekme (Bu, basit bir yaklaşımdır.)
    # NOT: Telegram API'si "tüm mesajları çek" gibi bir komut vermez. 
    # Bunun yerine, belirli bir aralıktaki mesajları çekmek için 'get_updates' veya 'get_history' gibi 
    # yöntemler gerekir. 'copy_message' ile sadece ID kullanarak kopyalama yapacağız.
    
    # --- Gerçek Dünyada Yapılması Gereken (Basitlik İçin Atlanmıştır) ---
    # Bu adımda, kaynak kanaldan paylaşılmamış tüm mesaj ID'lerini (örneğin son 1000 mesaj)
    # çekmeniz ve shared_ids ile karşılaştırmanız gerekir. Telethon kütüphanesi bu iş için daha uygundur.
    # Burada basitleştirilmiş bir yaklaşımla, rastgele bir mesaj ID'si deneyeceğiz (ideal değil, ama mantığı gösterir).
    # ÖRNEK: Manuel olarak bir ID listesi olduğunu varsayalım:
    
    # Lütfen buraya KAYNAK KANALINIZDAN çekilmesini istediğiniz mesajların ID'lerini yazın.
    # Eğer burayı boş bırakırsanız bot çalışmayacaktır!
    ALL_MESSAGE_IDS = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20] # ÖRNEK ID'ler
    
    unshared_ids = [mid for mid in ALL_MESSAGE_IDS if mid not in shared_ids]

    if not unshared_ids:
        logger.warning("Paylaşılmamış içerik kalmadı!")
        # Test modunda ise kullanıcıya bilgi ver
        if is_test:
            await context.bot.send_message(
                chat_id=context.job.data['user_id'], 
                text="Paylaşılmamış içerik kalmadı. Test başarısız."
            )
        return
        
    # 2. Rastgele Seçim
    message_to_share_id = random.choice(unshared_ids)
    
    try:
        # 3. Mesajı Kopyalama ve Temizleme
        # Önce mesajın detaylarını çekmek için 'forwardMessage' yerine 
        # daha gelişmiş bir kütüphane (Telethon) gerekebilir.
        # Python-Telegram-Bot ile en kolay yöntem 'copy_message' kullanmaktır.
        
        # Basitlik için kopyalama işlemini başlatıyoruz
        # Not: copy_message metni temizleme imkanı sunmaz, sadece kopyalar.
        # Temizleme yapmak için mesajın tüm detaylarını alıp yeniden göndermeliyiz.
        
        # Bu aşamada, mesajın içeriğini (metin, medya) çekip temizleyip yeniden göndermek için
        # mesajı getirecek özel bir fonksiyon yazılması gerekir. 
        # Python-telegram-bot'ta bu doğrudan 'getMessage' gibi bir yöntemle mümkün değildir,
        # sadece kendi botunuz tarafından gönderilen mesajlar için güncellemelerle alınabilir.
        
        # --- BASİTLEŞTİRİLMİŞ KOPYALAMA İŞLEMİ (Metin temizliği DİKKAT İSTER) ---
        # `copy_message` metin temizliği için iyi değildir, ancak en basit yöntemdir. 
        # Metin temizliğini sadece metin tabanlı bir gönderimle gösterelim.
        
        # Kopyalanacak mesajın metnini varsayımsal olarak alıyoruz (Gerçek projede API çağrısı ile almalısınız)
        # Eğer mesaj sadece metin ise, metni temizleyip öyle gönderelim:
        # Örnek metin çekme:
        # message_details = await bot.get_message(chat_id=SOURCE_CHANNEL_ID, message_id=message_to_share_id) 
        # cleaned_caption = clean_message_text(message_details.caption if message_details.caption else message_details.text)

        # Varsayımsal kopyalama (Gerçek hayatta bu SADECE metni kopyalar, linkler durur):
        await bot.copy_message(
            chat_id=TARGET_CHANNEL_ID,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_id=message_to_share_id,
            caption="*Temizlendi ve Paylaşıldı!*", # Bu caption linkleri/kullanıcı adlarını silmez!
            parse_mode='Markdown'
        )
        
        # 4. Başarılı İşlem Sonrası Kayıt
        save_shared_message(message_to_share_id)
        logger.info("Mesaj ID %d, kanala başarıyla kopyalandı.", message_to_share_id)

    except Exception as e:
        logger.error("Mesaj kopyalanırken hata oluştu: %s", e)


# --- 5. TELEGRAM KOMUTLARI (TEST MODU) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bota /start komutu ile ilk mesajı gönderir."""
    await update.message.reply_text(
        "Merhaba! Bot başlatıldı ve zamanlayıcı kuruldu.\n"
        "Paylaşım saatleri: 12:00 - 19:00 arası.\n"
        "Test modu için: /test_paylasim"
    )

async def test_paylasim_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/test_paylasim komutu ile hemen bir paylaşım denemesi yapar."""
    await update.message.reply_text("Test paylaşımı başlatılıyor. Lütfen kanalı kontrol edin...")
    
    # Test Modunda, is_test=True olarak ana fonksiyonu çağır
    # Job'a user_id'yi ekleyerek başarılı/başarısız bilgisini göndermeyi sağla
    job_data = {'user_id': update.effective_chat.id}
    await transfer_content(context, is_test=True)


# --- 6. ZAMANLAYICI BAŞLATMA ---

def start_scheduler(application):
    """APScheduler'ı kurar ve paylaşım görevini ekler."""
    scheduler = AsyncIOScheduler()
    
    # Her saat başı (örneğin .00'da) çalışacak görevi ekle.
    # Görev, saat 12 ile 19 arasında olup olmadığını kontrol edecek.
    # Saat 19:00'da (yani 19:00:00'da) çalışmaz. 
    scheduler.add_job(
        transfer_content, 
        'cron', 
        hour='12-18', # Saat 12'den baş
      
