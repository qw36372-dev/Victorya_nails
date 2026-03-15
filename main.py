"""
main.py — точка входа

Переменные окружения (задаются в панели bothost.ru):
  API_TOKEN, DATABASE_URL, LEADS_CHANNEL_ID
"""

import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import BOT_TOKEN
from handlers.admin import panel as admin_panel
from handlers.admin import slots as admin_slots
from handlers.common import start as common_start
from handlers.user import appointments as user_appointments
from handlers.user import booking as user_booking
from handlers.user import info as user_info
from services.notifications import restore_reminders

# ── Логирование ──────────────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

# Консоль
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

# Файл — максимум 5 МБ, хранить 3 последних файла
file_handler = RotatingFileHandler(
    "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter(LOG_FORMAT))

logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])
logger = logging.getLogger(__name__)


async def main():
    bot       = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    scheduler = AsyncIOScheduler()
    scheduler.start()

    await restore_reminders(bot, scheduler)

    dp = Dispatcher(storage=MemoryStorage())
    dp["scheduler"] = scheduler

    dp.include_router(common_start.router)
    dp.include_router(user_booking.router)
    dp.include_router(user_appointments.router)
    dp.include_router(user_info.router)
    dp.include_router(admin_panel.router)
    dp.include_router(admin_slots.router)

    logger.info("💅 Nail Studio Bot запущен!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
