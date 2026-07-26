from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = "sqlite:///./investment_ai.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    username = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=True)
    is_approved = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)

    # Link the user to their persistent tickers
    tickers = relationship("UserTicker", back_populates="owner")

class UserTicker(Base):
    __tablename__ = "user_tickers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    symbol = Column(String, index=True)
    shares = Column(Float, default=0.0)
    buy_price = Column(Float, default=0.0)
    section = Column(String, default="new") # 'new' or 'portfolio'

    owner = relationship("User", back_populates="tickers")

def init_db():
    Base.metadata.create_all(bind=engine)