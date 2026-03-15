"""
services/schedule.py — логика расписания: доступные даты и слоты
"""

import calendar
from datetime import date, datetime, timedelta


def get_all_slots(date_str: str, start: str = "09:00", end: str = "20:00", step: int = 30) -> list[str]:
    """Все слоты с шагом step минут в рабочем диапазоне"""
    slot   = datetime.strptime(f"{date_str} {start}", "%Y-%m-%d %H:%M")
    finish = datetime.strptime(f"{date_str} {end}",   "%Y-%m-%d %H:%M")
    slots  = []
    while slot < finish:
        slots.append(slot.strftime("%H:%M"))
        slot += timedelta(minutes=step)
    return slots


def get_available_slots(date_str: str, duration_min: int, booked: list[str]) -> list[str]:
    """Слоты, в которые помещается услуга длительностью duration_min, и которые не заняты."""
    end_time = datetime.strptime(f"{date_str} 20:00", "%Y-%m-%d %H:%M")
    slot     = datetime.strptime(f"{date_str} 09:00", "%Y-%m-%d %H:%M")
    available = []
    while slot + timedelta(minutes=duration_min) <= end_time:
        slot_str = slot.strftime("%H:%M")
        if slot_str not in booked:
            available.append(slot_str)
        slot += timedelta(minutes=30)
    return available


def get_available_dates_in_month(year: int, month: int, master_id: int, duration_min: int) -> set[str]:
    """
    Возвращает множество строк YYYY-MM-DD для дней месяца,
    где есть хотя бы один свободный слот (Пн–Сб, не прошедшие).
    """
    from storage.database import db   # отложенный импорт — избегаем кругового

    today = date.today()
    available = set()
    _, days_in_month = calendar.monthrange(year, month)

    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        if d <= today:          # сегодня и прошлое — пропускаем
            continue
        if d.weekday() == 6:    # воскресенье — выходной
            continue
        date_str = d.strftime("%Y-%m-%d")
        booked = db.get_booked_slots(master_id, date_str)
        if get_available_slots(date_str, duration_min, booked):
            available.add(date_str)

    return available
