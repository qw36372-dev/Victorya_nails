"""
handlers/common/start.py — /start и главное меню
"""

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import MASTER_NAME, MASTER_BIO, SALON_NAME
from keyboards.inline import main_menu_kb
from storage.database import db

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db.add_user(user.id, user.first_name, user.last_name, user.username)
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        f"Я — личный бот мастера <b>{MASTER_NAME}</b>\n"
        f"<i>{MASTER_BIO}</i>\n\n"
        f"Здесь вы можете:\n"
        f"• Записаться на маникюр или педикюр\n"
        f"• Выбрать удобную дату и время\n"
        f"• Посмотреть прайс и контакты\n"
        f"• Отменить запись\n\n"
        f"Выберите нужный раздел ниже 👇",
        reply_markup=main_menu_kb(user.id),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text(
        f"💅 Личный бот мастера <b>{MASTER_NAME}</b>\n\n"
        f"Выберите нужный раздел:",
        reply_markup=main_menu_kb(cb.from_user.id),
        parse_mode=ParseMode.HTML,
    )
    await cb.answer()
