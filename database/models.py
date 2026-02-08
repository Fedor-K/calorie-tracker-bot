from datetime import datetime, timezone
from sqlalchemy import BigInteger, String, Float, Integer, DateTime, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user_id
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Цели
    calorie_goal: Mapped[int] = mapped_column(Integer, default=2000)
    water_goal: Mapped[int] = mapped_column(Integer, default=2000)  # мл
    protein_goal: Mapped[int] = mapped_column(Integer, default=100)  # г

    # Физические параметры
    current_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)  # см
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)  # male/female
    goal: Mapped[str | None] = mapped_column(String(20), nullable=True)  # lose/gain/maintain/health

    # Локация и настройки
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Страна для рекомендаций
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")

    # Настройки напоминаний
    remind_water: Mapped[bool] = mapped_column(Boolean, default=True)
    remind_food: Mapped[bool] = mapped_column(Boolean, default=True)
    remind_weight: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    food_entries: Mapped[list["FoodEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    weight_entries: Mapped[list["WeightEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    water_entries: Mapped[list["WaterEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    activity_entries: Mapped[list["ActivityEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    conversation_messages: Mapped[list["ConversationMessage"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    user_memories: Mapped[list["UserMemory"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    trend_subscriptions: Mapped[list["TrendSubscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class FoodEntry(Base):
    __tablename__ = "food_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    # Информация о еде
    description: Mapped[str] = mapped_column(Text)  # Описание от AI
    meal_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # breakfast, lunch, dinner, snack

    # Нутриенты
    calories: Mapped[int] = mapped_column(Integer, default=0)
    protein: Mapped[float] = mapped_column(Float, default=0)  # г
    carbs: Mapped[float] = mapped_column(Float, default=0)  # г
    fat: Mapped[float] = mapped_column(Float, default=0)  # г
    fiber: Mapped[float] = mapped_column(Float, default=0)  # г

    # Мета
    photo_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="food_entries")


class WeightEntry(Base):
    __tablename__ = "weight_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    weight: Mapped[float] = mapped_column(Float)  # кг
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="weight_entries")


class WaterEntry(Base):
    __tablename__ = "water_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    amount: Mapped[int] = mapped_column(Integer)  # мл

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="water_entries")


class ActivityEntry(Base):
    __tablename__ = "activity_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    activity_type: Mapped[str] = mapped_column(String(100))  # бег, ходьба, тренировка
    duration: Mapped[int] = mapped_column(Integer)  # минуты
    calories_burned: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="activity_entries")


class ConversationMessage(Base):
    """История диалога с AI коучем"""
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="conversation_messages")


class UserMemory(Base):
    """Долгосрочная память о пользователе"""
    __tablename__ = "user_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String(50))  # preference, habit, restriction, goal, fact
    content: Mapped[str] = mapped_column(Text)  # "не ест молочку", "тренируется по утрам"
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="user_memories")


# ============================================================================
# Trend Watcher Models
# ============================================================================

class TrendSource(Base):
    """Sources for trend data (RSS feeds, websites, APIs)"""
    __tablename__ = "trend_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(50))  # rss, web, api
    category: Mapped[str] = mapped_column(String(50))  # beauty, art, both
    language: Mapped[str] = mapped_column(String(10), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    entries: Mapped[list["TrendEntry"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class TrendEntry(Base):
    """Individual trend items collected from sources"""
    __tablename__ = "trend_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("trend_sources.id"), nullable=True)

    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50))  # beauty, art
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)  # skincare, makeup, contemporary, digital, etc.
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # comma-separated tags
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)  # positive, neutral, negative
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)  # AI-assigned relevance/momentum score 0-100
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    source: Mapped["TrendSource"] = relationship(back_populates="entries")


class TrendDigest(Base):
    """AI-generated trend digests / reports"""
    __tablename__ = "trend_digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50))  # beauty, art, both
    period: Mapped[str] = mapped_column(String(20))  # daily, weekly
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)  # AI-generated markdown summary
    top_trends: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of top trend titles
    entry_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of TrendEntry IDs used
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class TrendSubscription(Base):
    """User subscriptions to trend categories"""
    __tablename__ = "trend_subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    category: Mapped[str] = mapped_column(String(50))  # beauty, art, both
    subcategories: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of subcategories
    frequency: Mapped[str] = mapped_column(String(20), default="daily")  # daily, weekly, realtime
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="trend_subscriptions")
