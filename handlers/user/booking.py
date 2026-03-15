"""
handlers/user/booking.py — полный сценарий записи клиента (один мастер)

Шаги: услуга → календарь → время → имя → телефон → пожелания → подтверждение
"""

from datetime import date, datetime

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from keyboards.inline import (
    back_kb, calendar_kb, confirm_booking_kb, after_booking_kb,
    notes_kb, services_kb, times_kb,
)
from keyboards.reply import phone_request_kb, remove_kb
from services.calculator import calc_end_time
from services.notifications import notify_channel_new
from services.schedule import get_available_dates_in_month, get_available_slots
from states import Booking
from storage.database import db

router = Router()

DAY_NAMES_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def _get_sole_master() -> dict:
    masters = db.get_all_masters()
    return masters[0] if masters else {"id": 1, "name": "Мастер"}


# ── Вспомогательная функция: показать календарь ───────────────────────────────

async def _show_calendar(target, state: FSMContext, year: int, month: int, edit: bool = True):
    await state.set_state(Booking.select_date)
    data      = await state.get_data()
    available = get_available_dates_in_month(year, month, data["master_id"], data["service_duration"])

    text = (
        f"✅ Услуга: <b>{data['service_name']}</b>\n"
        f"⏱ Длительность: {data['service_duration']} мин.\n"
        f"💰 Стоимость: {data['service_price']}₽\n\n"
        f"📅 <b>Выберите дату:</b>\n"
        f"<i>Цифра — свободно   ✗ — занято   · — недоступно</i>"
    )
    kb = calendar_kb(year, month, available, data["service_id"])

    if edit and isinstance(target, Message):
        await target.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await target.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ── 1. Выбор услуги ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "book")
async def cb_book(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Booking.select_service)
    services = db.get_services()
    await cb.message.edit_text(
        "💅 <b>Выберите услугу:</b>\n\nМаникюр, педикюр, наращивание и уход за ногтями ✨",
        reply_markup=services_kb(services),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.callback_query(Booking.select_service, F.data.startswith("service_"))
async def cb_select_service(cb: CallbackQuery, state: FSMContext):
    service_id = int(cb.data.split("_")[1])
    service    = db.get_service(service_id)
    master     = _get_sole_master()

    await state.update_data(
        service_id=service_id,
        service_name=service["name"],
        service_duration=service["duration"],
        service_price=service["price"],
        master_id=master["id"],
        master_name=master["name"],
    )

    today = date.today()
    await _show_calendar(cb.message, state, today.year, today.month, edit=True)
    await cb.answer()


# ── 2. Навигация по месяцам ───────────────────────────────────────────────────

@router.callback_query(Booking.select_date, F.data.startswith("cal_nav_"))
async def cb_cal_nav(cb: CallbackQuery, state: FSMContext):
    _, _, y, m = cb.data.split("_")
    year, month = int(y), int(m)

    today = date.today()
    # Защита от ухода в прошлое
    if (year, month) < (today.year, today.month):
        await cb.answer("Нельзя выбрать прошедший месяц", show_alert=False)
        return

    await _show_calendar(cb.message, state, year, month, edit=True)
    await cb.answer()


@router.callback_query(Booking.select_date, F.data == "cal_noop")
async def cb_cal_noop(cb: CallbackQuery):
    await cb.answer()


# ── 3. Выбор даты ─────────────────────────────────────────────────────────────

@router.callback_query(Booking.select_date, F.data.startswith("date_"))
async def cb_select_date(cb: CallbackQuery, state: FSMContext):
    date_str = cb.data.split("_")[1]
    await state.update_data(date=date_str)
    await state.set_state(Booking.select_time)
    data = await state.get_data()

    booked    = db.get_booked_slots(data["master_id"], date_str)
    available = get_available_slots(date_str, data["service_duration"], booked)

    if not available:
        await cb.answer("😔 На этот день все слоты уже заняты", show_alert=True)
        await state.set_state(Booking.select_date)
        return

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    await cb.message.edit_text(
        f"✅ Услуга: <b>{data['service_name']}</b>\n"
        f"📅 Дата: <b>{DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')}</b>\n\n"
        f"🕐 <b>Выберите время:</b>",
        reply_markup=times_kb(available, back_cb=f"service_{data['service_id']}"),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ── 4. Выбор времени ──────────────────────────────────────────────────────────

@router.callback_query(Booking.select_time, F.data.startswith("time_"))
async def cb_select_time(cb: CallbackQuery, state: FSMContext):
    time_str = cb.data.split("_")[1]
    await state.update_data(time=time_str)

    user_info = db.get_user_info(cb.from_user.id)
    if user_info and user_info.get("phone"):
        await state.update_data(client_name=user_info["name"], client_phone=user_info["phone"])
        await _ask_notes(cb.message, state, edit=True)
    else:
        await state.set_state(Booking.enter_name)
        await cb.message.edit_text(
            "📝 <b>Введите ваше имя:</b>\n\nКак к вам обращаться?",
            reply_markup=back_kb("book"),
            parse_mode=ParseMode.HTML,
        )
    await cb.answer()


# ── 5. Имя ────────────────────────────────────────────────────────────────────

@router.message(Booking.enter_name, F.text)
async def msg_enter_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("❗ Пожалуйста, введите корректное имя (минимум 2 символа).")
        return
    await state.update_data(client_name=name)
    await state.set_state(Booking.enter_phone)
    await message.answer(
        "📱 <b>Укажите номер телефона:</b>\n\n"
        "Нажмите кнопку или введите вручную (например: +79001234567)",
        reply_markup=phone_request_kb(),
        parse_mode=ParseMode.HTML,
    )


# ── 6. Телефон ────────────────────────────────────────────────────────────────

@router.message(Booking.enter_phone, F.contact | F.text)
async def msg_enter_phone(message: Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    else:
        phone = message.text.strip()
        if len("".join(filter(str.isdigit, phone))) < 10:
            await message.answer(
                "❗ Пожалуйста, введите корректный номер телефона.",
                reply_markup=remove_kb(),
            )
            return

    data = await state.get_data()
    name = data.get("client_name", message.from_user.first_name)
    db.update_user_contact(message.from_user.id, name, phone)
    await state.update_data(client_phone=phone)
    await message.answer("✅", reply_markup=remove_kb())
    await _ask_notes(message, state, edit=False)


# ── 7. Пожелания ─────────────────────────────────────────────────────────────

async def _ask_notes(target, state: FSMContext, edit: bool = False):
    await state.set_state(Booking.enter_notes)
    text = (
        "💬 <b>Дополнительная информация</b>\n\n"
        "Есть ли особые пожелания?\n"
        "<i>Например: форма ногтей, длина, желаемый дизайн, "
        "аллергия на материалы, особенности ногтевой пластины и т.д.</i>"
    )
    if edit and isinstance(target, Message):
        await target.edit_text(text, reply_markup=notes_kb(), parse_mode=ParseMode.HTML)
    else:
        await target.answer(text, reply_markup=notes_kb(), parse_mode=ParseMode.HTML)


@router.message(Booking.enter_notes, F.text)
async def msg_enter_notes(message: Message, state: FSMContext):
    await state.update_data(notes=message.text.strip()[:500])
    data      = await state.get_data()
    user_info = {"name": data["client_name"], "phone": data["client_phone"]}
    await _show_confirmation(message, state, user_info, edit=False)


@router.callback_query(Booking.enter_notes, F.data == "notes_skip")
async def cb_notes_skip(cb: CallbackQuery, state: FSMContext):
    await state.update_data(notes="")
    data      = await state.get_data()
    user_info = {"name": data["client_name"], "phone": data["client_phone"]}
    await _show_confirmation(cb.message, state, user_info, edit=True)
    await cb.answer()


# ── 8. Подтверждение ─────────────────────────────────────────────────────────

async def _show_confirmation(target, state: FSMContext, user_info: dict, edit: bool = False):
    data     = await state.get_data()
    date_obj = datetime.strptime(data["date"], "%Y-%m-%d")
    end_time = calc_end_time(data["date"], data["time"], data["service_duration"])

    notes_line = f"💬 Пожелания: <i>{data['notes']}</i>\n" if data.get("notes") else ""
    text = (
        f"📋 <b>Подтверждение записи</b>\n\n"
        f"👤 Клиент: <b>{user_info['name']}</b>\n"
        f"📱 Телефон: <b>{user_info['phone']}</b>\n\n"
        f"💅 Услуга: <b>{data['service_name']}</b>\n"
        f"📅 Дата: <b>{DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')}</b>\n"
        f"🕐 Время: <b>{data['time']} – {end_time}</b>\n"
        f"💰 Стоимость: <b>{data['service_price']}₽</b>\n"
        f"{notes_line}"
        f"\n✅ Подтвердить запись?"
    )
    await state.set_state(Booking.confirm)
    if edit and isinstance(target, Message):
        await target.edit_text(text, reply_markup=confirm_booking_kb(), parse_mode=ParseMode.HTML)
    else:
        await target.answer(text, reply_markup=confirm_booking_kb(), parse_mode=ParseMode.HTML)


# ── 9. Запись создана ────────────────────────────────────────────────────────

@router.callback_query(Booking.confirm, F.data == "confirm_booking")
async def cb_confirm_booking(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data      = await state.get_data()
    user_id   = cb.from_user.id
    user_info = db.get_user_info(user_id)

    apt_id = db.create_appointment(
        user_id=user_id,
        service_id=data["service_id"],
        master_id=data["master_id"],
        date=data["date"],
        time=data["time"],
        client_name=user_info["name"],
        client_phone=user_info["phone"],
        notes=data.get("notes", ""),
    )

    date_obj = datetime.strptime(data["date"], "%Y-%m-%d")
    await cb.message.edit_text(
        f"📋 <b>Заявка принята!</b>\n\n"
        f"💅 Услуга: <b>{data['service_name']}</b>\n"
        f"📅 <b>{DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')} в {data['time']}</b>\n\n"
        f"⏳ <i>Ожидайте подтверждения — я свяжусь с вами в течение 1 часа.</i>\n\n"
        f"Как только подтвержу запись, вы получите уведомление. 💅",
        reply_markup=after_booking_kb(),
        parse_mode=ParseMode.HTML,
    )

    await notify_channel_new(bot, apt_id, user_id, data, user_info)
    await state.clear()
    await cb.answer()
