"""
Веб-сервер для OAuth callbacks (WHOOP и др.)
"""
from aiohttp import web
from aiogram import Bot

from services.whoop import exchange_code_for_token, save_whoop_tokens
import config


async def whoop_callback(request: web.Request) -> web.Response:
    """Обработчик OAuth callback от WHOOP"""
    code = request.query.get("code")
    state = request.query.get("state")  # telegram user_id
    error = request.query.get("error")

    if error:
        return web.Response(
            text=f"""
            <html>
            <head><meta charset="utf-8"><title>Ошибка</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>❌ Ошибка авторизации</h1>
                <p>{error}</p>
                <p>Закрой это окно и попробуй снова в боте.</p>
            </body>
            </html>
            """,
            content_type="text/html"
        )

    if not code or not state:
        return web.Response(
            text="Missing code or state",
            status=400
        )

    try:
        user_id = int(state)

        # Обмениваем код на токен
        tokens = await exchange_code_for_token(code)

        # Сохраняем токены
        await save_whoop_tokens(user_id, tokens)

        # Отправляем сообщение в Telegram
        bot: Bot = request.app["bot"]
        await bot.send_message(
            user_id,
            "✅ **WHOOP успешно подключен!**\n\n"
            "Теперь ты можешь:\n"
            "• Смотреть Recovery Score\n"
            "• Отслеживать сон\n"
            "• Синхронизировать тренировки\n\n"
            "Используй /whoop для просмотра данных!",
            parse_mode="Markdown"
        )

        return web.Response(
            text="""
            <html>
            <head>
                <meta charset="utf-8">
                <title>WHOOP подключен!</title>
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        text-align: center;
                        padding: 50px;
                        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                        color: white;
                        min-height: 100vh;
                        margin: 0;
                    }
                    .container {
                        max-width: 400px;
                        margin: 0 auto;
                    }
                    h1 { font-size: 48px; margin-bottom: 10px; }
                    p { font-size: 18px; opacity: 0.9; }
                    .success { color: #00ff88; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>✅</h1>
                    <h2 class="success">WHOOP подключен!</h2>
                    <p>Можешь закрыть это окно и вернуться в Telegram.</p>
                </div>
            </body>
            </html>
            """,
            content_type="text/html"
        )

    except Exception as e:
        return web.Response(
            text=f"""
            <html>
            <head><meta charset="utf-8"><title>Ошибка</title></head>
            <body style="font-family: Arial; text-align: center; padding: 50px;">
                <h1>❌ Ошибка</h1>
                <p>{str(e)}</p>
            </body>
            </html>
            """,
            content_type="text/html"
        )


async def health_check(request: web.Request) -> web.Response:
    """Health check endpoint"""
    return web.Response(text="OK")


def create_app(bot: Bot) -> web.Application:
    """Создаёт aiohttp приложение"""
    app = web.Application()
    app["bot"] = bot

    app.router.add_get("/whoop/callback", whoop_callback)
    app.router.add_get("/health", health_check)

    return app


async def start_webhook_server(bot: Bot, host: str = "0.0.0.0", port: int = 8080):
    """Запускает веб-сервер"""
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
