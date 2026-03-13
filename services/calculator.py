"""
services/calculator.py — вспомогательная логика по услугам
"""

from datetime import datetime, timedelta


def calc_end_time(date_str: str, time_str: str, duration_min: int) -> str:
    """Возвращает время окончания услуги в формате HH:MM"""
    start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return (start + timedelta(minutes=duration_min)).strftime("%H:%M")
