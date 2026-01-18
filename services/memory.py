"""
Сервис работы с памятью AI коуча
- Сохранение и получение истории сообщений
- Сохранение и получение долгосрочной памяти (факты о пользователе)
"""
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.db import async_session
from database.models import ConversationMessage, UserMemory


# Максимальное количество сообщений в контексте
MAX_CONVERSATION_MESSAGES = 20


async def save_message(user_id: int, role: str, content: str) -> ConversationMessage:
    """
    Сохранить сообщение в историю диалога

    Args:
        user_id: ID пользователя
        role: "user" или "assistant"
        content: Текст сообщения

    Returns:
        Созданная запись ConversationMessage или None если content пустой
    """
    # Не сохраняем пустые сообщения
    if not content or not content.strip():
        return None

    async with async_session() as session:
        message = ConversationMessage(
            user_id=user_id,
            role=role,
            content=content.strip()
        )
        session.add(message)
        await session.commit()
        await session.refresh(message)
        return message


async def get_recent_messages(
    user_id: int,
    limit: int = MAX_CONVERSATION_MESSAGES
) -> list[dict]:
    """
    Получить последние N сообщений для контекста

    Args:
        user_id: ID пользователя
        limit: Максимальное количество сообщений

    Returns:
        Список словарей {"role": str, "content": str}
    """
    async with async_session() as session:
        result = await session.execute(
            select(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .where(ConversationMessage.content != '')  # Фильтруем пустые
            .where(ConversationMessage.content.isnot(None))  # Фильтруем None
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        messages = result.scalars().all()

        # Возвращаем в хронологическом порядке (старые первыми), только непустые
        return [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(messages)
            if msg.content and msg.content.strip()
        ]


async def clear_old_messages(user_id: int, days: int = 7) -> int:
    """
    Удалить старые сообщения (старше N дней)

    Args:
        user_id: ID пользователя
        days: Количество дней для хранения

    Returns:
        Количество удалённых записей
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        result = await session.execute(
            delete(ConversationMessage)
            .where(ConversationMessage.user_id == user_id)
            .where(ConversationMessage.created_at < cutoff)
        )
        await session.commit()
        return result.rowcount


async def save_memory(
    user_id: int,
    category: str,
    content: str
) -> UserMemory:
    """
    Сохранить факт о пользователе в долгосрочную память

    Args:
        user_id: ID пользователя
        category: Категория (preference, habit, restriction, goal, fact)
        content: Текст факта

    Returns:
        Созданная запись UserMemory
    """
    async with async_session() as session:
        # Проверяем, нет ли уже такого факта
        existing = await session.execute(
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .where(UserMemory.category == category)
            .where(UserMemory.content == content)
        )
        if existing.scalar_one_or_none():
            # Уже есть такой факт
            return existing.scalar_one()

        memory = UserMemory(
            user_id=user_id,
            category=category,
            content=content
        )
        session.add(memory)
        await session.commit()
        await session.refresh(memory)
        return memory


async def get_memories(
    user_id: int,
    category: Optional[str] = None
) -> list[dict]:
    """
    Получить долгосрочную память пользователя

    Args:
        user_id: ID пользователя
        category: Фильтр по категории (опционально)

    Returns:
        Список словарей {"category": str, "content": str}
    """
    async with async_session() as session:
        query = select(UserMemory).where(UserMemory.user_id == user_id)

        if category:
            query = query.where(UserMemory.category == category)

        query = query.order_by(UserMemory.created_at.desc())

        result = await session.execute(query)
        memories = result.scalars().all()

        return [
            {"category": mem.category, "content": mem.content}
            for mem in memories
        ]


async def get_memories_as_text(user_id: int) -> str:
    """
    Получить память пользователя в текстовом формате для промпта

    Returns:
        Строка с фактами о пользователе
    """
    memories = await get_memories(user_id)

    if not memories:
        return ""

    # Группируем по категориям
    categories = {
        "preference": "Предпочтения",
        "habit": "Привычки",
        "restriction": "Ограничения",
        "goal": "Цели",
        "fact": "Факты"
    }

    grouped = {}
    for mem in memories:
        cat = mem["category"]
        if cat not in grouped:
            grouped[cat] = []
        grouped[cat].append(mem["content"])

    lines = []
    for cat, items in grouped.items():
        cat_name = categories.get(cat, cat)
        lines.append(f"{cat_name}:")
        for item in items:
            lines.append(f"  - {item}")

    return "\n".join(lines)


async def delete_memory(user_id: int, content: str) -> bool:
    """
    Удалить факт из памяти

    Args:
        user_id: ID пользователя
        content: Текст факта для удаления

    Returns:
        True если удалено, False если не найдено
    """
    async with async_session() as session:
        result = await session.execute(
            delete(UserMemory)
            .where(UserMemory.user_id == user_id)
            .where(UserMemory.content == content)
        )
        await session.commit()
        return result.rowcount > 0


async def update_memory(
    user_id: int,
    old_content: str,
    new_content: str
) -> Optional[UserMemory]:
    """
    Обновить факт в памяти

    Args:
        user_id: ID пользователя
        old_content: Старый текст
        new_content: Новый текст

    Returns:
        Обновлённая запись или None
    """
    async with async_session() as session:
        result = await session.execute(
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .where(UserMemory.content == old_content)
        )
        memory = result.scalar_one_or_none()

        if memory:
            memory.content = new_content
            memory.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(memory)
            return memory

        return None
