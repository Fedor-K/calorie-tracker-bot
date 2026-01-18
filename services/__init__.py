from services.ai import (
    analyze_food_image,
    estimate_activity_calories,
    generate_meal_plan,
    process_message,
    COACH_TOOLS
)
from services.scheduler import setup_scheduler
from services.memory import (
    save_message,
    get_recent_messages,
    save_memory,
    get_memories,
    get_memories_as_text
)
from services.coach import (
    handle_message,
    handle_photo_message,
    get_user_context,
    execute_tool
)

__all__ = [
    # AI
    "analyze_food_image",
    "estimate_activity_calories",
    "generate_meal_plan",
    "process_message",
    "COACH_TOOLS",
    # Scheduler
    "setup_scheduler",
    # Memory
    "save_message",
    "get_recent_messages",
    "save_memory",
    "get_memories",
    "get_memories_as_text",
    # Coach
    "handle_message",
    "handle_photo_message",
    "get_user_context",
    "execute_tool"
]
