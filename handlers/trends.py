"""
Handlers for the Trend Watcher feature.
Provides /trends command and inline keyboard navigation for beauty & art market trends.
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards.trends import (
    get_trends_main_keyboard,
    get_trends_category_keyboard,
    get_subscription_keyboard,
)
from services.trends import (
    get_top_trends,
    get_latest_digest,
    generate_digest,
    get_user_subscriptions,
    subscribe_user,
    unsubscribe_user,
    search_trends,
    get_trend_stats,
)

logger = logging.getLogger(__name__)
router = Router()


# ============================================================================
# FSM States
# ============================================================================

class TrendSearchStates(StatesGroup):
    waiting_for_query = State()


# ============================================================================
# Helper: Format trend entries for Telegram
# ============================================================================

def _format_trend_list(entries, title: str) -> str:
    """Format a list of trend entries into a Telegram message"""
    if not entries:
        return f"<b>{title}</b>\n\nПока нет данных. Тренды обновляются автоматически."

    lines = [f"<b>{title}</b>\n"]
    for i, e in enumerate(entries, 1):
        score_bar = _score_to_bar(e.trend_score)
        category_emoji = "💄" if e.category == "beauty" else "🎨"
        sub_tag = f" #{e.subcategory}" if e.subcategory else ""

        line = f"{i}. {category_emoji} <b>{e.title[:80]}</b>"
        if e.summary:
            line += f"\n   <i>{e.summary[:120]}...</i>"
        line += f"\n   {score_bar} {e.trend_score:.0f}/100{sub_tag}"
        if e.url:
            line += f'\n   <a href="{e.url}">Читать →</a>'

        lines.append(line)

    return "\n\n".join(lines)


def _score_to_bar(score: float) -> str:
    """Convert score 0-100 to a visual bar"""
    filled = int(score / 10)
    return "▓" * filled + "░" * (10 - filled)


# ============================================================================
# /trends command
# ============================================================================

@router.message(Command("trends"))
async def cmd_trends(message: Message):
    """Main entry point for the trend watcher"""
    await message.answer(
        "<b>📊 Trend Watcher — Beauty & Art</b>\n\n"
        "Отслеживайте тренды рынков красоты и искусства.\n"
        "Выберите раздел:",
        reply_markup=get_trends_main_keyboard(),
    )


@router.message(F.text == "📈 Тренды")
async def btn_trends(message: Message):
    """Reply keyboard button handler"""
    await cmd_trends(message)


# ============================================================================
# Callback handlers
# ============================================================================

@router.callback_query(F.data == "trends_main")
async def cb_trends_main(callback: CallbackQuery):
    """Return to main trends menu"""
    await callback.message.edit_text(
        "<b>📊 Trend Watcher — Beauty & Art</b>\n\n"
        "Отслеживайте тренды рынков красоты и искусства.\n"
        "Выберите раздел:",
        reply_markup=get_trends_main_keyboard(),
    )
    await callback.answer()


# --- Top trends by category ---

@router.callback_query(F.data == "trends_top_beauty")
async def cb_top_beauty(callback: CallbackQuery):
    """Show beauty trends category page"""
    await callback.message.edit_text(
        "<b>💄 Beauty Trends</b>\n\n"
        "Тренды рынка красоты — skincare, makeup, haircare и другие.",
        reply_markup=get_trends_category_keyboard("beauty"),
    )
    await callback.answer()


@router.callback_query(F.data == "trends_top_art")
async def cb_top_art(callback: CallbackQuery):
    """Show art trends category page"""
    await callback.message.edit_text(
        "<b>🎨 Art Trends</b>\n\n"
        "Тренды арт-рынка — contemporary, digital art, exhibitions и другие.",
        reply_markup=get_trends_category_keyboard("art"),
    )
    await callback.answer()


# --- Top trends with time period ---

@router.callback_query(F.data.startswith("trends_top_") & ~F.data.in_({"trends_top_beauty", "trends_top_art"}))
async def cb_top_trends_period(callback: CallbackQuery):
    """Show top trends for category + period (e.g. trends_top_beauty_24h)"""
    parts = callback.data.split("_")
    # trends_top_<category>_<period>
    if len(parts) >= 4:
        category = parts[2]
        period = parts[3]
    else:
        category = parts[2] if len(parts) > 2 else "both"
        period = "24h"

    hours = 24 if period == "24h" else 168
    period_label = "за 24 часа" if period == "24h" else "за неделю"
    cat_emoji = "💄" if category == "beauty" else "🎨"

    entries = await get_top_trends(category=category, hours=hours, limit=10)

    text = _format_trend_list(
        entries,
        f"{cat_emoji} Топ тренды {period_label}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_trends_category_keyboard(category),
        disable_web_page_preview=True,
    )
    await callback.answer()


# --- Subcategory trends ---

@router.callback_query(F.data.startswith("trends_sub_"))
async def cb_subcategory_trends(callback: CallbackQuery):
    """Show trends for a specific subcategory"""
    subcategory = callback.data.replace("trends_sub_", "")

    # Determine parent category
    from services.trends import BEAUTY_SUBCATEGORIES, ART_SUBCATEGORIES
    if subcategory in BEAUTY_SUBCATEGORIES:
        parent_cat = "beauty"
        cat_emoji = "💄"
    elif subcategory in ART_SUBCATEGORIES:
        parent_cat = "art"
        cat_emoji = "🎨"
    else:
        parent_cat = "both"
        cat_emoji = "📊"

    entries = await get_top_trends(
        category=parent_cat,
        subcategory=subcategory,
        hours=168,
        limit=10,
    )

    text = _format_trend_list(
        entries,
        f"{cat_emoji} Тренды: #{subcategory}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_trends_category_keyboard(parent_cat),
        disable_web_page_preview=True,
    )
    await callback.answer()


# --- Digests ---

@router.callback_query(F.data.startswith("trends_digest_"))
async def cb_digest(callback: CallbackQuery):
    """Show latest digest for a category"""
    category = callback.data.replace("trends_digest_", "")
    cat_labels = {
        "beauty": "💄 Beauty",
        "art": "🎨 Art",
        "both": "💄🎨 Beauty & Art",
    }

    await callback.answer("Загружаю дайджест...")

    digest = await get_latest_digest(category=category)

    if not digest:
        # Try generating one
        digest = await generate_digest(category=category)

    if digest:
        text = digest.content
        # Truncate if too long for Telegram (4096 chars)
        if len(text) > 4000:
            text = text[:3990] + "..."
    else:
        text = (
            f"<b>{cat_labels.get(category, category)} — Дайджест</b>\n\n"
            "Дайджест пока не готов. Тренды собираются автоматически, "
            "первый дайджест будет доступен после обновления."
        )

    await callback.message.edit_text(
        text,
        reply_markup=get_trends_main_keyboard(),
        disable_web_page_preview=True,
    )


# --- Subscriptions ---

@router.callback_query(F.data == "trends_subscriptions")
async def cb_subscriptions(callback: CallbackQuery):
    """Show subscription management"""
    user_id = callback.from_user.id
    subs = await get_user_subscriptions(user_id)

    if subs:
        sub_text = "\n".join([
            f"  • {s.category} ({s.frequency})"
            for s in subs
        ])
        text = (
            f"<b>🔔 Ваши подписки на тренды</b>\n\n"
            f"{sub_text}\n\n"
            f"Нажмите чтобы подписаться/отписаться:"
        )
    else:
        text = (
            "<b>🔔 Подписки на тренды</b>\n\n"
            "У вас пока нет подписок.\n"
            "Подпишитесь, чтобы получать дайджесты автоматически:"
        )

    await callback.message.edit_text(
        text,
        reply_markup=get_subscription_keyboard(subs),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("trends_toggle_sub_"))
async def cb_toggle_subscription(callback: CallbackQuery):
    """Toggle subscription for a category"""
    category = callback.data.replace("trends_toggle_sub_", "")
    user_id = callback.from_user.id

    subs = await get_user_subscriptions(user_id)
    active_cats = {s.category for s in subs}

    if category in active_cats:
        await unsubscribe_user(user_id, category)
        await callback.answer(f"Отписка от {category} ✓")
    else:
        await subscribe_user(user_id, category)
        await callback.answer(f"Подписка на {category} ✓")

    # Refresh keyboard
    subs = await get_user_subscriptions(user_id)
    await callback.message.edit_reply_markup(
        reply_markup=get_subscription_keyboard(subs),
    )


@router.callback_query(F.data.startswith("trends_freq_"))
async def cb_set_frequency(callback: CallbackQuery):
    """Set digest frequency for all active subscriptions"""
    frequency = callback.data.replace("trends_freq_", "")
    user_id = callback.from_user.id

    subs = await get_user_subscriptions(user_id)
    for sub in subs:
        await subscribe_user(user_id, sub.category, frequency=frequency)

    freq_label = "ежедневно" if frequency == "daily" else "еженедельно"
    await callback.answer(f"Частота: {freq_label} ✓")

    # Refresh
    subs = await get_user_subscriptions(user_id)
    await callback.message.edit_reply_markup(
        reply_markup=get_subscription_keyboard(subs),
    )


# --- Statistics ---

@router.callback_query(F.data == "trends_stats")
async def cb_stats(callback: CallbackQuery):
    """Show trend statistics"""
    stats = await get_trend_stats()

    text = (
        "<b>📊 Статистика Trend Watcher</b>\n\n"
        f"📰 Всего записей: {stats['total_entries']}\n"
        f"🕐 За 24 часа: {stats['entries_24h']}\n"
        f"📅 За 7 дней: {stats['entries_7d']}\n\n"
        f"💄 Beauty (7д): {stats['beauty_7d']}\n"
        f"🎨 Art (7д): {stats['art_7d']}\n\n"
        f"📡 Активных источников: {stats['active_sources']}\n"
        f"🔔 Подписчиков: {stats['active_subscribers']}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_trends_main_keyboard(),
    )
    await callback.answer()


# --- Search ---

@router.callback_query(F.data == "trends_search")
async def cb_search_start(callback: CallbackQuery, state: FSMContext):
    """Start trend search flow"""
    await state.set_state(TrendSearchStates.waiting_for_query)
    await callback.message.edit_text(
        "<b>🔍 Поиск трендов</b>\n\n"
        "Введите ключевое слово для поиска.\n"
        "Например: <i>retinol</i>, <i>AI art</i>, <i>sustainability</i>\n\n"
        "Отправьте /cancel для отмены."
    )
    await callback.answer()


@router.message(TrendSearchStates.waiting_for_query)
async def process_search_query(message: Message, state: FSMContext):
    """Process search query"""
    query = message.text.strip()

    if query.startswith("/cancel"):
        await state.clear()
        await message.answer(
            "Поиск отменён.",
            reply_markup=get_trends_main_keyboard(),
        )
        return

    await state.clear()

    entries = await search_trends(query)
    text = _format_trend_list(entries, f"🔍 Результаты: «{query}»")

    await message.answer(
        text,
        reply_markup=get_trends_main_keyboard(),
        disable_web_page_preview=True,
    )
