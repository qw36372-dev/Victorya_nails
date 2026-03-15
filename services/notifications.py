"""
services/notifications.py — напоминания клиентам и уведомления в канал
"""

import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import LEADS_CHANNEL_ID, SALON_ADDRESS

logger = logging.getLogger(__name__)

DAY_NAMES_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


# ── Напоминание клиенту (только для active записей) ───────────────────────────

async def send_reminder(bot: Bot, user_id: int, apt_id: int, reminder_type: str):
    from storage.database import db
    apt = db.get_appointment(apt_id)
    if not apt or apt["status"] != "active":
        return

    date_obj  = datetime.strptime(apt["date"], "%Y-%m-%d")
    time_text = "завтра" if reminder_type == "24h" else "через 2 часа"
    emoji     = "🔔" if reminder_type == "24h" else "⏰"

    try:
        await bot.send_message(
            user_id,
            f"{emoji} <b>Напоминание о записи!</b>\n\n"
            f"Ваш визит <b>{time_text}</b>:\n\n"
            f"💅 {apt['service_name']}\n"
            f"📅 {DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')}\n"
            f"🕐 Время: <b>{apt['time']}</b>\n\n"
            f"📍 Адрес: {SALON_ADDRESS}\n"
            f"Жду вас! 💅🌸",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_{apt_id}")
            ]]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Reminder error for user {user_id}: {e}")


# ── Восстановление напоминаний после рестарта ─────────────────────────────────

async def restore_reminders(bot: Bot, scheduler: AsyncIOScheduler):
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


# ── Уведомление в канал: новая ПРЕДВАРИТЕЛЬНАЯ запись ────────────────────────

async def notify_channel_new(bot: Bot, apt_id: int, user_id: int, data: dict, user_info: dict):
    date_obj   = datetime.strptime(data["date"], "%Y-%m-%d")
    notes_line = f"\nℹ️ Пожелания: <i>{data['notes']}</i>" if data.get("notes") else ""

    # Кнопки для мастера прямо в канале
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить",       callback_data=f"apt_confirm_{apt_id}"),
            InlineKeyboardButton(text="❌ Отменить",          callback_data=f"apt_cancel_{apt_id}"),
        ],
        [
            InlineKeyboardButton(text="⏰ Предложить другое время", callback_data=f"apt_reschedule_{apt_id}"),
        ],
        [
            InlineKeyboardButton(text="✉️ Написать клиенту", url=f"tg://user?id={user_id}"),
            InlineKeyboardButton(text="📞 Позвонить",         url=f"tel:+{''.join(filter(str.isdigit, user_info['phone']))}"),
        ],
    ])

    try:
        await bot.send_message(
            LEADS_CHANNEL_ID,
            f"🆕 <b>Новая заявка на запись! #{apt_id}</b>\n\n"
            f"👤 {user_info['name']} ({user_info['phone']})\n"
            f"💅 {data['service_name']}\n"
            f"📅 {DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')} в {data['time']}"
            f"{notes_line}\n\n"
            f"⏳ <i>Ожидает подтверждения</i>",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Channel new-booking notify error: {e}")


# ── Уведомление об отмене клиентом ───────────────────────────────────────────

async def notify_channel_cancel(bot: Bot, apt: dict):
    date_obj  = datetime.strptime(apt["date"], "%Y-%m-%d")
    client_tg = apt.get("client_telegram_id")
    digits    = "".join(filter(str.isdigit, apt["client_phone"]))
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✉️ Написать клиенту", url=f"tg://user?id={client_tg}"),
        InlineKeyboardButton(text="📞 Позвонить",         url=f"tel:+{digits}"),
    ]])
    try:
        await bot.send_message(
            LEADS_CHANNEL_ID,
            f"❌ <b>Клиент отменил запись!</b>\n\n"
            f"👤 {apt['client_name']} ({apt['client_phone']})\n"
            f"💅 {apt['service_name']}\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} в {apt['time']}",
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Channel cancel notify error: {e}")


# ── Уведомление клиенту: запись подтверждена ─────────────────────────────────

async def notify_client_confirmed(bot: Bot, apt: dict):
    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
    try:
        await bot.send_message(
            apt["client_telegram_id"],
            f"✅ <b>Ваша запись подтверждена!</b>\n\n"
            f"💅 {apt['service_name']}\n"
            f"📅 {DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n\n"
            f"📍 {SALON_ADDRESS}\n\n"
            f"Жду вас! 💅🌸",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отменить запись", callback_data=f"cancel_{apt['id']}")]
            ]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Notify confirmed error: {e}")


# ── Уведомление клиенту: запись отменена мастером ────────────────────────────

async def notify_client_cancelled_by_master(bot: Bot, apt: dict):
    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
    try:
        await bot.send_message(
            apt["client_telegram_id"],
            f"😔 <b>К сожалению, ваша запись отменена.</b>\n\n"
            f"💅 {apt['service_name']}\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n\n"
            f"Пожалуйста, выберите другое удобное время для записи.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💅 Записаться снова", callback_data="book")]
            ]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Notify cancelled-by-master error: {e}")


# ── Уведомление клиенту: предложение другого времени ─────────────────────────

async def notify_client_reschedule_offer(bot: Bot, apt: dict, new_date: str, new_time: str):
    old_date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
    new_date_obj = datetime.strptime(new_date, "%Y-%m-%d")
    try:
        await bot.send_message(
            apt["client_telegram_id"],
            f"⏰ <b>Мастер предлагает перенести запись</b>\n\n"
            f"💅 {apt['service_name']}\n\n"
            f"Было: {DAY_NAMES_FULL[old_date_obj.weekday()]}, {old_date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n"
            f"Новое время: <b>{DAY_NAMES_FULL[new_date_obj.weekday()]}, {new_date_obj.strftime('%d.%m.%Y')} в {new_time}</b>\n\n"
            f"Вы согласны?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять",  callback_data=f"reschedule_accept_{apt['id']}_{new_date}_{new_time}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reschedule_decline_{apt['id']}"),
                ]
            ]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error(f"Notify reschedule offer error: {e}")
