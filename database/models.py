from datetime import datetime
from sqlalchemy import BigInteger, String, Float, Integer, DateTime, Text, Boolean, ForeignKey
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

    # Настройки напоминаний
    remind_water: Mapped[bool] = mapped_column(Boolean, default=True)
    remind_food: Mapped[bool] = mapped_column(Boolean, default=True)
    remind_weight: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Moscow")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    food_entries: Mapped[list["FoodEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    weight_entries: Mapped[list["WeightEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    water_entries: Mapped[list["WaterEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    activity_entries: Mapped[list["ActivityEntry"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="food_entries")


class WeightEntry(Base):
    __tablename__ = "weight_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    weight: Mapped[float] = mapped_column(Float)  # кг
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="weight_entries")


class WaterEntry(Base):
    __tablename__ = "water_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    amount: Mapped[int] = mapped_column(Integer)  # мл

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="water_entries")


class ActivityEntry(Base):
    __tablename__ = "activity_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))

    activity_type: Mapped[str] = mapped_column(String(100))  # бег, ходьба, тренировка
    duration: Mapped[int] = mapped_column(Integer)  # минуты
    calories_burned: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="activity_entries")
