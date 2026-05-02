from datetime import datetime, date as date_type
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    DateTime, Date, BigInteger, ForeignKey, Text
)
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    is_authenticated = Column(Boolean, default=False)
    profile_complete = Column(Boolean, default=False)

    age = Column(Integer, nullable=True)
    gender = Column(String(10), nullable=True)
    weight = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    target_weight = Column(Float, nullable=True)
    activity_level = Column(String(20), nullable=True)
    daily_calories = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    food_logs = relationship("FoodLog", back_populates="user", cascade="all, delete-orphan")
    milestones = relationship("Milestone", back_populates="user", cascade="all, delete-orphan", order_by="Milestone.target_weight")


class FoodLog(Base):
    __tablename__ = "food_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    date = Column(Date, default=date_type.today)
    food_description = Column(Text)
    calories = Column(Integer)
    photo_file_id = Column(String(500), nullable=True)
    confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="food_logs")


class Milestone(Base):
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    target_weight = Column(Float)
    achieved = Column(Boolean, default=False)
    achieved_at = Column(DateTime, nullable=True)
    notified = Column(Boolean, default=False)

    user = relationship("User", back_populates="milestones")
