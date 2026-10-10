import sqlite3
from contextlib import contextmanager
from datetime import datetime
from config import DATABASE_PATH

def get_db():
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
    with get_db_cursor() as cur:
        # 1. users
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

        # 2. buses
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

        # 3. routes
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

        # 4. stops
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

        # 5. route_stops
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

        # 6. trips
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

        # 7. gps_positions
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

        # 8. stop_arrivals
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

        # 9. notification_jobs
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

        # 10. audit_logs
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

        # 11. system_settings
        cur.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            description TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # Indexes for fast querying under high concurrency (100+ users)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trips_status ON trips(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trips_route_status ON trips(route_id, status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gps_positions_trip ON gps_positions(trip_id, timestamp);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_gps_positions_trip_id_desc ON gps_positions(trip_id, id DESC);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_route_stops_route ON route_stops(route_id, stop_order);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_stop_arrivals_trip ON stop_arrivals(trip_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_buses_active ON buses(is_active, is_deleted);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_routes_active ON routes(is_active, is_deleted);")

def log_audit(user_id: int | None, username: str | None, action: str, entity_type: str, entity_id: str | None, details: str, ip_address: str = ""):
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO audit_logs (user_id, username, action, entity_type, entity_id, details, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, action, entity_type, str(entity_id) if entity_id is not None else None, details, ip_address))
