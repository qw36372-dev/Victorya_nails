"""
handlers/admin/panel.py — панель администратора, записи, статистика
"""

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import ADMIN_IDS
from keyboards.inline import admin_menu_kb, back_kb
from states import Admin
from storage.database import db

router = Router()


@router.callback_query(F.data == "admin")
async def cb_admin(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in ADMIN_IDS:
        await cb.answer("⛔ Доступ запрещён", show_alert=True)
        return
    await state.set_state(Admin.menu)

    today     = datetime.now().strftime("%Y-%m-%d")
    today_apt = db.get_appointments_by_date(today)

    await cb.message.edit_text(
        f"⚙️ <b>Панель администратора</b>\n\n"
        f"👥 Всего клиентов: <b>{db.get_total_users()}</b>\n"
        f"📅 Записей сегодня: <b>{len(today_apt)}</b>",
        reply_markup=admin_menu_kb(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


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
            text += (
                f"🕐 <b>{apt['time']}</b> — {apt['service_name']}\n"
                f"   👤 {apt['client_name']} ({apt['client_phone']})\n"
                f"   👩 {apt['master_name']}\n\n"
            )

    await cb.message.edit_text(text, reply_markup=back_kb("admin"), parse_mode=ParseMode.HTML)
    await cb.answer()


@router.callback_query(Admin.menu, F.data == "admin_stats")
async def cb_admin_stats(cb: CallbackQuery):
    stats = db.get_stats()
    await cb.message.edit_text(
        f"📊 <b>Статистика салона</b>\n\n"
        f"👥 Всего клиентов: <b>{stats['total_users']}</b>\n"
        f"📅 Всего записей: <b>{stats['total_appointments']}</b>\n"
        f"✅ Активных: <b>{stats['active_appointments']}</b>\n"
        f"❌ Отменено: <b>{stats['cancelled_appointments']}</b>\n"
        f"💰 Выручка (ожид.): <b>{stats['expected_revenue']}₽</b>",
        reply_markup=back_kb("admin"),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()
