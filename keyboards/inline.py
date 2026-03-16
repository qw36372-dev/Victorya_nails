"""
keyboards/inline.py — все inline-клавиатуры бота
"""

import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMIN_IDS

DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


# ── Общие ────────────────────────────────────────────────────────────────────

def main_menu_kb(user_id: int, has_contact: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="💅 Записаться на услугу", callback_data="book")],
        [InlineKeyboardButton(text="📋 Мои записи",           callback_data="my_appointments")],
        [InlineKeyboardButton(text="💰 Прайс-лист",           callback_data="price_list")],
        [InlineKeyboardButton(text="📍 Контакты и адрес",     callback_data="contacts")],
    ]
    if has_contact:
        rows.append([InlineKeyboardButton(text="🗑 Удалить мои данные", callback_data="clear_my_data")])
    if user_id in ADMIN_IDS:
        rows.append([InlineKeyboardButton(text="⚙️ Панель администратора", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb(callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад", callback_data=callback)]
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])


# ── Запись: услуги ────────────────────────────────────────────────────────────

def services_kb(services: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"{s['emoji']} {s['name']} — {s['price']}₽",
            callback_data=f"service_{s['id']}",
        )]
        for s in services
    ]
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Запись: мастера ───────────────────────────────────────────────────────────

def masters_kb(masters: list, back_cb: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=f"👩 {m['name']} — {m['specialization']}",
            callback_data=f"master_{m['id']}",
        )]
        for m in masters
    ]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Запись: календарь ─────────────────────────────────────────────────────────

def calendar_kb(year: int, month: int, available_dates: set, service_id: int) -> InlineKeyboardMarkup:
    """
    Полноценный календарь на месяц с навигацией.
    ✅ — есть свободные слоты  ✗ — все занято  · — прошедший/выходной
    """
    today = date.today()
    rows  = []

    # ── Навигация: < Март 2026 > ─────────────────────────────────────────────
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    # Максимум — 12 месяцев вперёд от сегодня
    max_m     = today.month + 12
    max_year  = today.year + (max_m - 1) // 12
    max_month = (max_m - 1) % 12 + 1

    # ◀️ — можно, если предыдущий месяц не раньше текущего
    can_prev = (prev_y, prev_m) >= (today.year, today.month)
    # ▶️ — можно, если следующий месяц не позже максимума
    can_next = (next_y, next_m) <= (max_year, max_month)

    rows.append([
        InlineKeyboardButton(
            text="◀️" if can_prev else " ",
            callback_data=f"cal_nav_{prev_y}_{prev_m}" if can_prev else "cal_noop",
        ),
        InlineKeyboardButton(
            text=f"{MONTH_NAMES[month]} {year}",
            callback_data="cal_noop",
        ),
        InlineKeyboardButton(
            text="▶️" if can_next else " ",
            callback_data=f"cal_nav_{next_y}_{next_m}" if can_next else "cal_noop",
        ),
    ])

    # ── Заголовки дней ────────────────────────────────────────────────────────
    rows.append([
        InlineKeyboardButton(text=d, callback_data="cal_noop")
        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    ])

    # ── Дни месяца ────────────────────────────────────────────────────────────
    for week in calendar.monthcalendar(year, month):
        row = []
        for weekday, day in enumerate(week):
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="cal_noop"))
                continue
            d        = date(year, month, day)
            date_str = d.strftime("%Y-%m-%d")
            if d <= today or weekday == 6:           # прошедшее или воскресенье
                row.append(InlineKeyboardButton(text="·", callback_data="cal_noop"))
            elif date_str in available_dates:        # есть свободные слоты
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"date_{date_str}"))
            else:                                    # всё занято
                row.append(InlineKeyboardButton(text="✗", callback_data="cal_noop"))
        rows.append(row)

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"service_{service_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Запись: время ─────────────────────────────────────────────────────────────

def times_kb(available: list, back_cb: str) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, slot in enumerate(available):
        row.append(InlineKeyboardButton(text=slot, callback_data=f"time_{slot}"))
        if len(row) == 4 or i == len(available) - 1:
            rows.append(row)
            row = []
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Запись: пожелания ────────────────────────────────────────────────────────

def notes_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Пропустить", callback_data="notes_skip")]
    ])


# ── Запись: подтверждение ────────────────────────────────────────────────────

def confirm_booking_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_booking")],
        [InlineKeyboardButton(text="❌ Отменить",    callback_data="main_menu")],
    ])


def after_booking_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои записи",  callback_data="my_appointments")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


# ── Мои записи ───────────────────────────────────────────────────────────────

def appointments_kb(appointments: list) -> InlineKeyboardMarkup:
    from datetime import datetime
    rows = []
    for apt in appointments:
        date_obj = datetime.strptime(apt["date"], "%Y-%m-%d")
        rows.append([InlineKeyboardButton(
            text=f"❌ Отменить {apt['service_name']} {date_obj.strftime('%d.%m')}",
            callback_data=f"cancel_{apt['id']}",
        )])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_cancel_kb(apt_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, отменить", callback_data="confirm_cancel")],
        [InlineKeyboardButton(text="🔙 Назад",         callback_data="my_appointments")],
    ])


# ── Прайс / контакты ─────────────────────────────────────────────────────────

def info_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💅 Записаться",  callback_data="book")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


# ── Канал: кнопки мастера ────────────────────────────────────────────────────

def channel_buttons_kb(tg_id: int, phone: str) -> InlineKeyboardMarkup:
    # Очищаем номер от всех нецифровых символов, кроме ведущего +
    digits   = "".join(filter(str.isdigit, phone))
    phone_clean = f"+{digits}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✉️ Написать клиенту", url=f"tg://user?id={tg_id}"),
        InlineKeyboardButton(text="📞 Позвонить",         url=f"tel:{phone_clean}"),
    ]])


# ── Админ панель ─────────────────────────────────────────────────────────────

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Записи сегодня",      callback_data="admin_today")],
        [InlineKeyboardButton(text="📅 Записи на завтра",    callback_data="admin_tomorrow")],
        [InlineKeyboardButton(text="🔒 Заблокировать время", callback_data="admin_block")],
        [InlineKeyboardButton(text="📊 Статистика",           callback_data="admin_stats")],
        [InlineKeyboardButton(text="🏠 Главное меню",         callback_data="main_menu")],
    ])


# ── Блокировка слотов ─────────────────────────────────────────────────────────

def block_masters_kb(masters: list) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"👩 {m['name']}", callback_data=f"block_master_{m['id']}")]
        for m in masters
    ]
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def block_dates_kb(dates: list, master_id: int) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, d in enumerate(dates):
        row.append(InlineKeyboardButton(
            text=f"{DAY_NAMES_SHORT[d.weekday()]} {d.strftime('%d.%m')}",
            callback_data=f"block_date_{d.strftime('%Y-%m-%d')}",
        ))
        if len(row) == 3 or i == len(dates) - 1:
            rows.append(row)
            row = []
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_block")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def block_slots_grid_kb(all_slots: list, booked: list, blocked_map: dict, master_id: int) -> InlineKeyboardMarkup:
    rows, row = [], []
    for i, slot in enumerate(all_slots):
        if slot in booked and slot not in blocked_map:
            label, cb_data = f"🔴 {slot}", f"block_noop_{slot}"
        elif slot in blocked_map:
            label, cb_data = f"🟡 {slot}", f"unblock_{blocked_map[slot]}"
        else:
            label, cb_data = f"🟢 {slot}", f"block_time_{slot}"
        row.append(InlineKeyboardButton(text=label, callback_data=cb_data))
        if len(row) == 4 or i == len(all_slots) - 1:
            rows.append(row)
            row = []
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"block_master_{master_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
