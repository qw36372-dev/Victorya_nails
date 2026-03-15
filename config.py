"""
⚙️ Конфигурация бота — Личный бот мастера маникюра

ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ (задаются в панели bothost.ru):
  API_TOKEN        — токен от @BotFather
  DATABASE_URL     — строка подключения к PostgreSQL
  LEADS_CHANNEL_ID — ID приватного канала (узнать через @getmyid_bot)
"""

import os
import sys

# ── Токен бота ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("API_TOKEN")
if not BOT_TOKEN:
    sys.exit("❌ Переменная окружения API_TOKEN не задана!")

# ── База данных ──────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    sys.exit("❌ Переменная окружения DATABASE_URL не задана!")

# ── Канал для лидов ──────────────────────────────────────────────────────────
_leads_raw = os.environ.get("LEADS_CHANNEL_ID")
if not _leads_raw:
    sys.exit("❌ Переменная окружения LEADS_CHANNEL_ID не задана!")
LEADS_CHANNEL_ID: int = int(_leads_raw)

# ── Администраторы ───────────────────────────────────────────────────────────
# Укажите Telegram ID администраторов (узнать через @getmyid_bot)
# Несколько админов: ADMIN_IDS = {111111111, 222222222, 333333333}
ADMIN_IDS: set = {323280426}

# ── Данные мастера ────────────────────────────────────────────────────────────
MASTER_NAME     = "Виктория"           # Ваше имя
MASTER_BIO      = "Мастер маникюра и педикюра, опыт 7 лет 💅"
SALON_NAME      = f"Мастер {MASTER_NAME}"
SALON_ADDRESS   = "Батайск, Октябрьская улица, 129, 346894 • На против 16 школы"
SALON_PHONE     = "+7 (900) 123-45-67"
SALON_WHATSAPP  = "+7 (900) 123-45-67"
SALON_INSTAGRAM = "@vic_nails"
SALON_BUS     = "остановка "почта", 3 мин пешком"
WORK_HOURS      = "Пн-Сб 9:00 – 20:00, Вс — выходной"
