"""
handlers/user/info.py — прайс-лист и контакты
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery

from config import (
    SALON_NAME, SALON_ADDRESS, SALON_PHONE,
    SALON_WHATSAPP, SALON_INSTAGRAM, SALON_BUS, WORK_HOURS,
)
from keyboards.inline import info_kb
from storage.database import db

router = Router()


@router.callback_query(F.data == "price_list")
async def cb_price_list(cb: CallbackQuery):
    services    = db.get_services()
    text        = "💰 <b>Прайс-лист:</b>\n"
    current_cat = None
    for s in services:
        if s["category"] != current_cat:
            current_cat = s["category"]
            text += f"\n<b>── {current_cat} ──</b>\n"
        text += f"{s['emoji']} {s['name']} — от <b>{s['price']}₽</b> ({s['duration']} мин.)\n"

    await cb.message.edit_text(text, reply_markup=info_kb(), parse_mode=ParseMode.HTML)
    await cb.answer()


@router.callback_query(F.data == "contacts")
async def cb_contacts(cb: CallbackQuery):
    await cb.message.edit_text(
        f"📍 <b>{SALON_NAME}</b>\n\n"
        f"🏠 Адрес: {SALON_ADDRESS}\n"
        f"🕐 Режим работы: {WORK_HOURS}\n"
        f"📞 Телефон: {SALON_PHONE}\n"
        f"📱 WhatsApp: {SALON_WHATSAPP}\n"
        f"📷 Instagram: {SALON_INSTAGRAM}\n\n"
        f"🚌 {SALON_BUS}\n"
        f"🅿️ Есть бесплатная парковка",
        reply_markup=info_kb(),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()