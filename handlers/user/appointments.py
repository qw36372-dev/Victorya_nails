"""
handlers/user/appointments.py — просмотр и отмена записей
"""

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from keyboards.inline import appointments_kb, confirm_cancel_kb
from services.notifications import notify_channel_cancel
from states import MyAppointments
from storage.database import db

router = Router()

DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


async def _delete_prev(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "my_appointments")
async def cb_my_appointments(cb: CallbackQuery, state: FSMContext, bot: Bot):
    await state.set_state(MyAppointments.view)
    appointments = db.get_user_appointments(cb.from_user.id)

    if not appointments:
        msg = await cb.message.answer(
            "📋 У вас пока нет активных записей.\n\nЗапишитесь к нашим мастерам! 💅",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💅 Записаться",  callback_data="book")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
            ]),
        )
    else:
        text = "📋 <b>Ваши записи:</b>\n\n"
        for apt in appointments:
            date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
            status   = "⏳ Ожидает подтверждения" if apt["status"] == "pending" else "✅ Подтверждена"
            text += (
                f"📌 <b>{apt['service_name']}</b>\n"
                f"   📅 {DAY_NAMES_SHORT[date_obj.weekday()]} {date_obj.strftime('%d.%m.%Y')} в {apt['time']}\n"
                f"   💰 {apt['price']}₽\n"
                f"   {status}\n\n"
            )
        msg = await cb.message.answer(
            text,
            reply_markup=appointments_kb(appointments),
            parse_mode=ParseMode.HTML,
        )

    await _delete_prev(bot, cb.message.chat.id, cb.message.message_id)
    await cb.answer()


@router.callback_query(MyAppointments.view, F.data.startswith("cancel_"))
async def cb_cancel_appointment(cb: CallbackQuery, state: FSMContext, bot: Bot):
    apt_id = int(cb.data.split("_")[1])
    apt    = db.get_appointment(apt_id)
    if not apt:
        await cb.answer("Запись не найдена", show_alert=True)
        return

    await state.update_data(cancel_apt_id=apt_id)
    await state.set_state(MyAppointments.confirm_cancel)
    date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")

    msg = await cb.message.answer(
        f"❓ Вы уверены, что хотите отменить запись?\n\n"
        f"💅 {apt['service_name']}\n"
        f"📅 {date_obj.strftime('%d.%m.%Y')} в {apt['time']}",
        reply_markup=confirm_cancel_kb(apt_id),
        parse_mode=ParseMode.HTML,
    )
    await _delete_prev(bot, cb.message.chat.id, cb.message.message_id)
    await cb.answer()


@router.callback_query(MyAppointments.confirm_cancel, F.data == "confirm_cancel")
async def cb_confirm_cancel(cb: CallbackQuery, state: FSMContext, bot: Bot, scheduler):
    data   = await state.get_data()
    apt_id = data["cancel_apt_id"]
    apt    = db.get_appointment(apt_id)
    db.cancel_appointment(apt_id)

    for job_id in [f"reminder_24h_{apt_id}", f"reminder_2h_{apt_id}"]:
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass

    msg = await cb.message.answer(
        "✅ Запись отменена.\n\nЕсли захотите снова записаться — я всегда здесь! 💅",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💅 Записаться снова", callback_data="book")],
            [InlineKeyboardButton(text="🏠 Главное меню",      callback_data="main_menu")],
        ]),
    )
    await _delete_prev(bot, cb.message.chat.id, cb.message.message_id)
    await notify_channel_cancel(bot, apt)
    await state.clear()
    await cb.answer()
