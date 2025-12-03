import os
import re
import random
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from dotenv import load_dotenv

# Ortam değişkenlerini yükle
load_dotenv()

# --- Ayarlar ve Ortam Değişkenleri ---

# Telegram API kimlik bilgileri (Telethon için)
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
SESSION_NAME = 'ders_notu_session' # Botun oturum dosyası adı

# Bot Token (Postu gönderecek bot için)
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Hedef Kanal
TARGET_CHANNEL = os.getenv('TARGET_CHANNEL') # örn: -100xxxxxxxxxx

# Kaynak Kanallar (Kullanıcı adı veya ID)
SOURCE_CHANNELS = [
    os.getenv('SOURCE_CHANNEL_1'), # örn: '@KaynakKanal1'
    os.getenv('SOURCE_CHANNEL_2')  # örn: '@KaynakKanal2'
]

# Yasaklı Kelimeler (Reklamları filtrelemek için)
BANNED_WORDS = [
    'reklam', 'sponsor', 'ücretli', 'kampanya', 'indirim', 
    'çekiliş', 'kazanma şansı', 'satın al', 'iletişim', 
    'üyelik', 'premium', 'bitcoin'
]

# Post Çekme Aralığı (Son 30 gün)
TIME_LIMIT = timedelta(days=30)
NOW = datetime.now()
TIME_THRESHOLD = NOW - TIME_LIMIT

# Kaç adet post atılacağı
POST_COUNT = 2

# --- Fonksiyonlar ---

def clean_message_text(text):
    """
    Mesaj metninden kullanıcı adlarını, linkleri ve forward etiketlerini temizler.
    """
    if not text:
        return ""
    
    # Forward etiketlerini kaldırma
    # Ör: 'Forwarded from X' veya 't.me/X' gibi ifadeleri kaldırma
    text = re.sub(r'(?i)forwarded from.*\n?', '', text).strip()

    # t.me linklerini kaldırma
    text = re.sub(r't\.me/[a-zA-Z0-9_/]+', '', text)
    
    # Genel URL'leri kaldırma
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

async def get_and_filter_posts():
    """
    Belirtilen kaynak kanallardan son 30 gün içindeki postları çeker ve filtreler.
    """
    print("Kanallara bağlanılıyor...")
    # Kullanıcı hesabı gibi davranacak client başlatılıyor
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    
    all_valid_posts = []

    for channel_id in SOURCE_CHANNELS:
        if not channel_id:
            continue
            
        print(f"-> {channel_id} kanalından içerikler çekiliyor...")
        try:
            # Sadece son 30 günlük postları çek
            messages = await client.get_messages(
                channel_id, 
                limit=None, 
                offset_date=TIME_THRESHOLD # Bu tarihten daha yeni olanları alır
            )
            
            for msg in messages:
                # 1. Post tipi ve tarihi kontrolü
                # Sadece fotoğraf veya belge içeren ya da sadece metin içeren mesajları al
                if not msg.date or msg.date < TIME_THRESHOLD:
                    continue
                if not (msg.text or msg.media):
                    continue
                
                # 2. Yasaklı kelime ve metin temizliği
                cleaned_text = clean_message_text(msg.text)
                if is_banned(cleaned_text):
                    print(f"   [Filtre] Yasaklı kelime bulundu: {msg.id}")
                    continue
                    
                # Eğer post bir medya içeriyorsa (fotoğraf, dosya), bunu listeye ekle.
                # Aksi halde, sadece metin içeriği varsa bunu da ekle.
                if msg.media and (isinstance(msg.media, MessageMediaPhoto) or isinstance(msg.media, MessageMediaDocument)):
                    all_valid_posts.append({
                        'type': 'media',
                        'message': msg,
                        'caption': cleaned_text,
                        'date': msg.date
                    })
                elif msg.text and cleaned_text:
                    all_valid_posts.append({
                        'type': 'text',
                        'message': msg,
                        'text': cleaned_text,
                        'date': msg.date
                    })

        except Exception as e:
            print(f"Hata oluştu ({channel_id}): {e}")
            
    await client.disconnect()
    print(f"\nToplam çekilen ve filtrelenen post sayısı: {len(all_valid_posts)}")
    return all_valid_posts

async def send_posts(selected_posts):
    """
    Seçilen postları hedef kanala bot token'ı ile gönderir.
    """
    if not selected_posts:
        print("Gönderilecek post bulunamadı.")
        return

    # Bot client başlatılıyor (Bot Token ile)
    bot_client = TelegramClient(SESSION_NAME, API_ID, API_HASH).start(bot_token=BOT_TOKEN)
    await bot_client
    
    print(f"\n{len(selected_posts)} adet post kanala gönderiliyor...")
    
    for post in selected_posts:
        msg = post['message']
        try:
            if post['type'] == 'media':
                # Fotoğraf veya belge gönderme
                await bot_client.send_file(
                    TARGET_CHANNEL,
                    msg.media,
                    caption=post['caption'],
                    force_document=True if isinstance(msg.media, MessageMediaDocument) else False
                )
            elif post['type'] == 'text':
                # Sadece metin gönderme
                await bot_client.send_message(
                    TARGET_CHANNEL,
                    post['text']
                )
            
            print(f"-> Post gönderildi (ID: {msg.id}, Tarih: {post['date'].strftime('%Y-%m-%d %H:%M')})")
            # Postlar arası bekleme ekleyebilirsiniz
            await bot_client.run_until_disconnected() 
            
        except Exception as e:
            print(f"Gönderme sırasında hata: {e}")
            
    await bot_client.disconnect()
    print("Gönderme işlemi tamamlandı.")


async def main():
    """
    Ana çalışma akışı
    """
    valid_posts = await get_and_filter_posts()
    
    if len(valid_posts) < POST_COUNT:
        print(f"Yeterli sayıda post ({POST_COUNT}) bulunamadı. Toplam: {len(valid_posts)}")
        return

    # Farklı zamanlardan post seçimi için:
    # 1. Post: Son 30 günün ilk yarısından (örneğin ilk 15 gün) rastgele seçilir
    # 2. Post: Son 30 günün ikinci yarısından (örneğin son 15 gün) rastgele seçilir
    
    # Tarih aralığını ikiye bölme noktası
    HALF_WAY_DATE = NOW - timedelta(days=15)
    
    first_half_posts = [p for p in valid_posts if p['date'] < HALF_WAY_DATE]
    second_half_posts = [p for p in valid_posts if p['date'] >= HALF_WAY_DATE]
    
    selected_posts = []
    
    if first_half_posts:
        selected_posts.append(random.choice(first_half_posts))
        
    if second_half_posts:
        # Seçilen postlar arasında kopya olmaması için kontrol
        if selected_posts and second_half_posts:
             # Eğer ikinci yarıdan bir post seçilecekse ve ilk yarıdan zaten bir tane seçilmişse,
             # farklı post olduğundan emin olmak için ID'leri kontrol et
             while True:
                candidate = random.choice(second_half_posts)
                if candidate['message'].id != selected_posts[0]['message'].id:
                    selected_posts.append(candidate)
                    break
                # Eğer sadece 1 tane post varsa (nadiren), döngüden çıkmak için
                if len(second_half_posts) == 1:
                    break
        elif second_half_posts:
             selected_posts.append(random.choice(second_half_posts))


    # Postları gönder
    await send_posts(selected_posts[:POST_COUNT])
    
if __name__ == '__main__':
    # Telethon'un async yapısını çalıştırmak için
    import asyncio
    asyncio.run(main())
                      
