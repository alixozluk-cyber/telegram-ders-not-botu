from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# Veritabanı dosyasını tanımlayın (Railway'de PostgreSQL kullanırken bağlantı dizesi buraya gelir)
DATABASE_URL = "sqlite:///bot_database.db"

# SQLAlchemy kurulumu
Engine = create_engine(DATABASE_URL)
Base = declarative_base()

# Veri modeli
class Content(Base):
    __tablename__ = "contents"
    
    id = Column(Integer, primary_key=True)
    # Mesajı kolayca yeniden göndermek için toplayıcı kanaldaki mesaj ID'si
    collector_message_id = Column(Integer, unique=True, nullable=False)
    # Kullanılıp kullanılmadığını belirten bayrak (True: Kullanıldı, False: Hazır)
    is_used = Column(Boolean, default=False)
    
    def __repr__(self):
        return f"<Content(id={self.id}, message_id={self.collector_message_id}, is_used={self.is_used})>"

# Veritabanı tablolarını oluşturma
def init_db():
    Base.metadata.create_all(Engine)

# Veritabanı oturumu oluşturucu
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=Engine)

# Veritabanı işlemleri için bir oturum alın
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
