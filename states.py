"""
FSM состояния бота
"""

from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    """Сценарий записи клиента"""
    select_service = State()   # выбор услуги
    select_master  = State()   # выбор мастера
    select_date    = State()   # выбор даты
    select_time    = State()   # выбор времени
    enter_name     = State()   # ввод имени
    enter_phone    = State()   # ввод телефона
    enter_notes    = State()   # пожелания / комментарий
    confirm        = State()   # подтверждение


class MyAppointments(StatesGroup):
    """Просмотр и отмена записей"""
    view           = State()
    confirm_cancel = State()


class Admin(StatesGroup):
    """Панель администратора"""
    menu         = State()
    block_master = State()
    block_date   = State()
    block_time   = State()
