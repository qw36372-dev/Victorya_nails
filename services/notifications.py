"""
services/notifications.py — напоминания клиентам и уведомления в канал
"""

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import LEADS_CHANNEL_ID
from keyboards.inline import channel_buttons_kb

logger = logging.getLogger(__name__)

DAY_NAMES_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


# ── Напоминание клиенту ───────────────────────────────────────────────────────

async def send_reminder(bot: Bot, user_id: int, apt_id: int, reminder_type: str):
    """Отправляет напоминание о визите (24h или 2h)"""
    from storage.database import db  # отложенный импорт — избегаем кругового
    apt = db.get_appointment(apt_id)
    if not apt or apt["status"] == "cancelled":
        return

    date_obj  = datetime.strptime(apt["date"], "%Y-%m-%d")
    time_text = "завтра" if reminder_type == "24h" else "через 2 часа"
    emoji     = "🔔" if reminder_type == "24h" else "⏰"

    try:
        await bot.send_message(
            user_id,
            f"{emoji} <b>Напоминание о записи!</b>\n\n"
            f"Ваш визит <b>{time_text}</b>:\n\n"
            f"💇 {apt['service_name']}\n"
            f"👩 Мастер: {apt['master_name']}\n"
            f"📅 {DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')}\n"
            f"🕐 Время: <b>{apt['time']}</b>\n\n"
            f"📍 Адрес: ул. Цветочная, 15\n"
            f"Ждём вас! 💅🌸",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_{apt_id}")
            ]]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Reminder error for user {user_id}: {e}")


# ── Восстановление напоминаний после рестарта ────────────────────────────────

async def restore_reminders(bot: Bot, scheduler: AsyncIOScheduler):
    """Читает активные будущие записи из БД и перепланирует напоминания"""
    from storage.database import db
    appointments = db.get_active_future_appointments()
    restored = 0
    for apt in appointments:
        apt_dt   = datetime.strptime(f"{apt['date']} {apt['time']}", "%Y-%m-%d %H:%M")
        user_row = db.get_user_by_internal_id(apt["user_id"])
        if not user_row:
            continue
        tg_id = user_row["telegram_id"]
        for hours, label in [(24, "24h"), (2, "2h")]:
            run_at = apt_dt - timedelta(hours=hours)
            if run_at > datetime.now():
                scheduler.add_job(
                    send_reminder, "date", run_date=run_at,
                    args=[bot, tg_id, apt["id"], label],
                    id=f"reminder_{label}_{apt['id']}", replace_existing=True,
                )
                restored += 1
    logger.info(f"✅ Восстановлено напоминаний: {restored}")


# ── Уведомления в канал ──────────────────────────────────────────────────────

async def notify_channel_new(bot: Bot, apt_id: int, user_id: int, data: dict, user_info: dict):
    """Уведомление о новой записи в приватный канал"""
    date_obj   = datetime.strptime(data["date"], "%Y-%m-%d")
    notes_line = f"\nℹ️ Дополнительно: <i>{data['notes']}</i>" if data.get("notes") else "\nℹ️ Дополнительно: не указано"
    try:
        await bot.send_message(
            LEADS_CHANNEL_ID,
            f"🆕 <b>Новая запись! #{apt_id}</b>\n\n"
            f"👤 {user_info['name']} ({user_info['phone']})\n"
            f"💇 {data['service_name']}\n"
            f"👩 Мастер: {data['master_name']}\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} в {data['time']}"
            f"{notes_line}",
            reply_markup=channel_buttons_kb(user_id, user_info["phone"]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Channel new-booking notify error: {e}")


async def notify_channel_cancel(bot: Bot, apt: dict):
    """Уведомление об отмене записи в приватный канал"""
    date_obj  = datetime.strptime(apt["date"], "%Y-%m-%d")
    client_tg = apt.get("client_telegram_id")
    try:
        await bot.send_message(
            LEADS_CHANNEL_ID,
            f"❌ <b>Отмена записи!</b>\n\n"
            f"👤 {apt['client_name']} ({apt['client_phone']})\n"
            f"💇 {apt['service_name']}\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} в {apt['time']}",
            reply_markup=channel_buttons_kb(client_tg, apt["client_phone"]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Channel cancel notify error: {e}")
