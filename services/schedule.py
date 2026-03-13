"""
services/schedule.py — логика расписания: доступные даты и слоты
"""

from datetime import datetime, timedelta


def get_next_working_days(count: int = 7) -> list[datetime]:
    """Возвращает count рабочих дней (Пн–Сб), начиная с завтрашнего"""
    dates = []
    current = datetime.now()
    while len(dates) < count:
        current += timedelta(days=1)
        if current.weekday() < 6:   # 0–5 = Пн–Сб
            dates.append(current)
    return dates


def get_all_slots(date_str: str, start: str = "09:00", end: str = "20:00", step: int = 30) -> list[str]:
    """Все слоты с шагом step минут в рабочем диапазоне"""
    slot = datetime.strptime(f"{date_str} {start}", "%Y-%m-%d %H:%M")
    finish = datetime.strptime(f"{date_str} {end}", "%Y-%m-%d %H:%M")
    slots = []
    while slot < finish:
        slots.append(slot.strftime("%H:%M"))
        slot += timedelta(minutes=step)
    return slots


def get_available_slots(date_str: str, duration_min: int, booked: list[str]) -> list[str]:
    """
    Слоты, в которые помещается услуга длительностью duration_min,
    и которые не заняты.
    """
    end_time = datetime.strptime(f"{date_str} 20:00", "%Y-%m-%d %H:%M")
    slot = datetime.strptime(f"{date_str} 09:00", "%Y-%m-%d %H:%M")
    available = []
    while slot + timedelta(minutes=duration_min) <= end_time:
        slot_str = slot.strftime("%H:%M")
        if slot_str not in booked:
            available.append(slot_str)
        slot += timedelta(minutes=30)
    return available
