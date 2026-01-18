import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Claude API (Anthropic)
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Z.AI API (fallback)
ZAI_API_KEY = os.getenv("ZAI_API_KEY")
ZAI_API_URL = os.getenv("ZAI_API_URL", "https://api.z.ai/api/paas/v4/chat/completions")
ZAI_MODEL = os.getenv("ZAI_MODEL", "GLM-4.6V-Flash")

# Database
DATABASE_URL = os.getenv("DATABASE_URL")

# Default goals
DEFAULT_WATER_GOAL = int(os.getenv("DEFAULT_WATER_GOAL", 2000))  # мл
DEFAULT_CALORIE_GOAL = int(os.getenv("DEFAULT_CALORIE_GOAL", 2000))  # ккал
