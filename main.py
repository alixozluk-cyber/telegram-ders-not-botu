import os
import re
import json
import time
from datetime import datetime
from telebot import TeleBot
from dotenv import load_dotenv

# Railway, genellikle ortam değişkenlerini doğrudan ayarlar, 
# ancak yerel test için gerekli olabilir.
load_dotenv()

# --- AYARLAR ---
# Ortam değişkenleri kontrolü ve yüklenmesi
BOT_TOKEN = os.getenv('BOT_TOKEN')
try:
    # Kanal ID'leri int'e çevrilirken hata olmaması için kontrol
    SOURCE_CHANNEL_ID = int(os.getenv('SOURCE_CHANNEL_ID')) 
    TARGET_CHANNEL_ID = int(os.getenv('TARGET_CHANNEL_ID'))
except (TypeError, ValueError):
    # Eğer değişkenler yoksa veya int'e çevrilemiyorsa, programı durdurur
    print("HATA: Ortam değişkenleri (SOURCE_CHANNEL_ID/TARGET_CHANNEL_ID) eksik veya hatalı.")
    exit(1) # Hata koduyla çıkış yap

# Yasaklı Kelimeler (Reklamları filtrelemek için)
BANNED_WORDS = [
    'reklam', 'sponsor', 'ücretli', 'kampanya', 'indirim', 
    'çekiliş', 'satın al', 'üyelik', 'bitcoin', 'iletişim',
    'fırsat', 'kazan'
]

# --- YARDIMCI FONKSİYONLAR ---

def clean_text(text):
    """
    Mesaj metninden URL'leri, kullanıcı adlarını ve fazla boşlukları temizler.
    """
    if not text:
        return ""
        
    # URL'leri kaldırma
    text = re.sub(r'https?:\/\/[^\s]+', '', text)
    # @kullanıcıadlarını kaldırma
    text = re.sub(r'@[a-zA-Z0-9_]+', '', text)
    # Çoklu boşlukları tek boşluğa indirgeme
    text = re.sub(r'\s{2,}', ' ', text).strip()
    
    return text

def is_banned(text):
    """
    Mesaj metninde yasaklı kelime geçip geçmediğini kontrol eder.
    """
    if not text:
        return False
        
    lower_text = text.lower()
    for word in BANNED_WORDS:
        if word in lower_text:
            return True
    return False

def get_last_sent_message_id():
    """
    Son gönderilen mesaj ID'sini geçici bir dosyadan okur.
    """
    try:
        # Railway'de dosya sistemi geçicidir, bu sadece bir kerelik denemeler için uygundur.
        # Üretim ortamı için 'Postgres' gibi bir veritabanı kullanılmalıdır.
        with open('last_id.json', 'r') as f:
            data = json.load(f)
            return data.get('last_message_id', 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

def set_last_sent_message_id(message_id):
    """
    Son gönderilen mesaj ID'sini dosyaya kaydeder.
    """
    # Mesaj ID'si 0'dan büyükse kaydet
    if message_id > 0:
        try:
            with open('last_id.json', 'w') as f:
                json.dump({'last_message_id': message_id}, f)
        except Exception as e:
            print(f"ID kaydedilirken hata oluştu: {e}")

# --- ANA İŞ AKIŞI ---

def transfer_posts():
    """
    Kaynak kanaldan yeni mesajları çeker, filtreler ve hedefe gönderir.
    """
    if not BOT_TOKEN:
        print("Hata: BOT_TOKEN tanımlı değil.")
        return

    bot = TeleBot(BOT_TOKEN)
    
    # En son gönderilen mesaj ID'sini al
    last_sent_id = get_last_sent_message_id()
    print(f"En son gönderilen ID: {last_sent_id}")
    
    messages_to_transfer = []

    try:
        # Son 100 güncellemeyi çek (Bu, botun yönetici olduğu kanallardaki son mesajları içerebilir)
        # Offset'i last_sent_id + 1 olarak ayarlamak, sadece yeni mesajları almayı hedefler.
        updates = bot.get_updates(offset=last_sent_id + 1, limit=100, timeout=10)
        
    except Exception as e:
        print(f"HATA: Telegram API'dan güncellemeler alınamadı. Botunuzun Kaynak Kanala Yönetici olarak eklendiğinden emin olun. Hata: {e}")
        return
        
    # Güncellemelerden sadece Kaynak Kanalımızın mesajlarını filtrele
    for update in updates:
        # Kanal postları (updates'ten gelen kanal mesajları)
        if update.channel_post and update.channel_post.chat.id == SOURCE_CHANNEL_ID:
            msg = update.channel_post
            
            # Message ID'si, last_sent_id'den büyük ve anlamlı olmalı
            if msg.message_id > last_sent_id:
                messages_to_transfer.append(msg)
    
    # En eski mesajdan en yeniye doğru sırala ve sadece ilk 2 tanesini al (saatte 2 post kuralı)
    # Cron Job her saat çalıştığı için, bu kısıtlamayı manuel koyabiliriz.
    messages_to_transfer.sort(key=lambda x: x.date) 
    
    new_last_id = last_sent_id
    post_count_sent = 0

    for msg in messages_to_transfer:
        if post_count_sent >= 2:
            # Sadece 2 post gönderdikten sonra döngüyü kır
            new_last_id = max(new_last_id, msg.message_id) # Atlanan postların ID'sini de kaydet
            continue

        text = msg.text or msg.caption
        
        # 1. Filtreleme ve Temizleme
        cleaned_text = clean_text(text)
        
        if is_banned(cleaned_text):
            print(f"-> Post {msg.message_id}: Yasaklı kelime nedeniyle atlandı.")
            new_last_id = max(new_last_id, msg.message_id)
            continue
            
        if not cleaned_text and not msg.photo and not msg.document and not msg.video:
            print(f"-> Post {msg.message_id}: Temizlendikten sonra boş kaldı/Desteklenmeyen tip.")
            new_last_id = max(new_last_id, msg.message_id)
            continue

        # 2. Gönderme İşlemi
        try:
            if msg.photo:
                # Fotoğrafı gönder
                bot.send_photo(TARGET_CHANNEL_ID, msg.photo[-1].file_id, caption=cleaned_text)
            elif msg.document:
                # Belgeyi/Dosyayı gönder
                bot.send_document(TARGET_CHANNEL_ID, msg.document.file_id, caption=cleaned_text)
            elif msg.video:
                 # Videoyu gönder
                bot.send_video(TARGET_CHANNEL_ID, msg.video.file_id, caption=cleaned_text)
            else:
                # Sadece metni gönder
                bot.send_message(TARGET_CHANNEL_ID, cleaned_text)
            
            print(f"-> Post {msg.message_id} başarıyla gönderildi.")
            new_last_id = msg.message_id
            post_count_sent += 1
            
            # Postlar arası kısa bir bekleme
            time.sleep(1) 
            
        except Exception as e:
            print(f"Post {msg.message_id} gönderilirken hata oluştu: {e}")
            new_last_id = max(new_last_id, msg.message_id) # Başarısız olsa bile bir daha denememesi için ID'yi kaydet

    # Son gönderilen/işlenen mesaj ID'sini güncelle
    if new_last_id > last_sent_id:
        set_last_sent_message_id(new_last_id)
        print(f"Son işlenen/gönderilen ID, {new_last_id} olarak güncellendi.")
    else:
        print("Yeni gönderilecek post bulunamadı veya saat kotası doldu.")


if __name__ == '__main__':
    # TRT 12:00-19:00, UTC 9-16'ya karşılık gelir.
    current_utc_hour = datetime.utcnow().hour
    
    # 9 (dahil) ile 16 (dahil) arası UTC saatleri
    if 9 <= current_utc_hour <= 16:
        print(f"✅ Saat dilimi uygun (UTC Saati: {current_utc_hour}:00, TRT: {current_utc_hour+3}:00). Transfer başlatılıyor...")
        transfer_posts()
    else:
        print(f"❌ Saat dilimi uygun değil (UTC Saati: {current_utc_hour}:00). Atlanıyor.")

