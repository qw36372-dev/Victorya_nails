"""
handlers/admin/panel.py — панель администратора + подтверждение/отмена/перенос записей
"""

from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from keyboards.inline import admin_menu_kb, back_kb
from services.notifications import (
    notify_client_confirmed,
    notify_client_cancelled_by_master,
    notify_client_reschedule_offer,
    send_reminder,
)
from states import Admin, AdminReschedule
from storage.database import db

router = Router()

# Временное хранилище: {admin_tg_id: apt_id} — для флоу переноса записи
_reschedule_pending: dict[int, int] = {}


# ── Главное меню админа ───────────────────────────────────────────────────────

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
            status_icon = "✅" if apt["status"] == "active" else "⏳"
            text += (
                f"{status_icon} <b>{apt['time']}</b> — {apt['service_name']}\n"
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


# ── Подтверждение записи мастером ─────────────────────────────────────────────

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
    apt = db.get_appointment(apt_id)   # обновлённые данные

    # Планируем напоминания
    apt_dt = datetime.strptime(f"{apt['date']} {apt['time']}", "%Y-%m-%d %H:%M")
    for hours, label in [(24, "24h"), (2, "2h")]:
        run_at = apt_dt - timedelta(hours=hours)
        if run_at > datetime.now():
            scheduler.add_job(
                send_reminder, "date", run_date=run_at,
                args=[bot, apt["client_telegram_id"], apt_id, label],
                id=f"reminder_{label}_{apt_id}", replace_existing=True,
            )

    # Редактируем сообщение в канале
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

    # Уведомляем клиента
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

    # Удаляем напоминания если были
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


# ── Предложить другое время ───────────────────────────────────────────────────

@router.callback_query(F.data.startswith("apt_reschedule_"))
async def cb_apt_reschedule(cb: CallbackQuery, bot: Bot, state: FSMContext):
    apt_id    = int(cb.data.split("_")[2])
    apt       = db.get_appointment(apt_id)
    admin_id  = cb.from_user.id

    if not apt:
        await cb.answer("Запись не найдена", show_alert=True)
        return
    if apt["status"] == "cancelled":
        await cb.answer("Запись уже отменена", show_alert=True)
        return

    # Сохраняем в памяти: какую запись переносим
    _reschedule_pending[admin_id] = apt_id

    # Отправляем мастеру личное сообщение с инструкцией
    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
    try:
        await bot.send_message(
            admin_id,
            f"⏰ <b>Перенос записи #{apt_id}</b>\n\n"
            f"👤 {apt['client_name']}\n"
            f"💅 {apt['service_name']}\n"
            f"Текущее время: {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n\n"
            f"Введите новую дату и время в формате:\n"
            f"<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
            f"Например: <code>25.04.2026 14:00</code>",
            parse_mode=ParseMode.HTML,
        )
        await cb.answer("Отправил вам сообщение в личку 👆")
    except Exception as e:
        await cb.answer(f"Не могу написать в личку. Убедитесь, что запустили бота.", show_alert=True)
        return

    # Устанавливаем состояние ожидания нового времени
    await state.set_state(AdminReschedule.enter_datetime)


# ── Обработка ввода нового времени от мастера ─────────────────────────────────

@router.message(AdminReschedule.enter_datetime, F.text)
async def msg_reschedule_datetime(message: Message, state: FSMContext, bot: Bot):
    admin_id = message.from_user.id

    if admin_id not in _reschedule_pending:
        await message.answer("❗ Нет активного переноса. Нажмите кнопку в канале ещё раз.")
        await state.clear()
        return

    apt_id = _reschedule_pending[admin_id]
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
    if not apt:
        await message.answer("❗ Запись не найдена.")
        del _reschedule_pending[admin_id]
        await state.clear()
        return

    # Отправляем клиенту предложение
    await notify_client_reschedule_offer(bot, apt, new_date, new_time)

    del _reschedule_pending[admin_id]
    await state.clear()

    new_dt_fmt = new_dt.strftime("%d.%m.%Y в %H:%M")
    await message.answer(
        f"✅ Предложение отправлено клиенту {apt['client_name']}.\n"
        f"Предложенное время: <b>{new_dt_fmt}</b>\n\n"
        f"Ожидаем ответа клиента.",
        parse_mode=ParseMode.HTML,
    )


# ── Клиент принимает перенос ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("reschedule_accept_"))
async def cb_reschedule_accept(cb: CallbackQuery, bot: Bot, scheduler):
    parts    = cb.data.split("_")
    # reschedule_accept_{apt_id}_{date}_{time}
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

    # Перепланируем напоминания
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

    new_dt   = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
    await cb.message.edit_text(
        f"✅ <b>Перенос подтверждён!</b>\n\n"
        f"💅 {apt['service_name']}\n"
        f"📅 {new_dt.strftime('%d.%m.%Y')} в {new_time}\n\n"
        f"Ждём вас! 💅🌸",
        parse_mode=ParseMode.HTML,
    )
    await cb.answer("✅ Принято!")


# ── Клиент отклоняет перенос ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("reschedule_decline_"))
async def cb_reschedule_decline(cb: CallbackQuery, bot: Bot):
    apt_id = int(cb.data.split("_")[2])
    apt    = db.get_appointment(apt_id)

    db.cancel_appointment(apt_id)

    await cb.message.edit_text(
        "❌ Вы отклонили предложение о переносе.\n\n"
        "Запись отменена. Если хотите записаться — выберите удобное время.",
        reply_markup=None,
    )

    # Уведомляем мастера
    if apt:
        try:
            for admin_id in __import__("config").ADMIN_IDS:
                await bot.send_message(
                    admin_id,
                    f"❌ Клиент <b>{apt['client_name']}</b> отклонил предложение о переносе записи #{apt_id}.",
                    parse_mode=ParseMode.HTML,
                )
        except Exception:
            pass

    await cb.answer("Отклонено")
