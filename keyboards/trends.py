"""Keyboards for Trend Watcher feature"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_trends_main_keyboard() -> InlineKeyboardMarkup:
    """Main trend watcher menu"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💄 Beauty Trends", callback_data="trends_top_beauty"),
            InlineKeyboardButton(text="🎨 Art Trends", callback_data="trends_top_art"),
        ],
        [
            InlineKeyboardButton(text="📰 Дайджест", callback_data="trends_digest_both"),
        ],
        [
            InlineKeyboardButton(text="🔔 Подписки", callback_data="trends_subscriptions"),
            InlineKeyboardButton(text="📊 Статистика", callback_data="trends_stats"),
        ],
        [
            InlineKeyboardButton(text="🔍 Поиск", callback_data="trends_search"),
        ],
    ])


def get_trends_category_keyboard(category: str) -> InlineKeyboardMarkup:
    """Category-specific trend navigation"""
    rows = [
        [
            InlineKeyboardButton(
                text="📈 Топ за день",
                callback_data=f"trends_top_{category}_24h",
            ),
            InlineKeyboardButton(
                text="📅 Топ за неделю",
                callback_data=f"trends_top_{category}_7d",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📰 Дайджест",
                callback_data=f"trends_digest_{category}",
            ),
        ],
    ]

    if category == "beauty":
        rows.append([
            InlineKeyboardButton(text="💆 Skincare", callback_data="trends_sub_skincare"),
            InlineKeyboardButton(text="💋 Makeup", callback_data="trends_sub_makeup"),
            InlineKeyboardButton(text="💇 Haircare", callback_data="trends_sub_haircare"),
        ])
        rows.append([
            InlineKeyboardButton(text="🌿 Wellness", callback_data="trends_sub_wellness"),
            InlineKeyboardButton(text="🧪 Ingredients", callback_data="trends_sub_ingredients"),
            InlineKeyboardButton(text="🇰🇷 K-Beauty", callback_data="trends_sub_k-beauty"),
        ])
    elif category == "art":
        rows.append([
            InlineKeyboardButton(text="🖼 Contemporary", callback_data="trends_sub_contemporary"),
            InlineKeyboardButton(text="💻 Digital Art", callback_data="trends_sub_digital-art"),
            InlineKeyboardButton(text="📸 Photography", callback_data="trends_sub_photography"),
        ])
        rows.append([
            InlineKeyboardButton(text="🏛 Exhibitions", callback_data="trends_sub_exhibitions"),
            InlineKeyboardButton(text="💰 Auctions", callback_data="trends_sub_auctions"),
            InlineKeyboardButton(text="🌟 Emerging", callback_data="trends_sub_emerging-artists"),
        ])

    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="trends_main"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_subscription_keyboard(user_subs: list) -> InlineKeyboardMarkup:
    """Subscription management keyboard"""
    active_cats = {s.category for s in user_subs}

    beauty_icon = "✅" if "beauty" in active_cats else "➕"
    art_icon = "✅" if "art" in active_cats else "➕"
    both_icon = "✅" if "both" in active_cats else "➕"

    rows = [
        [
            InlineKeyboardButton(
                text=f"{beauty_icon} Beauty",
                callback_data="trends_toggle_sub_beauty",
            ),
            InlineKeyboardButton(
                text=f"{art_icon} Art",
                callback_data="trends_toggle_sub_art",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"{both_icon} Beauty + Art",
                callback_data="trends_toggle_sub_both",
            ),
        ],
    ]

    # Frequency selection if any subscriptions exist
    if active_cats:
        rows.append([
            InlineKeyboardButton(text="📅 Ежедневно", callback_data="trends_freq_daily"),
            InlineKeyboardButton(text="📆 Еженедельно", callback_data="trends_freq_weekly"),
        ])

    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="trends_main"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_trend_entry_keyboard(entry_url: str | None) -> InlineKeyboardMarkup:
    """Keyboard for individual trend entry"""
    rows = []
    if entry_url:
        rows.append([
            InlineKeyboardButton(text="🔗 Читать", url=entry_url),
        ])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="trends_main"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)
