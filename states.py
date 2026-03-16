"""
FSM состояния бота
"""

from aiogram.fsm.state import State, StatesGroup


class Booking(StatesGroup):
    """Сценарий записи клиента"""
    select_service  = State()
    select_date     = State()
    select_time     = State()
    choose_client   = State()   # для себя или для другого
    enter_name      = State()   # новый клиент — своё имя
    enter_phone     = State()   # новый клиент — свой телефон
    enter_other_name  = State() # запись для другого — имя
    enter_other_phone = State() # запись для другого — телефон
    enter_notes     = State()
    confirm         = State()


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
    """Предложение нового времени клиенту — мастер выбирает через календарь"""
    select_date = State()   # мастер выбирает дату в календаре
    select_time = State()   # мастер выбирает время


class ClientCounter(StatesGroup):
    """Клиент предлагает своё время в ответ на перенос"""
    enter_datetime = State()
