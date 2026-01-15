"""
WHOOP API интеграция
OAuth2 авторизация и получение данных
"""
import httpx
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select

from database.db import async_session
from database.models import User
import config

# WHOOP API endpoints
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v1"

# Scopes
WHOOP_SCOPES = "read:recovery read:sleep read:workout read:profile read:body_measurement"


def get_auth_url(user_id: int) -> str:
    """Генерирует URL для OAuth авторизации"""
    if not config.WHOOP_CLIENT_ID:
        return ""

    redirect_uri = f"{config.WHOOP_REDIRECT_URI}"

    params = {
        "client_id": config.WHOOP_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": WHOOP_SCOPES,
        "state": str(user_id)  # Передаём user_id для связки после callback
    }

    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{WHOOP_AUTH_URL}?{query}"


async def exchange_code_for_token(code: str) -> dict:
    """Обменивает authorization code на access token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            WHOOP_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.WHOOP_REDIRECT_URI,
                "client_id": config.WHOOP_CLIENT_ID,
                "client_secret": config.WHOOP_CLIENT_SECRET,
            }
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Обновляет access token используя refresh token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            WHOOP_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": config.WHOOP_CLIENT_ID,
                "client_secret": config.WHOOP_CLIENT_SECRET,
            }
        )
        response.raise_for_status()
        return response.json()


async def get_valid_token(user_id: int) -> Optional[str]:
    """Получает валидный access token для пользователя, обновляя если нужно"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.whoop_access_token:
            return None

        # Проверяем не истёк ли токен
        if user.whoop_token_expires and user.whoop_token_expires < datetime.utcnow():
            # Нужно обновить токен
            if not user.whoop_refresh_token:
                return None

            try:
                tokens = await refresh_access_token(user.whoop_refresh_token)
                user.whoop_access_token = tokens["access_token"]
                user.whoop_refresh_token = tokens.get("refresh_token", user.whoop_refresh_token)
                user.whoop_token_expires = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
                await session.commit()
            except Exception:
                return None

        return user.whoop_access_token


async def save_whoop_tokens(user_id: int, tokens: dict):
    """Сохраняет токены WHOOP для пользователя"""
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            user.whoop_access_token = tokens["access_token"]
            user.whoop_refresh_token = tokens.get("refresh_token")
            user.whoop_token_expires = datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))

            # Получаем WHOOP user_id
            profile = await get_profile(tokens["access_token"])
            if profile:
                user.whoop_user_id = str(profile.get("user_id"))

            await session.commit()


async def _api_request(access_token: str, endpoint: str, params: dict = None) -> dict:
    """Выполняет запрос к WHOOP API"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{WHOOP_API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params
        )
        response.raise_for_status()
        return response.json()


async def get_profile(access_token: str) -> dict:
    """Получает профиль пользователя"""
    try:
        return await _api_request(access_token, "/user/profile/basic")
    except Exception:
        return {}


async def get_recovery(user_id: int, start_date: str = None) -> dict:
    """
    Получает данные восстановления
    start_date в формате YYYY-MM-DD
    """
    token = await get_valid_token(user_id)
    if not token:
        return {"error": "Not connected"}

    params = {}
    if start_date:
        params["start"] = start_date

    try:
        return await _api_request(token, "/recovery", params)
    except Exception as e:
        return {"error": str(e)}


async def get_sleep(user_id: int, start_date: str = None) -> dict:
    """Получает данные о сне"""
    token = await get_valid_token(user_id)
    if not token:
        return {"error": "Not connected"}

    params = {}
    if start_date:
        params["start"] = start_date

    try:
        return await _api_request(token, "/activity/sleep", params)
    except Exception as e:
        return {"error": str(e)}


async def get_workouts(user_id: int, start_date: str = None) -> dict:
    """Получает данные о тренировках"""
    token = await get_valid_token(user_id)
    if not token:
        return {"error": "Not connected"}

    params = {}
    if start_date:
        params["start"] = start_date

    try:
        return await _api_request(token, "/activity/workout", params)
    except Exception as e:
        return {"error": str(e)}


async def get_body_measurement(user_id: int) -> dict:
    """Получает измерения тела"""
    token = await get_valid_token(user_id)
    if not token:
        return {"error": "Not connected"}

    try:
        return await _api_request(token, "/body_measurement")
    except Exception as e:
        return {"error": str(e)}


async def get_today_summary(user_id: int) -> dict:
    """Получает сводку за сегодня"""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    recovery = await get_recovery(user_id, today)
    sleep = await get_sleep(user_id, today)
    workouts = await get_workouts(user_id, today)

    return {
        "recovery": recovery,
        "sleep": sleep,
        "workouts": workouts
    }
