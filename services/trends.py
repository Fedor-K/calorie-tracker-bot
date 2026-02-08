"""
Trend Watcher Service
Collects, analyzes, and delivers beauty & art market trends.

Sources:
- RSS feeds from beauty blogs, art magazines, industry publications
- Web scraping of trending topics
- AI-powered analysis and scoring via Claude
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from xml.etree import ElementTree

import httpx
from sqlalchemy import select, func, delete, and_

import config
from database.db import async_session
from database.models import TrendSource, TrendEntry, TrendDigest, TrendSubscription, User

logger = logging.getLogger(__name__)


# ============================================================================
# Default Sources
# ============================================================================

DEFAULT_SOURCES = [
    # Beauty sources
    {
        "name": "Allure",
        "url": "https://www.allure.com/feed/rss",
        "source_type": "rss",
        "category": "beauty",
        "language": "en",
    },
    {
        "name": "Byrdie",
        "url": "https://www.byrdie.com/rss",
        "source_type": "rss",
        "category": "beauty",
        "language": "en",
    },
    {
        "name": "Cosmopolitan Beauty",
        "url": "https://www.cosmopolitan.com/style-beauty/rss",
        "source_type": "rss",
        "category": "beauty",
        "language": "en",
    },
    {
        "name": "Vogue Beauty",
        "url": "https://www.vogue.com/feed/rss",
        "source_type": "rss",
        "category": "beauty",
        "language": "en",
    },
    {
        "name": "BeautyIndependent",
        "url": "https://www.beautyindependent.com/feed/",
        "source_type": "rss",
        "category": "beauty",
        "language": "en",
    },
    # Art sources
    {
        "name": "Artnet News",
        "url": "https://news.artnet.com/feed",
        "source_type": "rss",
        "category": "art",
        "language": "en",
    },
    {
        "name": "Hyperallergic",
        "url": "https://hyperallergic.com/feed/",
        "source_type": "rss",
        "category": "art",
        "language": "en",
    },
    {
        "name": "ARTnews",
        "url": "https://www.artnews.com/feed/",
        "source_type": "rss",
        "category": "art",
        "language": "en",
    },
    {
        "name": "The Art Newspaper",
        "url": "https://www.theartnewspaper.com/rss",
        "source_type": "rss",
        "category": "art",
        "language": "en",
    },
    {
        "name": "Colossal",
        "url": "https://www.thisiscolossal.com/feed/",
        "source_type": "rss",
        "category": "art",
        "language": "en",
    },
]


# ============================================================================
# Subcategory definitions
# ============================================================================

BEAUTY_SUBCATEGORIES = [
    "skincare", "makeup", "haircare", "fragrance", "nails",
    "wellness", "ingredients", "sustainability", "celebrity",
    "k-beauty", "indie-brands", "tools-devices"
]

ART_SUBCATEGORIES = [
    "contemporary", "digital-art", "photography", "sculpture",
    "street-art", "exhibitions", "auctions", "art-market",
    "emerging-artists", "art-tech", "nft", "installations"
]

ALL_CATEGORIES = {
    "beauty": BEAUTY_SUBCATEGORIES,
    "art": ART_SUBCATEGORIES,
}


# ============================================================================
# Source Management
# ============================================================================

async def init_default_sources():
    """Seed default trend sources if none exist"""
    async with async_session() as session:
        result = await session.execute(select(func.count(TrendSource.id)))
        count = result.scalar_one()

        if count == 0:
            logger.info("[Trends] Seeding default sources...")
            for src_data in DEFAULT_SOURCES:
                source = TrendSource(**src_data)
                session.add(source)
            await session.commit()
            logger.info(f"[Trends] Added {len(DEFAULT_SOURCES)} default sources")


async def get_active_sources(category: Optional[str] = None) -> list[TrendSource]:
    """Get all active trend sources, optionally filtered by category"""
    async with async_session() as session:
        query = select(TrendSource).where(TrendSource.is_active == True)
        if category and category != "both":
            query = query.where(TrendSource.category == category)
        result = await session.execute(query)
        return result.scalars().all()


# ============================================================================
# RSS Feed Parsing
# ============================================================================

def _parse_rss_date(date_str: str) -> Optional[datetime]:
    """Parse various RSS date formats"""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).replace(tzinfo=None)
        except (ValueError, AttributeError):
            continue
    return None


def _strip_html(text: str) -> str:
    """Remove HTML tags from text"""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:500]  # Cap summary length


def _extract_image_from_content(content: str) -> Optional[str]:
    """Try to extract first image URL from HTML content"""
    if not content:
        return None
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    return match.group(1) if match else None


async def fetch_rss_feed(source: TrendSource) -> list[dict]:
    """Fetch and parse an RSS feed, returning raw entry dicts"""
    entries = []
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(source.url, headers={
                "User-Agent": "TrendWatcherBot/1.0 (RSS reader)"
            })
            resp.raise_for_status()

        root = ElementTree.fromstring(resp.text)

        # Handle both RSS 2.0 and Atom feeds
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # RSS 2.0
        items = root.findall(".//item")
        if items:
            for item in items[:20]:  # Limit per feed
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                description = item.findtext("description", "")
                pub_date = item.findtext("pubDate", "")
                content_encoded = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")

                image_url = _extract_image_from_content(content_encoded or description)

                entries.append({
                    "title": title,
                    "url": link,
                    "summary": _strip_html(description),
                    "image_url": image_url,
                    "published_at": _parse_rss_date(pub_date) if pub_date else None,
                })
        else:
            # Atom format
            atom_entries = root.findall("atom:entry", ns)
            for entry in atom_entries[:20]:
                title = entry.findtext("atom:title", "", ns).strip()
                link_el = entry.find("atom:link", ns)
                link = link_el.get("href", "") if link_el is not None else ""
                summary = entry.findtext("atom:summary", "", ns)
                updated = entry.findtext("atom:updated", "", ns)
                content = entry.findtext("atom:content", "", ns)

                image_url = _extract_image_from_content(content or summary)

                entries.append({
                    "title": title,
                    "url": link,
                    "summary": _strip_html(summary),
                    "image_url": image_url,
                    "published_at": _parse_rss_date(updated) if updated else None,
                })

    except Exception as e:
        logger.warning(f"[Trends] Failed to fetch RSS from {source.name}: {e}")

    return entries


# ============================================================================
# Trend Collection
# ============================================================================

async def collect_trends(category: Optional[str] = None) -> int:
    """
    Collect trends from all active sources.
    Returns number of new entries added.
    """
    sources = await get_active_sources(category)
    new_count = 0

    for source in sources:
        if source.source_type == "rss":
            raw_entries = await fetch_rss_feed(source)
        else:
            logger.info(f"[Trends] Skipping unsupported source type: {source.source_type}")
            continue

        if not raw_entries:
            continue

        async with async_session() as session:
            for entry_data in raw_entries:
                # Skip entries without titles
                if not entry_data.get("title"):
                    continue

                # Dedup by URL
                if entry_data.get("url"):
                    existing = await session.execute(
                        select(TrendEntry).where(TrendEntry.url == entry_data["url"])
                    )
                    if existing.scalar_one_or_none():
                        continue

                trend_entry = TrendEntry(
                    source_id=source.id,
                    title=entry_data["title"],
                    url=entry_data.get("url"),
                    summary=entry_data.get("summary"),
                    category=source.category,
                    image_url=entry_data.get("image_url"),
                    published_at=entry_data.get("published_at"),
                    trend_score=0.0,  # Will be scored by AI later
                )
                session.add(trend_entry)
                new_count += 1

            # Update last fetched timestamp
            src = await session.get(TrendSource, source.id)
            if src:
                src.last_fetched_at = datetime.now(timezone.utc)

            await session.commit()

    logger.info(f"[Trends] Collected {new_count} new entries")
    return new_count


# ============================================================================
# AI-Powered Trend Analysis
# ============================================================================

async def analyze_and_score_trends(category: Optional[str] = None, hours: int = 24) -> int:
    """
    Use Claude to analyze recent unscored trends:
    - Assign subcategories
    - Generate tags
    - Score trend momentum (0-100)
    - Detect sentiment

    Returns number of entries analyzed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with async_session() as session:
        query = (
            select(TrendEntry)
            .where(TrendEntry.trend_score == 0.0)
            .where(TrendEntry.fetched_at >= cutoff)
        )
        if category and category != "both":
            query = query.where(TrendEntry.category == category)

        result = await session.execute(query)
        entries = result.scalars().all()

    if not entries:
        return 0

    # Process in batches of 10
    batch_size = 10
    analyzed = 0

    for i in range(0, len(entries), batch_size):
        batch = entries[i:i + batch_size]
        entries_text = "\n".join([
            f"[{e.id}] ({e.category}) {e.title} | {(e.summary or '')[:150]}"
            for e in batch
        ])

        prompt = f"""Analyze these beauty/art market trend entries.
For each entry, determine:
1. subcategory (beauty: {', '.join(BEAUTY_SUBCATEGORIES)} | art: {', '.join(ART_SUBCATEGORIES)})
2. tags (3-5 comma-separated keywords)
3. trend_score (0-100, how trending/impactful is this topic right now)
4. sentiment (positive, neutral, negative)

Entries:
{entries_text}

Reply ONLY with valid JSON array, no markdown:
[
  {{"id": 123, "subcategory": "skincare", "tags": "retinol, anti-aging, k-beauty", "trend_score": 75, "sentiment": "positive"}},
  ...
]"""

        try:
            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}]
            }
            headers = {
                "x-api-key": config.CLAUDE_API_KEY,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                ai_result = resp.json()

            content = ai_result["content"][0]["text"].strip()
            # Clean markdown wrappers
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            if content.endswith("```"):
                content = content[:-3]

            scored_entries = json.loads(content.strip())

            # Update entries in DB
            async with async_session() as session:
                for scored in scored_entries:
                    entry = await session.get(TrendEntry, scored["id"])
                    if entry:
                        entry.subcategory = scored.get("subcategory")
                        entry.tags = scored.get("tags")
                        entry.trend_score = float(scored.get("trend_score", 1))
                        entry.sentiment = scored.get("sentiment")
                        analyzed += 1
                await session.commit()

        except Exception as e:
            logger.error(f"[Trends] AI analysis batch failed: {e}")
            continue

    logger.info(f"[Trends] Analyzed {analyzed} entries")
    return analyzed


# ============================================================================
# Digest Generation
# ============================================================================

async def generate_digest(category: str = "both", period: str = "daily") -> Optional[TrendDigest]:
    """
    Generate an AI-powered trend digest for a given category and period.
    Returns the created TrendDigest or None.
    """
    if period == "daily":
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    else:
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=1)

    async with async_session() as session:
        query = (
            select(TrendEntry)
            .where(TrendEntry.fetched_at >= cutoff)
            .where(TrendEntry.trend_score > 0)
            .order_by(TrendEntry.trend_score.desc())
        )
        if category != "both":
            query = query.where(TrendEntry.category == category)

        query = query.limit(30)
        result = await session.execute(query)
        entries = result.scalars().all()

    if not entries:
        return None

    entries_text = "\n".join([
        f"- [{e.category.upper()}] {e.title} (score: {e.trend_score}, tags: {e.tags or 'n/a'}) — {(e.summary or '')[:100]}"
        for e in entries
    ])

    category_label = {
        "beauty": "Beauty Market",
        "art": "Art Market",
        "both": "Beauty & Art Markets",
    }.get(category, category)

    period_label = "Daily" if period == "daily" else "Weekly"

    prompt = f"""You are a trend analyst for the {category_label}.
Create a concise {period_label.lower()} trend digest based on these entries:

{entries_text}

Write in Russian. Structure your digest:

1. **Headline** — catchy title for this digest
2. **Top 3-5 trends** — each with a brief explanation (2-3 sentences) of why it matters
3. **Market signals** — what these trends mean for professionals in {category_label.lower()}
4. **What to watch** — emerging topics that may grow

Keep it actionable and insightful. Use emojis sparingly. Total length: 300-500 words.
Format in Telegram-compatible HTML (<b>, <i>, <a href>, no markdown).
Do NOT wrap in ```."""

    try:
        payload = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}]
        }
        headers = {
            "x-api-key": config.CLAUDE_API_KEY,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            ai_result = resp.json()

        content = ai_result["content"][0]["text"].strip()

        # Extract title from first line
        lines = content.split("\n")
        title = _strip_html(lines[0]).strip("# ").strip() if lines else f"{period_label} {category_label} Digest"

        top_trends = json.dumps([e.title for e in entries[:5]], ensure_ascii=False)
        entry_ids = json.dumps([e.id for e in entries])

        async with async_session() as session:
            digest = TrendDigest(
                category=category,
                period=period,
                title=title,
                content=content,
                top_trends=top_trends,
                entry_ids=entry_ids,
            )
            session.add(digest)
            await session.commit()
            await session.refresh(digest)

        logger.info(f"[Trends] Generated {period} digest for {category}: {title}")
        return digest

    except Exception as e:
        logger.error(f"[Trends] Digest generation failed: {e}")
        return None


# ============================================================================
# Subscription Management
# ============================================================================

async def subscribe_user(user_id: int, category: str, frequency: str = "daily") -> TrendSubscription:
    """Subscribe a user to trend updates for a category"""
    async with async_session() as session:
        existing = await session.execute(
            select(TrendSubscription).where(
                and_(
                    TrendSubscription.user_id == user_id,
                    TrendSubscription.category == category,
                )
            )
        )
        sub = existing.scalar_one_or_none()

        if sub:
            sub.is_active = True
            sub.frequency = frequency
        else:
            sub = TrendSubscription(
                user_id=user_id,
                category=category,
                frequency=frequency,
            )
            session.add(sub)

        await session.commit()
        await session.refresh(sub)
        return sub


async def unsubscribe_user(user_id: int, category: str) -> bool:
    """Unsubscribe a user from trend updates"""
    async with async_session() as session:
        existing = await session.execute(
            select(TrendSubscription).where(
                and_(
                    TrendSubscription.user_id == user_id,
                    TrendSubscription.category == category,
                )
            )
        )
        sub = existing.scalar_one_or_none()
        if sub:
            sub.is_active = False
            await session.commit()
            return True
        return False


async def get_user_subscriptions(user_id: int) -> list[TrendSubscription]:
    """Get all active subscriptions for a user"""
    async with async_session() as session:
        result = await session.execute(
            select(TrendSubscription).where(
                and_(
                    TrendSubscription.user_id == user_id,
                    TrendSubscription.is_active == True,
                )
            )
        )
        return result.scalars().all()


# ============================================================================
# Trend Queries
# ============================================================================

async def get_top_trends(
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    hours: int = 24,
    limit: int = 10,
) -> list[TrendEntry]:
    """Get top trending entries by score"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with async_session() as session:
        query = (
            select(TrendEntry)
            .where(TrendEntry.fetched_at >= cutoff)
            .where(TrendEntry.trend_score > 0)
            .order_by(TrendEntry.trend_score.desc())
        )
        if category and category != "both":
            query = query.where(TrendEntry.category == category)
        if subcategory:
            query = query.where(TrendEntry.subcategory == subcategory)

        query = query.limit(limit)
        result = await session.execute(query)
        return result.scalars().all()


async def search_trends(query_text: str, category: Optional[str] = None, limit: int = 10) -> list[TrendEntry]:
    """Search trends by keyword in title/summary/tags"""
    async with async_session() as session:
        pattern = f"%{query_text.lower()}%"
        query = (
            select(TrendEntry)
            .where(
                (func.lower(TrendEntry.title).like(pattern))
                | (func.lower(TrendEntry.summary).like(pattern))
                | (func.lower(TrendEntry.tags).like(pattern))
            )
            .order_by(TrendEntry.trend_score.desc())
        )
        if category and category != "both":
            query = query.where(TrendEntry.category == category)

        query = query.limit(limit)
        result = await session.execute(query)
        return result.scalars().all()


async def get_latest_digest(category: str = "both", period: str = "daily") -> Optional[TrendDigest]:
    """Get the most recent digest for a category"""
    async with async_session() as session:
        query = (
            select(TrendDigest)
            .where(TrendDigest.category == category)
            .where(TrendDigest.period == period)
            .order_by(TrendDigest.created_at.desc())
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()


async def get_trend_stats() -> dict:
    """Get overall trend statistics"""
    cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)

    async with async_session() as session:
        # Total entries
        total = await session.execute(select(func.count(TrendEntry.id)))
        total_count = total.scalar_one()

        # Last 24h
        recent = await session.execute(
            select(func.count(TrendEntry.id)).where(TrendEntry.fetched_at >= cutoff_24h)
        )
        recent_count = recent.scalar_one()

        # Last 7 days
        week = await session.execute(
            select(func.count(TrendEntry.id)).where(TrendEntry.fetched_at >= cutoff_7d)
        )
        week_count = week.scalar_one()

        # By category
        beauty_count = await session.execute(
            select(func.count(TrendEntry.id))
            .where(TrendEntry.category == "beauty")
            .where(TrendEntry.fetched_at >= cutoff_7d)
        )
        art_count = await session.execute(
            select(func.count(TrendEntry.id))
            .where(TrendEntry.category == "art")
            .where(TrendEntry.fetched_at >= cutoff_7d)
        )

        # Active sources
        sources = await session.execute(
            select(func.count(TrendSource.id)).where(TrendSource.is_active == True)
        )

        # Active subscribers
        subs = await session.execute(
            select(func.count(TrendSubscription.id)).where(TrendSubscription.is_active == True)
        )

    return {
        "total_entries": total_count,
        "entries_24h": recent_count,
        "entries_7d": week_count,
        "beauty_7d": beauty_count.scalar_one(),
        "art_7d": art_count.scalar_one(),
        "active_sources": sources.scalar_one(),
        "active_subscribers": subs.scalar_one(),
    }


# ============================================================================
# Cleanup
# ============================================================================

async def cleanup_old_entries(days: int = 30):
    """Remove trend entries older than N days"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session() as session:
        result = await session.execute(
            delete(TrendEntry).where(TrendEntry.created_at < cutoff)
        )
        await session.commit()
        logger.info(f"[Trends] Cleaned up {result.rowcount} old entries")
