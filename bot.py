import logging
import os
import random
import datetime
from sqlalchemy.sql.expression import func

from telegram import Bot
from telegram.ext import Application, MessageHandler, filters, CommandHandler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import init_db, SessionLocal, Content

# --- Yapılandırma ---
# Bot token'ı ortam değişkeninden okuyun (Railway'de ayarlayacağınız yer)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN") 

# Kanal ID'lerinizi buraya yazın veya ortam değişkenlerinden okuyun
# NEGATIF ID KULLANILMALIDIR, Örn: -100123456789
COLLECTOR_CHANNEL_ID = -123456789012  # İçeriklerin atıldığı kanal ID'si
TARGET_CHANNEL_ID = -987654321098  # İçeriklerin aktarılacağı kanal ID'si

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Zamanlanmış Görev ---

def scheduled_poster(bot: Bot):
    """
    Belirtilen saat aralığında (12:00-19:00) rastgele bir içerik paylaşır.
    """
    now = datetime.datetime.now()
    # 12:00 (dahil) ile 19:00 (hariç) arasında kontrol
    if now.hour < 12 or now.hour >= 19:
        logger.info("Şu an paylaşım saati (12:00-19:00) dışında. Atlanıyor.")
        return

    db = SessionLocal()
    try:
        # Rastgele, kullanılmamış bir içerik seçin
        # .order_by(func.random()) ile rastgele seçim yapılır
        ready_content = db.query(Content).filter(Content.is_used == False).order_by(func.random()).first()

        if ready_content:
            message_id_to_forward = ready_content.collector_message_id
            
            # Mesajı hedef kanala ilet
            bot.forward_message(
                chat_id=TARGET_CHANNEL_ID,
                from_chat_id=COLLECTOR_CHANNEL_ID,
                message_id=message_id_to_forward
            )
            
            # İçeriğin durumunu 'Kullanıldı' olarak güncelle
            ready_content.is_used = True
            db.commit()
            logger.info(f"Başarılı aktarım: Mesaj ID {message_id_to_forward}. Artık kullanıldı.")
        else:
            logger.info("Aktarılmaya hazır içerik kalmadı.")

    except Exception as e:
        db.rollback()
        logger.error(f"Zamanlanmış paylaşım hatası: {e}")
    finally:
        db.close()

# --- Telegram İşleyicileri ---

async def collect_content(update, context):
    """
    Toplayıcı kanaldan gelen her mesajı (metin, fotoğraf, video, vb.) veritabanına kaydeder.
    Botun sadece toplayıcı kanala gönderilen mesajları işlemesi için filtre kullanıldı.
    """
    message = update.effective_message
    
    # Sadece Toplayıcı Kanaldan gelen mesajları işle
    if message.chat_id != COLLECTOR_CHANNEL_ID:
        return

    # Sadece yeni mesajları kaydet, veritabanında zaten varsa atla (unique constraint)
    db = SessionLocal()
    try:
        new_content = Content(collector_message_id=message.message_id, is_used=False)
        db.add(new_content)
        db.commit()
        logger.info(f"Toplanan yeni içerik kaydedildi. Mesaj ID: {message.message_id}")
    except Exception as e:
        # Zaten varsa (unique constraint hatası) veya başka bir hata oluşursa
        db.rollback()
        logger.warning(f"İçerik kaydetme hatası (muhtemelen zaten var): {e}")
    finally:
        db.close()

async def test_mode(update, context):
    """
    /test komutu: Saat kısıtlamasına bakmadan hemen rastgele bir içerik paylaşır.
    """
    # Komutu gönderen kullanıcının botu yönetmeye yetkili olduğundan emin olun!
    # Güvenlik için, bu komutu sadece kendi ID'nizin çalıştırmasını sağlayabilirsiniz.
    
    db = SessionLocal()
    try:
        # Rastgele, kullanılmamış bir içerik seçin
        ready_content = db.query(Content).filter(Content.is_used == False).order_by(func.random()).first()

        if ready_content:
            message_id_to_forward = ready_content.collector_message_id
            
            # Mesajı hedef kanala ilet
            await context.bot.forward_message(
                chat_id=TARGET_CHANNEL_ID,
                from_chat_id=COLLECTOR_CHANNEL_ID,
                message_id=message_id_to_forward
            )
            
            # İçeriğin durumunu 'Kullanıldı' olarak güncelle
            ready_content.is_used = True
            db.commit()
            
            response_text = f"✅ Test başarılı: İçerik (ID: {message_id_to_forward}) hemen aktarıldı ve 'kullanıldı' olarak işaretlendi."
        else:
            response_text = "⚠️ Test başarısız: Aktarılmaya hazır (kullanılmamış) içerik kalmadı."
            
        await update.message.reply_text(response_text)

    except Exception as e:
        db.rollback()
        logger.error(f"/test komutu hatası: {e}")
        await update.message.reply_text(f"❌ Bir hata oluştu: {e}")
    finally:
        db.close()


def main():
    """Botu başlatır ve işleyicileri kaydeder."""
    
    # Veritabanını başlat
    init_db()

    # Uygulamayı oluştur
    application = Application.builder().token(BOT_TOKEN).build()

    # Zamanlayıcıyı kur
    scheduler = BackgroundScheduler()
    # Her 30 dakikada bir çalışacak CronTrigger (12:00-19:00 arası her yarım saat)
    # Örn: Saat 12:00, 12:30, 13:00, ..., 18:30'da çalışır
    trigger = CronTrigger(hour='12-18', minute='0,30')
    
    # Zamanlanmış işi ekle
    scheduler.add_job(
        scheduled_poster, 
        trigger, 
        args=[application.bot], 
        name='Random Scheduled Poster'
    )
    scheduler.start()
    logger.info("Zamanlayıcı başlatıldı.")

    # İşleyicileri kaydet
    # Toplayıcı kanaldan gelen her türlü yeni mesajı yakalar
    application.add_handler(MessageHandler(filters.Chat(COLLECTOR_CHANNEL_ID) & filters.ALL, collect_content))
    # /test komutu
    application.add_handler(CommandHandler("test", test_mode))

    # Botu çalıştırmaya başla
    logger.info("Bot çalışmaya başladı...")
    application.run_polling()

if __name__ == '__main__':
    main()

def save_shared_message(message_id):
    """Yeni paylaşılan mesaj ID'sini kaydeder."""
    shared_ids = load_shared_messages()
    if message_id not in shared_ids:
        shared_ids.append(message_id)
        with open(SHARE_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(shared_ids, f, indent=4)

# --- 3. ANA İŞLEV: İÇERİK TRANSFERİ (SADE) ---

async def transfer_content_simple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /test komutu ile çağrıldığında, rastgele bir mesajı kopyalar.
    Zamanlama ve link temizliği yoktur.
    """
    
    await update.message.reply_text("Test transferi başlatılıyor...")
    
    shared_ids = load_shared_messages()
    unshared_ids = [mid for mid in ALL_MESSAGE_IDS if mid not in shared_ids]

    if not unshared_ids:
        await update.message.reply_text("Paylaşılmamış içerik kalmadı!")
        return
        
    message_to_share_id = random.choice(unshared_ids)
    
    try:
        # Mesajı kopyalama (En basit kopyalama yöntemi)
        await context.bot.copy_message(
            chat_id=TARGET_CHANNEL_ID,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_id=message_to_share_id,
            # Caption boş bırakılırsa orijinal caption/metin kopyalanır.
            # Böylece link temizliği sorunu şimdilik atlanmış olur.
        )
        
        save_shared_message(message_to_share_id)
        logger.info("Mesaj ID %d, kanala başarıyla kopyalandı.", message_to_share_id)
        await update.message.reply_text(f"✅ Mesaj ID {message_to_share_id} başarıyla kopyalandı. Hedef kanalı kontrol edin.")

    except Exception as e:
        logger.error("Mesaj kopyalanırken hata oluştu: %s", e)
        await update.message.reply_text(f"❌ Kopyalama hatası: {e}. Botun kanal admin yetkilerini kontrol edin.")


# --- 4. ANA ÇALIŞTIRMA FONKSİYONU ---

def main():
    """Botu çalıştırır."""
    if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_CHANNEL_ID:
        logger.error("❌ Ortam değişkenleri ayarlanmamış.")
        return

    # Uygulama oluşturma
    application = Application.builder().token(BOT_TOKEN).build()

    # SADECE KOMUT İŞLEYİCİSİ EKLENİR
    application.add_handler(CommandHandler("test", transfer_content_simple))
    application.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text("Bot hazır. Transferi denemek için /test komutunu kullanın.")))

    logger.info("✅ Minimal Bot çalışıyor...")
    # Polling başlatılıyor. Artık zamanlayıcı olmadığı için hatalar ortadan kalkmalıdır.
    application.run_polling(poll_interval=1)

if __name__ == "__main__":
    main()
    
