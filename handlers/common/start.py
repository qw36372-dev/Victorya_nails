"""
handlers/common/start.py — /start и главное меню
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import MASTER_NAME, MASTER_BIO
from keyboards.inline import main_menu_kb
from storage.database import db

router = Router()


def _menu_text(first_name: str = "") -> str:
    greeting = f"👋 Привет, {first_name}!\n\n" if first_name else ""
    return (
        f"{greeting}"
        f"Я — личный бот мастера <b>{MASTER_NAME}</b>\n"
        f"<i>{MASTER_BIO}</i>\n\n"
        f"Здесь вы можете:\n"
        f"• Записаться на маникюр или педикюр\n"
        f"• Выбрать удобную дату и время\n"
        f"• Посмотреть прайс и контакты\n"
        f"• Отменить запись\n\n"
        f"Выберите нужный раздел 👇"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db.add_user(user.id, user.first_name, user.last_name, user.username)
    user_info   = db.get_user_info(user.id)
    has_contact = bool(user_info and user_info.get("phone"))
    await message.answer(
        _menu_text(user.first_name),
        reply_markup=main_menu_kb(user.id, has_contact=has_contact),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    user_info   = db.get_user_info(cb.from_user.id)
    has_contact = bool(user_info and user_info.get("phone"))
    await cb.message.edit_text(
        f"💅 Личный бот мастера <b>{MASTER_NAME}</b>\n\n"
        f"Выберите нужный раздел:",
        reply_markup=main_menu_kb(cb.from_user.id, has_contact=has_contact),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


# ── Очистка данных клиента ────────────────────────────────────────────────────

@router.callback_query(F.data == "clear_my_data")
async def cb_clear_my_data(cb: CallbackQuery):
    user_info = db.get_user_info(cb.from_user.id)
    name      = user_info.get("name", "") if user_info else ""
    await cb.message.edit_text(
        f"🗑 <b>Удалить сохранённые данные?</b>\n\n"
        f"Имя: <b>{name}</b>\n\n"
        f"После удаления при следующей записи бот снова попросит "
        f"ввести имя и телефон.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, удалить",  callback_data="clear_confirm"),
                InlineKeyboardButton(text="❌ Отмена",       callback_data="main_menu"),
            ]
        ]),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()


@router.callback_query(F.data == "clear_confirm")
async def cb_clear_confirm(cb: CallbackQuery):
    db.clear_user_contact(cb.from_user.id)
    await cb.message.edit_text(
        "✅ <b>Данные удалены.</b>\n\n"
        "При следующей записи вас попросят ввести имя и телефон заново.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ]),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()
