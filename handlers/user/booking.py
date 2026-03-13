"""
handlers/user/booking.py — полный сценарий записи клиента (один мастер)

Шаги: услуга → дата → время → имя (если новый) → телефон (если новый) → пожелания → подтверждение
Шаг выбора мастера исключён — мастер всегда единственный.
"""

from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from keyboards.inline import (
    back_kb, confirm_booking_kb, after_booking_kb,
    dates_kb, notes_kb, services_kb, times_kb,
)
from keyboards.reply import phone_request_kb, remove_kb
from services.calculator import calc_end_time
from services.notifications import notify_channel_new, send_reminder
from services.schedule import get_available_slots, get_next_working_days
from states import Booking
from storage.database import db

router = Router()

DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
DAY_NAMES_FULL  = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]


def _get_sole_master() -> dict:
    """Возвращает единственного мастера из БД"""
    masters = db.get_all_masters()
    return masters[0] if masters else {"id": 1, "name": "Мастер"}


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

    # Автоматически берём единственного мастера
    master = _get_sole_master()

    await state.update_data(
        service_id=service_id,
        service_name=service["name"],
        service_duration=service["duration"],
        service_price=service["price"],
        master_id=master["id"],
        master_name=master["name"],
    )
    await state.set_state(Booking.select_date)

    dates = get_next_working_days(7)
    await cb.message.edit_text(
        f"✅ Услуга: <b>{service['name']}</b>\n"
        f"⏱ Длительность: {service['duration']} мин.\n"
        f"💰 Стоимость: {service['price']}₽\n\n"
        f"📅 <b>Выберите дату:</b>",
        reply_markup=dates_kb(dates, back_cb="book"),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ── 2. Выбор даты ─────────────────────────────────────────────────────────────

@router.callback_query(Booking.select_date, F.data.startswith("date_"))
async def cb_select_date(cb: CallbackQuery, state: FSMContext):
    date_str = cb.data.split("_")[1]
    await state.update_data(date=date_str)
    await state.set_state(Booking.select_time)
    data = await state.get_data()

    booked    = db.get_booked_slots(data["master_id"], date_str)
    available = get_available_slots(date_str, data["service_duration"], booked)

    if not available:
        await cb.message.edit_text(
            "😔 К сожалению, на выбранную дату все слоты заняты.\nПожалуйста, выберите другую дату.",
            reply_markup=back_kb(f"service_{data['service_id']}"),
        )
        await cb.answer()
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


# ── 3. Выбор времени ──────────────────────────────────────────────────────────

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


# ── 4. Имя ────────────────────────────────────────────────────────────────────

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


# ── 5. Телефон ────────────────────────────────────────────────────────────────

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


# ── 6. Пожелания / комментарий ───────────────────────────────────────────────

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


# ── 7. Подтверждение ─────────────────────────────────────────────────────────

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


# ── 8. Запись создана ────────────────────────────────────────────────────────

@router.callback_query(Booking.confirm, F.data == "confirm_booking")
async def cb_confirm_booking(cb: CallbackQuery, state: FSMContext, bot: Bot, scheduler: AsyncIOScheduler):
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

    # Планируем напоминания
    from datetime import timedelta
    apt_dt = datetime.strptime(f"{data['date']} {data['time']}", "%Y-%m-%d %H:%M")
    for hours, label in [(24, "24h"), (2, "2h")]:
        run_at = apt_dt - timedelta(hours=hours)
        if run_at > datetime.now():
            scheduler.add_job(
                send_reminder, "date", run_date=run_at,
                args=[bot, user_id, apt_id, label],
                id=f"reminder_{label}_{apt_id}", replace_existing=True,
            )

    date_obj = datetime.strptime(data["date"], "%Y-%m-%d")
    await cb.message.edit_text(
        f"🎉 <b>Запись успешно создана!</b>\n\n"
        f"💅 Услуга: <b>{data['service_name']}</b>\n"
        f"📅 <b>{DAY_NAMES_FULL[date_obj.weekday()]}, {date_obj.strftime('%d.%m.%Y')} в {data['time']}</b>\n\n"
        f"🔔 Я пришлю напоминание за 24 часа и за 2 часа до визита.\n"
        f"⏳ <i>Свяжусь с вами для подтверждения в течение 1 часа.</i>\n\n"
        f"Жду вас! 💅🌸",
        reply_markup=after_booking_kb(),
        parse_mode=ParseMode.HTML,
    )

    await notify_channel_new(bot, apt_id, user_id, data, user_info)
    await state.clear()
    await cb.answer()
