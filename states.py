"""
FSM состояния бота
"""

from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    """Сценарий записи клиента"""
    select_service = State()
    select_date    = State()
    select_time    = State()
    enter_name     = State()
    enter_phone    = State()
    enter_notes    = State()
    confirm        = State()


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


class AdminReschedule(StatesGroup):
    """Предложение нового времени клиенту"""
    enter_datetime = State()   # мастер вводит новую дату и время
