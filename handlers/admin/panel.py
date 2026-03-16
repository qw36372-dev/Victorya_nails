"""
handlers/admin/panel.py — панель администратора + подтверждение/отмена/перенос записей
"""

from datetime import date, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_IDS
from keyboards.inline import (
    admin_menu_kb, back_kb,
    reschedule_calendar_kb, reschedule_times_kb,
)
from services.notifications import (
    notify_client_confirmed,
    notify_client_cancelled_by_master,
    notify_client_reschedule_offer,
    send_reminder,
)
from services.schedule import get_available_slots
from states import Admin, AdminReschedule
from storage.database import db

router = Router()


# ── Главное меню ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin")
async def cb_admin(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.set_state(Admin.menu)

    today     = datetime.now().strftime("%Y-%m-%d")
    today_apt = db.get_appointments_by_date(today)
    pending   = db.get_pending_appointments()
    pending_line = f"\n⏳ Ожидают подтверждения: <b>{len(pending)}</b>" if pending else ""

    await cb.message.edit_text(
        f"⚙️ <b>Панель администратора</b>\n\n"
        f"👥 Всего клиентов: <b>{db.get_total_users()}</b>\n"
        f"📅 Записей сегодня: <b>{len(today_apt)}</b>"
        f"{pending_line}",
        reply_markup=admin_menu_kb(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ── Записи сегодня / завтра ───────────────────────────────────────────────────

@router.callback_query(Admin.menu, F.data.in_({"admin_today", "admin_tomorrow"}))
async def cb_admin_appointments(cb: CallbackQuery):
    if "today" in cb.data:
        target = datetime.now().strftime("%Y-%m-%d")
        label  = "сегодня"
    else:
        target = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        label  = "завтра"

    apts     = db.get_appointments_by_date(target)
    date_obj = datetime.strptime(target, "%Y-%m-%d")

    if not apts:
        text = f"📅 Записей {label} ({date_obj.strftime('%d.%m.%Y')}) нет."
    else:
        text = f"📅 <b>Записи {label} ({date_obj.strftime('%d.%m.%Y')}):</b>\n\n"
        for apt in sorted(apts, key=lambda x: x["time"]):
            icon = "✅" if apt["status"] == "active" else "⏳"
            text += (
                f"{icon} <b>{apt['time']}</b> — {apt['service_name']}\n"
                f"   👤 {apt['client_name']} ({apt['client_phone']})\n\n"
            )

    await cb.message.edit_text(text, reply_markup=back_kb("admin"), parse_mode=ParseMode.HTML)
    await cb.answer()


# ── Статистика ────────────────────────────────────────────────────────────────

@router.callback_query(Admin.menu, F.data == "admin_stats")
async def cb_admin_stats(cb: CallbackQuery):
    stats = db.get_stats()
    await cb.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Всего клиентов: <b>{stats['total_users']}</b>\n"
        f"📅 Всего записей: <b>{stats['total_appointments']}</b>\n"
        f"⏳ Ожидают подтверждения: <b>{stats.get('pending_appointments', 0)}</b>\n"
        f"✅ Подтверждённых: <b>{stats['active_appointments']}</b>\n"
        f"❌ Отменено: <b>{stats['cancelled_appointments']}</b>\n"
        f"💰 Выручка (ожид.): <b>{stats['expected_revenue']}₽</b>",
        reply_markup=back_kb("admin"),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ── Подтверждение записи ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("apt_confirm_"))
async def cb_apt_confirm(cb: CallbackQuery, bot: Bot, scheduler):
    apt_id = int(cb.data.split("_")[2])
    apt    = db.get_appointment(apt_id)

    if not apt:
        await cb.answer("Запись не найдена", show_alert=True)
        return
    if apt["status"] == "active":
        await cb.answer("Запись уже подтверждена ✅", show_alert=True)
        return
    if apt["status"] == "cancelled":
        await cb.answer("Запись уже отменена ❌", show_alert=True)
        return

    db.confirm_appointment(apt_id)
    apt = db.get_appointment(apt_id)

    apt_dt = datetime.strptime(f"{apt['date']} {apt['time']}", "%Y-%m-%d %H:%M")
    for hours, label in [(24, "24h"), (2, "2h")]:
        run_at = apt_dt - timedelta(hours=hours)
        if run_at > datetime.now():
            scheduler.add_job(
                send_reminder, "date", run_date=run_at,
                args=[bot, apt["client_telegram_id"], apt_id, label],
                id=f"reminder_{label}_{apt_id}", replace_existing=True,
            )

    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
    try:
        await cb.message.edit_text(
            f"✅ <b>Запись подтверждена! #{apt_id}</b>\n\n"
            f"👤 {apt['client_name']} ({apt['client_phone']})\n"
            f"💅 {apt['service_name']}\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n\n"
            f"<i>Подтверждено мастером</i>",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    await notify_client_confirmed(bot, apt)
    await cb.answer("✅ Запись подтверждена, клиент уведомлён")


# ── Отмена записи мастером ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("apt_cancel_"))
async def cb_apt_cancel(cb: CallbackQuery, bot: Bot, scheduler):
    apt_id = int(cb.data.split("_")[2])
    apt    = db.get_appointment(apt_id)

    if not apt:
        await cb.answer("Запись не найдена", show_alert=True)
        return
    if apt["status"] == "cancelled":
        await cb.answer("Запись уже отменена", show_alert=True)
        return

    db.cancel_appointment(apt_id)

    for job_id in [f"reminder_24h_{apt_id}", f"reminder_2h_{apt_id}"]:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
    try:
        await cb.message.edit_text(
            f"❌ <b>Запись отменена мастером #{apt_id}</b>\n\n"
            f"👤 {apt['client_name']} ({apt['client_phone']})\n"
            f"💅 {apt['service_name']}\n"
            f"📅 {date_obj.strftime('%d.%m.%Y')} в {apt['time']}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    await notify_client_cancelled_by_master(bot, apt)
    await cb.answer("❌ Запись отменена, клиент уведомлён")


# ── Перенос: мастер открывает календарь ──────────────────────────────────────

@router.callback_query(F.data.startswith("apt_reschedule_"))
async def cb_apt_reschedule(cb: CallbackQuery, state: FSMContext):
    apt_id = int(cb.data.split("_")[2])
    apt    = db.get_appointment(apt_id)

    if not apt:
        await cb.answer("Запись не найдена", show_alert=True)
        return
    if apt["status"] == "cancelled":
        await cb.answer("Запись уже отменена", show_alert=True)
        return

    await state.update_data(reschedule_apt_id=apt_id)
    await state.set_state(AdminReschedule.select_date)

    today = date.today()
    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")

    try:
        await cb.message.edit_text(
            f"⏰ <b>Перенос записи #{apt_id}</b>\n\n"
            f"👤 {apt['client_name']} — {apt['service_name']}\n"
            f"Текущее время: {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n\n"
            f"📅 <b>Выберите новую дату:</b>",
            reply_markup=reschedule_calendar_kb(today.year, today.month, apt_id),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        # Если сообщение из канала — отправляем в личку
        await cb.bot.send_message(
            cb.from_user.id,
            f"⏰ <b>Перенос записи #{apt_id}</b>\n\n"
            f"👤 {apt['client_name']} — {apt['service_name']}\n"
            f"Текущее время: {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n\n"
            f"📅 <b>Выберите новую дату:</b>",
            reply_markup=reschedule_calendar_kb(today.year, today.month, apt_id),
            parse_mode=ParseMode.HTML,
        )
    await cb.answer()


# ── Перенос: навигация по месяцам ────────────────────────────────────────────

@router.callback_query(F.data.startswith("rescal_nav_"))
async def cb_rescal_nav(cb: CallbackQuery, state: FSMContext):
    # rescal_nav_{apt_id}_{year}_{month}
    parts  = cb.data.split("_")
    apt_id = int(parts[2])
    year   = int(parts[3])
    month  = int(parts[4])

    apt      = db.get_appointment(apt_id)
    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")

    await cb.message.edit_text(
        f"⏰ <b>Перенос записи #{apt_id}</b>\n\n"
        f"👤 {apt['client_name']} — {apt['service_name']}\n"
        f"Текущее время: {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n\n"
        f"📅 <b>Выберите новую дату:</b>",
        reply_markup=reschedule_calendar_kb(year, month, apt_id),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.callback_query(F.data == "rescal_noop")
async def cb_rescal_noop(cb: CallbackQuery):
    await cb.answer()


# ── Перенос: мастер выбрал дату → показываем слоты ───────────────────────────

@router.callback_query(F.data.startswith("rescal_date_"))
async def cb_rescal_date(cb: CallbackQuery, state: FSMContext):
    # rescal_date_{apt_id}_{date_str}
    parts    = cb.data.split("_")
    apt_id   = int(parts[2])
    date_str = parts[3]

    await state.update_data(reschedule_apt_id=apt_id, reschedule_date=date_str)
    await state.set_state(AdminReschedule.select_time)

    apt       = db.get_appointment(apt_id)
    master_id = apt["master_id"]
    booked    = db.get_booked_slots(master_id, date_str)
    available = get_available_slots(date_str, apt["duration"] if "duration" in apt else 60, booked)

    # Получаем длительность услуги
    service = db.get_service(apt["service_id"])
    duration = service["duration"] if service else 60
    available = get_available_slots(date_str, duration, booked)

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    if not available:
        await cb.answer("😔 На эту дату нет свободных слотов", show_alert=True)
        return

    await cb.message.edit_text(
        f"⏰ <b>Перенос записи #{apt_id}</b>\n\n"
        f"📅 Дата: <b>{date_obj.strftime('%d.%m.%Y')}</b>\n\n"
        f"🕐 <b>Выберите время:</b>",
        reply_markup=reschedule_times_kb(available, apt_id, date_str),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ── Перенос: мастер выбрал время → отправляем предложение клиенту ────────────

@router.callback_query(AdminReschedule.select_time, F.data.startswith("rescal_time_"))
async def cb_rescal_time(cb: CallbackQuery, state: FSMContext, bot: Bot):
    # rescal_time_{apt_id}_{date_str}_{time_str}
    parts    = cb.data.split("_")
    apt_id   = int(parts[2])
    date_str = parts[3]
    time_str = parts[4]

    apt = db.get_appointment(apt_id)
    if not apt:
        await cb.answer("Запись не найдена", show_alert=True)
        return

    new_dt   = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    old_date = datetime.strptime(apt["date"], "%Y-%m-%d")

    # Подтверждение мастеру
    await cb.message.edit_text(
        f"⏰ <b>Предложение отправлено клиенту!</b>\n\n"
        f"👤 {apt['client_name']} — {apt['service_name']}\n"
        f"Было: {old_date.strftime('%d.%m.%Y')} в {apt['time']}\n"
        f"Предложено: <b>{new_dt.strftime('%d.%m.%Y')} в {time_str}</b>\n\n"
        f"<i>Ожидаем ответа клиента...</i>",
        parse_mode=ParseMode.HTML,
    )

    await state.clear()

    # Уведомляем клиента
    await notify_client_reschedule_offer(bot, apt, date_str, time_str)
    await cb.answer("✅ Предложение отправлено клиенту")


# ── Клиент принимает перенос ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("reschedule_accept_"))
async def cb_reschedule_accept(cb: CallbackQuery, bot: Bot, scheduler):
    parts    = cb.data.split("_")
    apt_id   = int(parts[2])
    new_date = parts[3]
    new_time = parts[4]

    apt = db.get_appointment(apt_id)
    if not apt:
        await cb.answer("Запись не найдена", show_alert=True)
        return

    db.reschedule_appointment(apt_id, new_date, new_time)
    db.confirm_appointment(apt_id)
    apt = db.get_appointment(apt_id)

    for job_id in [f"reminder_24h_{apt_id}", f"reminder_2h_{apt_id}"]:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    apt_dt = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
    for hours, label in [(24, "24h"), (2, "2h")]:
        run_at = apt_dt - timedelta(hours=hours)
        if run_at > datetime.now():
            scheduler.add_job(
                send_reminder, "date", run_date=run_at,
                args=[bot, apt["client_telegram_id"], apt_id, label],
                id=f"reminder_{label}_{apt_id}", replace_existing=True,
            )

    new_dt = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
    await cb.message.edit_text(
        f"✅ <b>Перенос подтверждён!</b>\n\n"
        f"💅 {apt['service_name']}\n"
        f"📅 {new_dt.strftime('%d.%m.%Y')} в {new_time}\n\n"
        f"Ждём вас! 💅🌸",
        parse_mode=ParseMode.HTML,
    )

    # Уведомляем мастера
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                f"✅ Клиент <b>{apt['client_name']}</b> принял перенос записи #{apt_id}.\n"
                f"Новое время: <b>{new_dt.strftime('%d.%m.%Y')} в {new_time}</b>",
                parse_mode=ParseMode.HTML,
            )
    except Exception:
        pass

    await cb.answer("✅ Принято!")


# ── Клиент предлагает своё время ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("reschedule_counter_"))
async def cb_reschedule_counter(cb: CallbackQuery, state: FSMContext):
    apt_id = int(cb.data.split("_")[2])
    from states import ClientCounter
    await state.set_state(ClientCounter.enter_datetime)
    await state.update_data(counter_apt_id=apt_id)

    await cb.message.edit_text(
        f"✍️ <b>Введите удобную вам дату и время:</b>\n\n"
        f"Формат: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        f"Например: <code>25.04.2026 14:00</code>",
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.message(F.text)
async def msg_client_counter(message: Message, state: FSMContext, bot: Bot):
    from states import ClientCounter
    current = await state.get_state()
    if current != ClientCounter.enter_datetime:
        return

    data   = await state.get_data()
    apt_id = data.get("counter_apt_id")
    text   = message.text.strip()

    try:
        new_dt   = datetime.strptime(text, "%d.%m.%Y %H:%M")
        new_date = new_dt.strftime("%Y-%m-%d")
        new_time = new_dt.strftime("%H:%M")
    except ValueError:
        await message.answer(
            "❗ Неверный формат. Введите дату и время так:\n"
            "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\nНапример: <code>25.04.2026 14:00</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    apt = db.get_appointment(apt_id)
    await state.clear()

    await message.answer(
        f"✅ Ваше пожелание отправлено мастеру!\n\n"
        f"Предложенное время: <b>{new_dt.strftime('%d.%m.%Y')} в {new_time}</b>\n\n"
        f"Ожидайте подтверждения.",
        parse_mode=ParseMode.HTML,
    )

    # Отправляем мастеру встречное предложение клиента
    if apt:
        try:
            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    admin_id,
                    f"✍️ <b>Клиент предложил своё время!</b>\n\n"
                    f"👤 {apt['client_name']} ({apt['client_phone']})\n"
                    f"💅 {apt['service_name']}\n"
                    f"Предложенное время: <b>{new_dt.strftime('%d.%m.%Y')} в {new_time}</b>\n\n"
                    f"Подтвердите или измените запись.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Подтвердить",  callback_data=f"counter_confirm_{apt_id}_{new_date}_{new_time}"),
                            InlineKeyboardButton(text="⏰ Другое время", callback_data=f"apt_reschedule_{apt_id}"),
                        ],
                        [
                            InlineKeyboardButton(text="❌ Отменить",     callback_data=f"apt_cancel_{apt_id}"),
                        ],
                    ]),
                    parse_mode=ParseMode.HTML,
                )
        except Exception:
            pass


# ── Мастер подтверждает время клиента ─────────────────────────────────────────

@router.callback_query(F.data.startswith("counter_confirm_"))
async def cb_counter_confirm(cb: CallbackQuery, bot: Bot, scheduler):
    parts    = cb.data.split("_")
    apt_id   = int(parts[2])
    new_date = parts[3]
    new_time = parts[4]

    db.reschedule_appointment(apt_id, new_date, new_time)
    db.confirm_appointment(apt_id)
    apt = db.get_appointment(apt_id)

    for job_id in [f"reminder_24h_{apt_id}", f"reminder_2h_{apt_id}"]:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    apt_dt = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
    for hours, label in [(24, "24h"), (2, "2h")]:
        run_at = apt_dt - timedelta(hours=hours)
        if run_at > datetime.now():
            scheduler.add_job(
                send_reminder, "date", run_date=run_at,
                args=[bot, apt["client_telegram_id"], apt_id, label],
                id=f"reminder_{label}_{apt_id}", replace_existing=True,
            )

    new_dt = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")

    try:
        await cb.message.edit_text(
            f"✅ <b>Время клиента подтверждено #{apt_id}</b>\n\n"
            f"👤 {apt['client_name']}\n"
            f"💅 {apt['service_name']}\n"
            f"📅 {new_dt.strftime('%d.%m.%Y')} в {new_time}",
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass

    await notify_client_confirmed(bot, apt)
    await cb.answer("✅ Подтверждено, клиент уведомлён")
