"""
storage/models.py — DDL таблиц и начальные данные (seed)
"""

import psycopg2
import psycopg2.extras


# ── DDL ──────────────────────────────────────────────────────────────────────

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id          SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        first_name  TEXT,
        last_name   TEXT,
        username    TEXT,
        name        TEXT,
        phone       TEXT,
        created_at  TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS categories (
        id   SERIAL PRIMARY KEY,
        name TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS services (
        id          SERIAL PRIMARY KEY,
        category_id INTEGER REFERENCES categories(id),
        name        TEXT NOT NULL,
        description TEXT,
        duration    INTEGER NOT NULL,
        price       INTEGER NOT NULL,
        emoji       TEXT DEFAULT '✂️'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS masters (
        id             SERIAL PRIMARY KEY,
        name           TEXT NOT NULL,
        specialization TEXT,
        bio            TEXT,
        is_active      INTEGER DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS master_services (
        master_id  INTEGER REFERENCES masters(id),
        service_id INTEGER REFERENCES services(id),
        PRIMARY KEY (master_id, service_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS appointments (
        id           SERIAL PRIMARY KEY,
        user_id      INTEGER REFERENCES users(id),
        service_id   INTEGER REFERENCES services(id),
        master_id    INTEGER REFERENCES masters(id),
        date         TEXT NOT NULL,
        time         TEXT NOT NULL,
        client_name  TEXT,
        client_phone TEXT,
        notes        TEXT DEFAULT '',
        status       TEXT DEFAULT 'active',
        created_at   TIMESTAMP DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS blocked_slots (
        id         SERIAL PRIMARY KEY,
        master_id  INTEGER REFERENCES masters(id),
        date       TEXT NOT NULL,
        time       TEXT NOT NULL,
        reason     TEXT DEFAULT 'Занято (журнал)',
        created_at TIMESTAMP DEFAULT NOW()
    )
    """,
]


def init_db(conn):
    """Создаёт таблицы, если их нет"""
    with conn.cursor() as cur:
        for stmt in TABLES:
            cur.execute(stmt)


def seed_data(conn):
    """Заполняет начальными данными (только при первом запуске)"""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT COUNT(*) FROM services")
        row = cur.fetchone()
        if row and list(row.values())[0] > 0:
            return  # данные уже есть

        # Категории
        cur.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", ("Маникюр",))
        cat1 = cur.fetchone()["id"]
        cur.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", ("Педикюр",))
        cat2 = cur.fetchone()["id"]
        cur.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", ("Наращивание и коррекция",))
        cat3 = cur.fetchone()["id"]
        cur.execute("INSERT INTO categories (name) VALUES (%s) RETURNING id", ("Дизайн и уход",))
        cat4 = cur.fetchone()["id"]

        # Услуги
        services = [
            # Маникюр
            (cat1, "Маникюр классический",       "Обрезной маникюр без покрытия",           60,   900, "💅"),
            (cat1, "Маникюр + гель-лак",          "Маникюр с покрытием гель-лак",            90,  1500, "💅"),
            (cat1, "Аппаратный маникюр",          "Аппаратный + покрытие гель-лак",          90,  1700, "💅"),
            (cat1, "Комбинированный маникюр",     "Комби + гель-лак, стойкость до 4 недель", 100, 1800, "💅"),
            (cat1, "Мужской маникюр",             "Уход + форма ногтей без покрытия",         60, 1000, "✂️"),
            # Педикюр
            (cat2, "Педикюр классический",        "Обрезной педикюр без покрытия",            75, 1200, "🦶"),
            (cat2, "Педикюр + гель-лак",          "Педикюр с покрытием гель-лак",            100, 1900, "🦶"),
            (cat2, "Аппаратный педикюр",          "Аппаратный + покрытие гель-лак",          100, 2000, "🦶"),
            (cat2, "SPA-педикюр",                 "Педикюр + скраб + маска + массаж",        120, 2500, "🌿"),
            # Наращивание и коррекция
            (cat3, "Наращивание ногтей (гель)",   "Полное наращивание на формы",             150, 3500, "💎"),
            (cat3, "Наращивание ногтей (акрил)",  "Полное наращивание акриловой пудрой",     150, 3800, "💎"),
            (cat3, "Коррекция наращивания",       "Коррекция отросшей зоны",                 120, 2500, "🔧"),
            (cat3, "Снятие нарощенных ногтей",    "Безопасное снятие без вреда",              60, 1000, "🔧"),
            # Дизайн и уход
            (cat4, "Nail-арт (1 ноготь)",         "Дизайн на 1 ногте",                        15,  200, "🎨"),
            (cat4, "Nail-арт (все ногти)",         "Роспись / стемпинг / наклейки",            45,  800, "🎨"),
            (cat4, "Парафинотерапия рук",          "Питание и увлажнение кожи рук",            30,  700, "✨"),
            (cat4, "Парафинотерапия ног",          "Питание и увлажнение кожи ног",            30,  800, "✨"),
            (cat4, "Укрепление ногтей (гель)",    "Тонкое покрытие для защиты ногтей",        60, 1200, "💪"),
        ]
        service_ids = []
        for s in services:
            cur.execute("""
                INSERT INTO services (category_id, name, description, duration, price, emoji)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """, s)
            service_ids.append(cur.fetchone()["id"])

        # Единственный мастер — берём имя из конфига
        from config import MASTER_NAME, MASTER_BIO
        cur.execute(
            "INSERT INTO masters (name, specialization, bio) VALUES (%s,%s,%s) RETURNING id",
            (MASTER_NAME, "Мастер маникюра и педикюра", MASTER_BIO),
        )
        master_id = cur.fetchone()["id"]

        # Привязываем все услуги к единственному мастеру
        cur.executemany(
            "INSERT INTO master_services (master_id, service_id) VALUES (%s,%s) ON CONFLICT DO NOTHING",
            [(master_id, sid) for sid in service_ids],
        )
