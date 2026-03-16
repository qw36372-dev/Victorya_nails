"""
handlers/admin/slots.py — блокировка и разблокировка слотов (один мастер)

Выбор даты через календарь с навигацией по месяцам.
"""

import calendar as cal_module
from datetime import date, datetime

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from services.schedule import get_all_slots
from states import Admin
from storage.database import db

router = Router()

MONTH_NAMES = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
DAY_NAMES_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def _get_sole_master() -> dict:
    masters = db.get_all_masters()
    return masters[0] if masters else {"id": 1, "name": "Мастер"}


def _admin_calendar_kb(year: int, month: int) -> InlineKeyboardMarkup:
    """Календарь для админа — все рабочие дни кликабельны (Пн–Сб), без проверки слотов."""
    today = date.today()
    rows  = []

    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1

    max_m     = today.month + 12
    max_year  = today.year + (max_m - 1) // 12
    max_month = (max_m - 1) % 12 + 1

    can_prev = (prev_y, prev_m) >= (today.year, today.month)
    can_next = (next_y, next_m) <= (max_year, max_month)

    # Навигация
    rows.append([
        InlineKeyboardButton(
            text="◀️" if can_prev else " ",
            callback_data=f"block_cal_nav_{prev_y}_{prev_m}" if can_prev else "block_cal_noop",
        ),
        InlineKeyboardButton(
            text=f"{MONTH_NAMES[month]} {year}",
            callback_data="block_cal_noop",
        ),
        InlineKeyboardButton(
            text="▶️" if can_next else " ",
            callback_data=f"block_cal_nav_{next_y}_{next_m}" if can_next else "block_cal_noop",
        ),
    ])

    # Заголовки дней
    rows.append([
        InlineKeyboardButton(text=d, callback_data="block_cal_noop")
        for d in DAY_NAMES_SHORT
    ])

    # Дни месяца
    for week in cal_module.monthcalendar(year, month):
        row = []
        for weekday, day in enumerate(week):
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="block_cal_noop"))
            elif weekday == 6:  # воскресенье
                row.append(InlineKeyboardButton(text="·", callback_data="block_cal_noop"))
            else:
                d        = date(year, month, day)
                date_str = d.strftime("%Y-%m-%d")
                row.append(InlineKeyboardButton(text=str(day), callback_data=f"block_date_{date_str}"))
        rows.append(row)

    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_admin_calendar(cb: CallbackQuery, year: int, month: int):
    await cb.message.edit_text(
        f"🔒 <b>Блокировка времени из журнала</b>\n\n"
        f"📅 Выберите дату:\n"
        f"<i>Цифра — рабочий день   · — воскресенье</i>",
        reply_markup=_admin_calendar_kb(year, month),
        parse_mode=ParseMode.HTML,
    )


# ── Открыть блокировку → показать календарь ───────────────────────────────────

@router.callback_query(Admin.menu, F.data == "admin_block")
async def cb_admin_block(cb: CallbackQuery, state: FSMContext):
    master = _get_sole_master()
    await state.update_data(block_master_id=master["id"], block_master_name=master["name"])
    await state.set_state(Admin.block_date)

    today = date.today()
    await _show_admin_calendar(cb, today.year, today.month)
    await cb.answer()


# ── Навигация по месяцам ──────────────────────────────────────────────────────

@router.callback_query(Admin.block_date, F.data.startswith("block_cal_nav_"))
async def cb_block_cal_nav(cb: CallbackQuery):
    _, _, _, y, m = cb.data.split("_")
    await _show_admin_calendar(cb, int(y), int(m))
    await cb.answer()


@router.callback_query(Admin.block_date, F.data == "block_cal_noop")
async def cb_block_cal_noop(cb: CallbackQuery):
    await cb.answer()


# ── Выбор даты → сетка слотов ────────────────────────────────────────────────

@router.callback_query(Admin.block_date, F.data.startswith("block_date_"))
async def cb_block_select_time(cb: CallbackQuery, state: FSMContext):
    date_str = cb.data.split("_")[2]
    await state.update_data(block_date=date_str)
    await state.set_state(Admin.block_time)
    await _render_slots_grid(cb, state, date_str)
    await cb.answer()


async def _render_slots_grid(cb: CallbackQuery, state: FSMContext, date_str: str):
    data      = await state.get_data()
    master_id = data["block_master_id"]

    all_slots = get_all_slots(date_str)
    booked    = db.get_booked_slots(master_id, date_str)

    def to_str(val):
        return val.strftime("%H:%M") if hasattr(val, "strftime") else str(val)[:5]

    blocked_list = db.get_blocked_slots_by_master_date(master_id, date_str)
    blocked_map  = {to_str(b["time"]): b["id"] for b in blocked_list}

    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

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

    # Кнопка назад возвращает в календарь текущего месяца
    d = datetime.strptime(date_str, "%Y-%m-%d")
    rows.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"block_cal_back_{d.year}_{d.month}",
    )])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await cb.message.edit_text(
        f"🔒 <b>{date_obj.strftime('%d.%m.%Y')}</b>\n\n"
        f"🟢 — свободно  🟡 — заблокировано  🔴 — занято клиентом",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


# ── Назад в календарь из сетки слотов ────────────────────────────────────────

@router.callback_query(Admin.block_time, F.data.startswith("block_cal_back_"))
async def cb_block_back_to_cal(cb: CallbackQuery, state: FSMContext):
    _, _, _, y, m = cb.data.split("_")
    await state.set_state(Admin.block_date)
    await _show_admin_calendar(cb, int(y), int(m))
    await cb.answer()


# ── Блокировать / разблокировать слот ────────────────────────────────────────

@router.callback_query(Admin.block_time, F.data.startswith("block_time_"))
async def cb_do_block(cb: CallbackQuery, state: FSMContext):
    time_str = cb.data[len("block_time_"):]
    data     = await state.get_data()
    result   = db.block_slot(data["block_master_id"], data["block_date"], time_str)
    await cb.answer("✅ Заблокировано" if result else "Уже заблокировано")
    await _render_slots_grid(cb, state, data["block_date"])


@router.callback_query(Admin.block_time, F.data.startswith("unblock_"))
async def cb_do_unblock(cb: CallbackQuery, state: FSMContext):
    slot_id = int(cb.data.split("_")[1])
    db.unblock_slot(slot_id)
    await cb.answer("🟢 Разблокировано")
    data = await state.get_data()
    await _render_slots_grid(cb, state, data["block_date"])


@router.callback_query(Admin.block_time, F.data.startswith("block_noop_"))
async def cb_block_noop(cb: CallbackQuery):
    await cb.answer("🔴 Этот слот занят записью клиента", show_alert=True)
