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
    Son gönderilen mesaj ID'sini basit bir dosyadan (Railway'de silinebilir, 
    ancak burada basitlik için geçici dosya kullanıyoruz) okur. 
    Daha güvenilir bir çözüm için Railway'de 'Postgres' eklentisi kullanmak gerekir.
    """
    try:
        with open('last_id.json', 'r') as f:
            data = json.load(f)
            return data.get('last_message_id', 0)
    except (FileNotFoundError, json.JSONDecodeError):
        return 0

def set_last_sent_message_id(message_id):
    """
    Son gönderilen mesaj ID'sini dosyaya kaydeder.
    """
    with open('last_id.json', 'w') as f:
        json.dump({'last_message_id': message_id}, f)

# --- ANA İŞ AKIŞI ---

def transfer_posts():
    if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not TARGET_CHANNEL_ID:
        print("Hata: Ortam değişkenleri eksik.")
        return

    bot = TeleBot(BOT_TOKEN)
    
    # Botun okuyabileceği en son mesaj ID'sini al
    last_sent_id = get_last_sent_message_id()
    
    print(f"En son gönderilen ID: {last_sent_id}")
    
    # 1. Kaynak kanaldan son 100 mesajı çek
    # Bot API, getUpdates ile sadece kendisinin görebildiği (bot ile etkileşime girilen) mesajları çeker.
    # Kanal geçmişini doğrudan okuyamaz. Bu nedenle, botun kanala yönetici olarak eklenip 
    # 'pinlenmiş' bir mesajı okumasını veya 'etiketlenen' mesajları çekmesini sağlamak daha güvenilir.
    # Ancak cron job için doğrudan bir "geçmişi oku" API'ı Bot Token ile yoktur.
    
    # **Alternatif (Daha güvenilir):** # Botu Kaynak Kanala yönetici olarak ekleyin ve
    # **"messages"** (Mesajları Oku) hakkını verin.
    # Ardından, güncel API'ı kullanarak kanalın "güncel" mesajlarını almaya çalışın.
    
    # En pratik yol: Kaynak kanalın son mesajlarını almak için 'get_chat' yerine,
    # manuel olarak kanal mesajlarını çeken bir API çağrısı yapmalıyız. 
    # Telebot kütüphanesi bu direkt geçmiş okuma işlevini sağlamadığı için, 
    # pratiklik adına botun yönetici olduğu ve bir 'Güncelleme' (Update) bekleyen 
    # bir yapıyı simüle etmeliyiz.
    
    # **Telebot ile Kanal Okuma Kısıtlaması nedeniyle, en güvenilir yöntem, 
    # Botun her çalıştığında Kaynak Kanalda bir 'dummy' mesaj gönderip silmesi 
    # ve bu sırada gelen son mesajları 'Updates' üzerinden almayı denemesidir.**
    
    # Ancak bu, cron işini karmaşıklaştırır. En basit yöntem olan 'son gönderilen ID'
    # üzerinden denemeye devam edeceğiz, ancak bu kısım Bot API'sinin sınırlamasıdır.

    # Simülasyon: Son gönderilen mesajları alıyoruz (Bot API kısıtlı bir geçmiş sunar)
    # Gerçek uygulamada, bu, botun yönetici olduğu kanallarda bile zor çalışır.
    # Bu yüzden, bu kod sadece *son mesajı* almayı hedefler, yüzlercesini değil.

    # Daha iyi bir yaklaşım için: Kaynak kanaldaki tüm mesajları okumak yerine, 
    # Sadece yeni gelen tek bir mesajı kontrol edelim.
    
    try:
        # Son mesajı al (Bu, botun kanalda yönetici olduğu varsayımıyla çalışır)
        last_message = bot.get_chat(SOURCE_CHANNEL_ID)
        
        # Eğer bu bir mesaj objesi ise (genellikle değil, chat objesi döner)
        # Daha güvenilir olan, 'telethon' yerine 'python-telegram-bot' kullanmaktır.
        
        # Basitleştirilmiş: Botun Kaynak Kanala en son gelen mesajını manuel olarak alıp,
        # bu mesajın ID'sini kullanmak zorundayız. Bot API'de bu zor.
        
        # **EN PRATİK ÇÖZÜM:** Kaynak kanala gönderilen içeriğin bir 'bot' tarafından 
        # değil, bizzat sizin tarafınızdan 'iletilmesi' (Forward) daha güvenilir olur.
        # Veya kodun sadece son 10 Update'i kontrol etmesi.
        
        updates = bot.get_updates(offset=None, limit=10, timeout=10)
        
    except Exception as e:
        print(f"Hata: Kaynak kanaldan mesaj alınamadı. Botun kanala 'Yönetici' olarak eklendiğinden ve 'Mesaj Silme' iznine sahip olduğundan emin olun. Hata: {e}")
        return
        
    messages_to_transfer = []
    
    # Gelen güncellemeleri işle
    for update in updates:
        # Eğer güncelleme bir kanal mesajı ise ve henüz gönderilmemişse
        if update.channel_post and update.channel_post.chat.id == SOURCE_CHANNEL_ID:
            msg = update.channel_post
            
            # Daha önce gönderilmiş ID'den büyükse, yeni bir mesajdır
            if msg.message_id > last_sent_id:
                messages_to_transfer.append(msg)

    # En eski mesajdan en yeniye doğru sırala ve gönder
    messages_to_transfer.sort(key=lambda x: x.date) 

    new_last_id = last_sent_id
    
    for msg in messages_to_transfer:
        text = msg.text or msg.caption
        
        # 1. Filtreleme ve Temizleme
        cleaned_text = clean_text(text)
        
        if is_banned(cleaned_text):
            print(f"-> Post {msg.message_id}: Yasaklı kelime nedeniyle atlandı.")
            new_last_id = msg.message_id
            continue
            
        # Eğer metin temizlendikten sonra boş kalıyorsa, atla
        if not cleaned_text and not msg.photo and not msg.document:
            print(f"-> Post {msg.message_id}: Temizlendikten sonra boş kaldı.")
            new_last_id = msg.message_id
            continue

        # 2. Gönderme İşlemi
        try:
            if msg.photo:
                # Fotoğrafı gönder
                bot.send_photo(TARGET_CHANNEL_ID, msg.photo[-1].file_id, caption=cleaned_text)
            elif msg.document:
                # Belgeyi/Dosyayı gönder
                bot.send_document(TARGET_CHANNEL_ID, msg.document.file_id, caption=cleaned_text)
            else:
                # Sadece metni gönder
                bot.send_message(TARGET_CHANNEL_ID, cleaned_text)
            
            print(f"-> Post {msg.message_id} başarıyla gönderildi.")
            new_last_id = msg.message_id # Başarılı gönderilen ID'yi kaydet
            
            # Postlar arası kısa bir bekleme (Telegram limitlerine takılmamak için)
            time.sleep(1) 
            
        except Exception as e:
            print(f"Post {msg.message_id} gönderilirken hata oluştu: {e}")
            # Hata durumunda bile ID'yi güncelleyelim ki tekrar denemesin
            new_last_id = msg.message_id 


    # Son gönderilen mesaj ID'sini güncelle
    if new_last_id > last_sent_id:
        set_last_sent_message_id(new_last_id)
        print(f"Son gönderilen ID, {new_last_id} olarak güncellendi.")

if __name__ == '__main__':
    # Şu anki saat dilimi kontrolü (Türkiye için 12:00-19:00 TRT)
    # Railway genellikle UTC kullandığı için, TRT'yi UTC'ye çevirmeliyiz:
    # 12:00 TRT (GMT+3) -> 9:00 UTC
    # 19:00 TRT (GMT+3) -> 16:00 UTC
    
    current_utc_hour = datetime.utcnow().hour
    
    # 9 (dahil) ile 16 (dahil) arası UTC saatleri
    if 9 <= current_utc_hour <= 16:
        print(f"✅ Saat dilimi uygun (UTC Saati: {current_utc_hour}:00). Gönderim başlatılıyor...")
        transfer_posts()
    else:
        print(f"❌ Saat dilimi uygun değil (UTC Saati: {current_utc_hour}:00). Atlanıyor.")


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
                      
