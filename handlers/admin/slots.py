"""
handlers/admin/slots.py — блокировка и разблокировка слотов (один мастер)

Выбор мастера исключён — используется единственный мастер автоматически.
"""

from datetime import datetime

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from keyboards.inline import block_dates_kb, block_slots_grid_kb
from services.schedule import get_all_slots, get_next_working_days
from states import Admin
from storage.database import db

router = Router()


def _get_sole_master() -> dict:
    masters = db.get_all_masters()
    return masters[0] if masters else {"id": 1, "name": "Мастер"}


@router.callback_query(Admin.menu, F.data == "admin_block")
async def cb_admin_block(cb: CallbackQuery, state: FSMContext):
    master = _get_sole_master()
    await state.update_data(block_master_id=master["id"], block_master_name=master["name"])
    await state.set_state(Admin.block_date)

    dates = get_next_working_days(7)
    await cb.message.edit_text(
        f"🔒 <b>Блокировка времени из журнала</b>\n\nВыберите дату:",
        reply_markup=block_dates_kb(dates, master["id"]),
        parse_mode=ParseMode.HTML,
    )
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
    await cb.message.edit_text(
        f"🔒 <b>{date_obj.strftime('%d.%m.%Y')}</b>\n\n"
        f"🟢 — свободно  🟡 — заблокировано вами  🔴 — занято клиентом",
        reply_markup=block_slots_grid_kb(all_slots, booked, blocked_map, master_id),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(Admin.block_date, F.data.startswith("block_date_"))
async def cb_block_select_time(cb: CallbackQuery, state: FSMContext):
    date_str = cb.data.split("_")[2]
    await state.update_data(block_date=date_str)
    await state.set_state(Admin.block_time)
    await _render_slots_grid(cb, state, date_str)
    await cb.answer()


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
