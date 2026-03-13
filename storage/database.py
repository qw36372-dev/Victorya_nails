"""
storage/database.py — класс Database и единственный экземпляр db
"""

import psycopg2
import psycopg2.extras
from typing import Optional

from config import DATABASE_URL
from storage.models import init_db, seed_data


class Database:
    """Все методы работы с PostgreSQL через psycopg2"""

    def __init__(self):
        conn = self._get_conn()
        init_db(conn)
        conn.commit()
        seed_data(conn)
        conn.commit()
        conn.close()

    # ── Низкоуровневый хелпер ────────────────────────────────────────────────

    def _get_conn(self):
        return psycopg2.connect(DATABASE_URL)

    def _exec(self, sql: str, params=None, fetch: Optional[str] = None):
        """
        Выполняет SQL и возвращает результат.
        fetch: "one" | "all" | "scalar" | None
        """
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params or ())
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                if fetch == "scalar":
                    row = cur.fetchone()
                    return list(row.values())[0] if row else None
                return None

    # ── Пользователи ─────────────────────────────────────────────────────────

    def add_user(self, telegram_id: int, first_name: str, last_name: str, username: str):
        self._exec("""
            INSERT INTO users (telegram_id, first_name, last_name, username)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (telegram_id) DO UPDATE
                SET first_name = EXCLUDED.first_name,
                    last_name  = EXCLUDED.last_name,
                    username   = EXCLUDED.username
        """, (telegram_id, first_name, last_name, username))

    def update_user_contact(self, telegram_id: int, name: str, phone: str):
        self._exec(
            "UPDATE users SET name = %s, phone = %s WHERE telegram_id = %s",
            (name, phone, telegram_id),
        )

    def get_user_info(self, telegram_id: int) -> Optional[dict]:
        row = self._exec(
            "SELECT * FROM users WHERE telegram_id = %s", (telegram_id,), fetch="one"
        )
        return dict(row) if row else None

    def get_total_users(self) -> int:
        return self._exec("SELECT COUNT(*) FROM users", fetch="scalar") or 0

    def get_user_by_internal_id(self, internal_id: int) -> Optional[dict]:
        row = self._exec("SELECT * FROM users WHERE id = %s", (internal_id,), fetch="one")
        return dict(row) if row else None

    # ── Услуги ───────────────────────────────────────────────────────────────

    def get_services(self) -> list:
        rows = self._exec("""
            SELECT s.*, c.name AS category
            FROM services s
            JOIN categories c ON s.category_id = c.id
            ORDER BY s.category_id, s.id
        """, fetch="all")
        return [dict(r) for r in rows] if rows else []

    def get_service(self, service_id: int) -> Optional[dict]:
        row = self._exec("""
            SELECT s.*, c.name AS category
            FROM services s JOIN categories c ON s.category_id = c.id
            WHERE s.id = %s
        """, (service_id,), fetch="one")
        return dict(row) if row else None

    # ── Мастера ──────────────────────────────────────────────────────────────

    def get_all_masters(self) -> list:
        rows = self._exec(
            "SELECT * FROM masters WHERE is_active = 1 ORDER BY name", fetch="all"
        )
        return [dict(r) for r in rows] if rows else []

    def get_masters_by_service(self, service_id: int) -> list:
        rows = self._exec("""
            SELECT m.* FROM masters m
            JOIN master_services ms ON m.id = ms.master_id
            WHERE ms.service_id = %s AND m.is_active = 1
        """, (service_id,), fetch="all")
        return [dict(r) for r in rows] if rows else []

    def get_master(self, master_id: int) -> Optional[dict]:
        row = self._exec("SELECT * FROM masters WHERE id = %s", (master_id,), fetch="one")
        return dict(row) if row else None

    # ── Записи ───────────────────────────────────────────────────────────────

    def get_booked_slots(self, master_id: int, date: str) -> list:
        """Возвращает список занятых слотов (appointments + blocked_slots) в формате HH:MM"""

        def to_str(val):
            return val.strftime("%H:%M") if hasattr(val, "strftime") else str(val)[:5]

        booked = self._exec("""
            SELECT time FROM appointments
            WHERE master_id = %s AND date = %s AND status = 'active'
        """, (master_id, date), fetch="all") or []

        blocked = self._exec("""
            SELECT time FROM blocked_slots
            WHERE master_id = %s AND date = %s
        """, (master_id, date), fetch="all") or []

        return [to_str(r["time"]) for r in booked] + [to_str(r["time"]) for r in blocked]

    def create_appointment(
        self, user_id: int, service_id: int, master_id: int,
        date: str, time: str, client_name: str, client_phone: str, notes: str = "",
    ) -> int:
        user_row = self._exec(
            "SELECT id FROM users WHERE telegram_id = %s", (user_id,), fetch="one"
        )
        internal_user_id = user_row["id"] if user_row else None
        row = self._exec("""
            INSERT INTO appointments
                (user_id, service_id, master_id, date, time, client_name, client_phone, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (internal_user_id, service_id, master_id, date, time, client_name, client_phone, notes),
            fetch="one",
        )
        return row["id"]

    def get_appointment(self, appointment_id: int) -> Optional[dict]:
        row = self._exec("""
            SELECT a.*, s.name AS service_name, s.price,
                   m.name AS master_name,
                   u.telegram_id AS client_telegram_id
            FROM appointments a
            JOIN services s ON a.service_id = s.id
            JOIN masters  m ON a.master_id  = m.id
            LEFT JOIN users u ON a.user_id  = u.id
            WHERE a.id = %s
        """, (appointment_id,), fetch="one")
        return dict(row) if row else None

    def get_user_appointments(self, telegram_id: int) -> list:
        rows = self._exec("""
            SELECT a.*, s.name AS service_name, s.price, m.name AS master_name
            FROM appointments a
            JOIN users    u ON a.user_id    = u.id
            JOIN services s ON a.service_id = s.id
            JOIN masters  m ON a.master_id  = m.id
            WHERE u.telegram_id = %s AND a.status = 'active'
              AND (a.date::date > CURRENT_DATE
                   OR (a.date::date = CURRENT_DATE AND a.time::time >= CURRENT_TIME))
            ORDER BY a.date, a.time
        """, (telegram_id,), fetch="all")
        return [dict(r) for r in rows] if rows else []

    def cancel_appointment(self, appointment_id: int):
        self._exec(
            "UPDATE appointments SET status = 'cancelled' WHERE id = %s", (appointment_id,)
        )

    def get_appointments_by_date(self, date: str) -> list:
        rows = self._exec("""
            SELECT a.*, s.name AS service_name, m.name AS master_name
            FROM appointments a
            JOIN services s ON a.service_id = s.id
            JOIN masters  m ON a.master_id  = m.id
            WHERE a.date = %s AND a.status = 'active'
            ORDER BY a.time
        """, (date,), fetch="all")
        return [dict(r) for r in rows] if rows else []

    def get_active_future_appointments(self) -> list:
        """Все будущие активные записи — для восстановления напоминаний"""
        rows = self._exec("""
            SELECT * FROM appointments
            WHERE status = 'active'
              AND (date::date > CURRENT_DATE
                   OR (date::date = CURRENT_DATE AND time::time > CURRENT_TIME))
        """, fetch="all")
        return [dict(r) for r in rows] if rows else []

    # ── Блокировка слотов ────────────────────────────────────────────────────

    def block_slot(self, master_id: int, date: str, time: str, reason: str = "Занято (журнал)") -> bool:
        exists = self._exec(
            "SELECT id FROM blocked_slots WHERE master_id=%s AND date=%s AND time=%s",
            (master_id, date, time), fetch="one",
        )
        if not exists:
            self._exec(
                "INSERT INTO blocked_slots (master_id, date, time, reason) VALUES (%s,%s,%s,%s)",
                (master_id, date, time, reason),
            )
            return True
        return False

    def unblock_slot(self, slot_id: int):
        self._exec("DELETE FROM blocked_slots WHERE id = %s", (slot_id,))

    def get_blocked_slots_by_master_date(self, master_id: int, date: str) -> list:
        rows = self._exec("""
            SELECT * FROM blocked_slots
            WHERE master_id = %s AND date = %s
            ORDER BY time
        """, (master_id, date), fetch="all")
        return [dict(r) for r in rows] if rows else []

    # ── Статистика ───────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        return {
            "total_users": self._exec("SELECT COUNT(*) FROM users", fetch="scalar") or 0,
            "total_appointments": self._exec("SELECT COUNT(*) FROM appointments", fetch="scalar") or 0,
            "active_appointments": self._exec(
                "SELECT COUNT(*) FROM appointments WHERE status='active'", fetch="scalar"
            ) or 0,
            "cancelled_appointments": self._exec(
                "SELECT COUNT(*) FROM appointments WHERE status='cancelled'", fetch="scalar"
            ) or 0,
            "expected_revenue": self._exec("""
                SELECT COALESCE(SUM(s.price), 0)
                FROM appointments a
                JOIN services s ON a.service_id = s.id
                WHERE a.status = 'active'
            """, fetch="scalar") or 0,
        }


# Единственный экземпляр — импортируется всеми модулями
db = Database()
