import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DATABASE_PATH, DATABASE_URL

# Check if PostgreSQL URL is provided
USE_POSTGRES = bool(DATABASE_URL and (DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")))

if USE_POSTGRES:
    try:
        import psycopg
        def pg_row_factory(cursor):
            if not cursor.description:
                return lambda values: values
            titles = [c.name for c in cursor.description]
            def make_row(values):
                class Row(dict):
                    def __getitem__(self, key):
                        if isinstance(key, int):
                            return values[key]
                        return super().__getitem__(key)
                return Row(zip(titles, values))
            return make_row
    except ImportError:
        USE_POSTGRES = False

class PgCursorWrapper:
    def __init__(self, pg_cursor):
        self._cur = pg_cursor
        self._lastrowid = None

    def execute(self, sql, params=None):
        clean_sql = sql
        # Translate SQLite '?' to PostgreSQL '%s'
        if "?" in clean_sql:
            clean_sql = clean_sql.replace("?", "%s")

        is_insert = clean_sql.strip().upper().startswith("INSERT INTO")
        has_returning = "RETURNING" in clean_sql.upper()

        if is_insert and not has_returning and ("system_settings" not in clean_sql):
            clean_sql = clean_sql.rstrip("; ") + " RETURNING id;"

        if params is None:
            self._cur.execute(clean_sql)
        else:
            self._cur.execute(clean_sql, params)

        if is_insert and not has_returning and ("system_settings" not in clean_sql):
            try:
                row = self._cur.fetchone()
                if row and "id" in row:
                    self._lastrowid = row["id"]
            except Exception:
                pass
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        return self._lastrowid

    def __iter__(self):
        return iter(self._cur)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

class PgConnectionWrapper:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PgCursorWrapper(self._conn.cursor())

    def execute(self, sql, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

def get_db():
    if DATABASE_URL and ("postgres" in DATABASE_URL):
        try:
            url = DATABASE_URL.strip().strip("'").strip('"')
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://"):]
            conn = psycopg.connect(url, row_factory=pg_row_factory, connect_timeout=10)
            conn.autocommit = False
            return PgConnectionWrapper(conn)
        except Exception as e:
            print(f"[DATABASE WARNING] PostgreSQL ulanishda xatolik: {e}. SQLite rejimiga o'tildi.")

    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 15000;")
    conn.execute("PRAGMA cache_size = -64000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

@contextmanager
def get_db_cursor():
    conn = get_db()
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    conn = get_db()
    is_pg = isinstance(conn, PgConnectionWrapper)
    cur = conn.cursor()
    try:
        if is_pg:
            # 1. users
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'driver')),
                full_name TEXT NOT NULL,
                phone TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 2. buses
            cur.execute("""
            CREATE TABLE IF NOT EXISTS buses (
                id SERIAL PRIMARY KEY,
                plate_number TEXT UNIQUE NOT NULL,
                bus_name TEXT NOT NULL,
                capacity INTEGER DEFAULT 30,
                model TEXT DEFAULT 'Isuzu SAZ NP 37',
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 3. routes
            cur.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id SERIAL PRIMARY KEY,
                route_number TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                bus_id INTEGER REFERENCES buses(id) ON DELETE SET NULL,
                driver_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                telegram_chat_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 4. stops
            cur.execute("""
            CREATE TABLE IF NOT EXISTS stops (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                default_geofence_radius INTEGER NOT NULL DEFAULT 100,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 5. route_stops
            cur.execute("""
            CREATE TABLE IF NOT EXISTS route_stops (
                id SERIAL PRIMARY KEY,
                route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
                stop_id INTEGER NOT NULL REFERENCES stops(id) ON DELETE CASCADE,
                stop_order INTEGER NOT NULL,
                estimated_minutes INTEGER DEFAULT 5,
                UNIQUE(route_id, stop_order),
                UNIQUE(route_id, stop_id)
            );
            """)

            # 6. trips
            cur.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id SERIAL PRIMARY KEY,
                route_id INTEGER NOT NULL REFERENCES routes(id),
                bus_id INTEGER NOT NULL REFERENCES buses(id),
                driver_id INTEGER NOT NULL REFERENCES users(id),
                start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'cancelled')),
                current_stop_id INTEGER REFERENCES stops(id),
                next_stop_id INTEGER REFERENCES stops(id),
                next_stop_order INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 7. gps_positions
            cur.execute("""
            CREATE TABLE IF NOT EXISTS gps_positions (
                id SERIAL PRIMARY KEY,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                bus_id INTEGER NOT NULL REFERENCES buses(id),
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                speed DOUBLE PRECISION DEFAULT 0.0,
                heading DOUBLE PRECISION DEFAULT 0.0,
                accuracy DOUBLE PRECISION DEFAULT 10.0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 8. stop_arrivals
            cur.execute("""
            CREATE TABLE IF NOT EXISTS stop_arrivals (
                id SERIAL PRIMARY KEY,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                stop_id INTEGER NOT NULL REFERENCES stops(id),
                arrived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                telegram_sent INTEGER DEFAULT 0,
                telegram_message_id TEXT,
                UNIQUE(trip_id, stop_id)
            );
            """)

            # 9. notification_jobs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS notification_jobs (
                id SERIAL PRIMARY KEY,
                trip_id INTEGER REFERENCES trips(id) ON DELETE SET NULL,
                stop_id INTEGER REFERENCES stops(id) ON DELETE SET NULL,
                chat_id TEXT NOT NULL,
                message_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'failed')),
                attempts INTEGER DEFAULT 0,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent_at TIMESTAMP
            );
            """)

            # 10. audit_logs
            cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 11. system_settings
            cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
        else:
            # SQLite Tables
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'driver')),
                full_name TEXT NOT NULL,
                phone TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                last_login DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS buses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT UNIQUE NOT NULL,
                bus_name TEXT NOT NULL,
                capacity INTEGER DEFAULT 30,
                model TEXT DEFAULT 'Isuzu SAZ NP 37',
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_number TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                bus_id INTEGER REFERENCES buses(id) ON DELETE SET NULL,
                driver_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                telegram_chat_id TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS stops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                default_geofence_radius INTEGER NOT NULL DEFAULT 100,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_deleted INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS route_stops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
                stop_id INTEGER NOT NULL REFERENCES stops(id) ON DELETE CASCADE,
                stop_order INTEGER NOT NULL,
                estimated_minutes INTEGER DEFAULT 5,
                UNIQUE(route_id, stop_order),
                UNIQUE(route_id, stop_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                route_id INTEGER NOT NULL REFERENCES routes(id),
                bus_id INTEGER NOT NULL REFERENCES buses(id),
                driver_id INTEGER NOT NULL REFERENCES users(id),
                start_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'cancelled')),
                current_stop_id INTEGER REFERENCES stops(id),
                next_stop_id INTEGER REFERENCES stops(id),
                next_stop_order INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS gps_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                bus_id INTEGER NOT NULL REFERENCES buses(id),
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                speed REAL DEFAULT 0.0,
                heading REAL DEFAULT 0.0,
                accuracy REAL DEFAULT 10.0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS stop_arrivals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                stop_id INTEGER NOT NULL REFERENCES stops(id),
                arrived_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                telegram_sent INTEGER DEFAULT 0,
                telegram_message_id TEXT,
                UNIQUE(trip_id, stop_id)
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS notification_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER REFERENCES trips(id) ON DELETE SET NULL,
                stop_id INTEGER REFERENCES stops(id) ON DELETE SET NULL,
                chat_id TEXT NOT NULL,
                message_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'failed')),
                attempts INTEGER DEFAULT 0,
                error_message TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                sent_at DATETIME
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                username TEXT,
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT,
                details TEXT,
                ip_address TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                description TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

        # Fast query indexes for both databases
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trips_route_status ON trips(route_id, status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gps_positions_trip ON gps_positions(trip_id, timestamp);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gps_positions_trip_id_desc ON gps_positions(trip_id, id DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_route_stops_route ON route_stops(route_id, stop_order);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stop_arrivals_trip ON stop_arrivals(trip_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_buses_active ON buses(is_active, is_deleted);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_routes_active ON routes(is_active, is_deleted);")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def log_audit(user_id: int | None, username: str | None, action: str, entity_type: str, entity_id: str | None, details: str, ip_address: str = ""):
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO audit_logs (user_id, username, action, entity_type, entity_id, details, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, action, entity_type, str(entity_id) if entity_id is not None else None, details, ip_address))
