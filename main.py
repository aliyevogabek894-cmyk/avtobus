import os
from datetime import datetime, date
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, Query, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import (
    BASE_DIR,
    GPS_STALE_THRESHOLD_SECONDS,
    DEFAULT_GEOFENCE_RADIUS,
    TELEGRAM_BOT_TOKEN,
    DEFAULT_TELEGRAM_CHAT_ID
)
from database import get_db, get_db_cursor, init_db, log_audit
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
    require_admin,
    require_driver
)
from gps_service import process_driver_gps, haversine_distance
from telegram_service import send_telegram_message

# Initialize App and DB
init_db()

app = FastAPI(
    title="Smart School Bus Management & GPS Tracking API",
    description="Maktab avtobuslari boshqaruv va jonli GPS kuzatuv platformasi",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- PYDANTIC SCHEMAS -----------------

class LoginRequest(BaseModel):
    username: str
    password: str

class PasswordResetRequest(BaseModel):
    new_password: str

class BusCreateRequest(BaseModel):
    plate_number: str
    bus_name: str
    capacity: int = 30
    model: str = "Isuzu SAZ NP 37"

class BusUpdateRequest(BaseModel):
    plate_number: Optional[str] = None
    bus_name: Optional[str] = None
    capacity: Optional[int] = None
    model: Optional[str] = None
    is_active: Optional[int] = None

class RouteCreateRequest(BaseModel):
    route_number: str
    name: str
    description: Optional[str] = ""
    bus_id: Optional[int] = None
    driver_id: Optional[int] = None
    telegram_chat_id: Optional[str] = ""

class RouteUpdateRequest(BaseModel):
    route_number: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    bus_id: Optional[int] = None
    driver_id: Optional[int] = None
    telegram_chat_id: Optional[str] = None
    is_active: Optional[int] = None

class StopCreateRequest(BaseModel):
    name: str
    latitude: float
    longitude: float
    default_geofence_radius: int = 100

class StopUpdateRequest(BaseModel):
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    default_geofence_radius: Optional[int] = None
    is_active: Optional[int] = None

class RouteStopAddRequest(BaseModel):
    stop_id: int
    stop_order: int
    estimated_minutes: int = 5

class RouteStopReorderRequest(BaseModel):
    stop_orders: List[dict]  # list of {"stop_id": 1, "order": 1}

class DriverCreateRequest(BaseModel):
    username: str
    password: str
    full_name: str
    phone: Optional[str] = ""
    route_id: Optional[int] = None
    bus_id: Optional[int] = None

class DriverUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[int] = None
    route_id: Optional[int] = None
    bus_id: Optional[int] = None

class GPSPayload(BaseModel):
    trip_id: int
    latitude: float
    longitude: float
    speed: float = 0.0
    heading: float = 0.0
    accuracy: float = 10.0

class TelegramSettingsRequest(BaseModel):
    bot_token: str
    default_chat_id: str

class TelegramTestRequest(BaseModel):
    chat_id: str
    message: Optional[str] = None

# ----------------- PUBLIC / PARENTS ENDPOINTS -----------------

@app.get("/api/public/routes")
def get_public_routes():
    """
    Returns list of all active routes for parents with live bus tracking status.
    Notice: Driver private personal data is excluded for privacy.
    """
    conn = get_db()
    try:
        routes = conn.execute("""
            SELECT r.id, r.route_number, r.name, r.description,
                   b.id as bus_id, b.bus_name, b.plate_number, b.model as bus_model
            FROM routes r
            LEFT JOIN buses b ON r.bus_id = b.id
            WHERE r.is_active = 1 AND r.is_deleted = 0
            ORDER BY r.id ASC
        """).fetchall()

        result = []
        for r in routes:
            route_dict = dict(r)

            # Get active trip if any
            trip = conn.execute("""
                SELECT t.id, t.start_time, t.next_stop_order, t.current_stop_id, t.next_stop_id,
                       s_cur.name as current_stop_name, s_next.name as next_stop_name
                FROM trips t
                LEFT JOIN stops s_cur ON t.current_stop_id = s_cur.id
                LEFT JOIN stops s_next ON t.next_stop_id = s_next.id
                WHERE t.route_id = ? AND t.status = 'active'
                ORDER BY t.id DESC LIMIT 1
            """, (r["id"],)).fetchone()

            # Count total stops
            stops_count = conn.execute("""
                SELECT COUNT(*) FROM route_stops rs
                JOIN stops s ON rs.stop_id = s.id
                WHERE rs.route_id = ? AND s.is_deleted = 0
            """, (r["id"],)).fetchone()[0]
            route_dict["total_stops"] = stops_count

            if trip:
                route_dict["is_in_trip"] = True
                route_dict["active_trip_id"] = trip["id"]
                route_dict["trip_start_time"] = trip["start_time"]
                route_dict["current_stop_name"] = trip["current_stop_name"]
                route_dict["next_stop_name"] = trip["next_stop_name"]

                # Get latest GPS
                latest_gps = conn.execute("""
                    SELECT latitude, longitude, speed, heading, timestamp
                    FROM gps_positions
                    WHERE trip_id = ?
                    ORDER BY id DESC LIMIT 1
                """, (trip["id"],)).fetchone()

                if latest_gps:
                    route_dict["latest_gps"] = dict(latest_gps)
                    # Check staleness
                    try:
                        gps_time = datetime.fromisoformat(str(latest_gps["timestamp"]).replace(" ", "T"))
                        diff_sec = (datetime.utcnow() - gps_time).total_seconds()
                        route_dict["is_gps_stale"] = diff_sec > GPS_STALE_THRESHOLD_SECONDS
                    except Exception:
                        route_dict["is_gps_stale"] = False
                else:
                    route_dict["latest_gps"] = None
                    route_dict["is_gps_stale"] = True
            else:
                route_dict["is_in_trip"] = False
                route_dict["active_trip_id"] = None
                route_dict["latest_gps"] = None
                route_dict["is_gps_stale"] = False
                route_dict["current_stop_name"] = None
                route_dict["next_stop_name"] = None

            result.append(route_dict)

        return {"routes": result}
    finally:
        conn.close()

@app.get("/api/public/routes/{route_id}")
def get_public_route_detail(route_id: int):
    """
    Detailed route view for parents: route stops, live bus GPS, completed stops, next stop.
    """
    conn = get_db()
    try:
        route = conn.execute("""
            SELECT r.id, r.route_number, r.name, r.description,
                   b.bus_name, b.plate_number, b.model
            FROM routes r
            LEFT JOIN buses b ON r.bus_id = b.id
            WHERE r.id = ? AND r.is_active = 1 AND r.is_deleted = 0
        """, (route_id,)).fetchone()

        if not route:
            raise HTTPException(status_code=404, detail="Yo'nalish topilmadi")

        route_data = dict(route)

        # Get route stops
        stops_rows = conn.execute("""
            SELECT rs.stop_order, rs.estimated_minutes,
                   s.id, s.name, s.latitude, s.longitude, s.default_geofence_radius
            FROM route_stops rs
            JOIN stops s ON rs.stop_id = s.id
            WHERE rs.route_id = ? AND s.is_deleted = 0
            ORDER BY rs.stop_order ASC
        """, (route_id,)).fetchall()

        stops_list = [dict(s) for s in stops_rows]

        # Active trip check
        trip = conn.execute("""
            SELECT * FROM trips
            WHERE route_id = ? AND status = 'active'
            ORDER BY id DESC LIMIT 1
        """, (route_id,)).fetchone()

        visited_stop_ids = []
        arrivals_list = []
        latest_gps = None
        is_gps_stale = False
        next_target_stop = None

        if trip:
            # Visited stops with names and exact times for on-site parent notifications
            arrivals = conn.execute("""
                SELECT sa.stop_id, sa.arrived_at, s.name as stop_name
                FROM stop_arrivals sa
                JOIN stops s ON sa.stop_id = s.id
                WHERE sa.trip_id = ?
                ORDER BY sa.id ASC
            """, (trip["id"],)).fetchall()
            visited_stop_ids = [a["stop_id"] for a in arrivals]
            arrivals_list = [dict(a) for a in arrivals]

            # Latest GPS
            gps_row = conn.execute("""
                SELECT latitude, longitude, speed, heading, accuracy, timestamp
                FROM gps_positions
                WHERE trip_id = ?
                ORDER BY id DESC LIMIT 1
            """, (trip["id"],)).fetchone()

            if gps_row:
                latest_gps = dict(gps_row)
                try:
                    gps_time = datetime.fromisoformat(str(gps_row["timestamp"]).replace(" ", "T"))
                    diff_sec = (datetime.utcnow() - gps_time).total_seconds()
                    is_gps_stale = diff_sec > GPS_STALE_THRESHOLD_SECONDS
                except Exception:
                    is_gps_stale = False

            # Next stop
            next_order = trip["next_stop_order"] or 1
            for s in stops_list:
                if s["stop_order"] >= next_order:
                    next_target_stop = s
                    break

        return {
            "route": route_data,
            "stops": stops_list,
            "trip": dict(trip) if trip else None,
            "visited_stop_ids": visited_stop_ids,
            "arrivals": arrivals_list,
            "latest_gps": latest_gps,
            "is_gps_stale": is_gps_stale,
            "next_stop": next_target_stop
        }
    finally:
        conn.close()

import httpx

@app.get("/api/public/school")
def get_school_info():
    """
    Get Central School location in Fergana city.
    """
    return {
        "name": "Farg'ona Bosh Maktabi",
        "city": "Farg'ona",
        "address": "Farg'ona shahri, Al-Farg'oniy / Sayilgoh ko'chasi",
        "latitude": 40.386400,
        "longitude": 71.786400
    }

@app.get("/api/public/stops")
def public_get_all_stops():
    """
    Get all active stops for parents and public overview.
    """
    conn = get_db()
    try:
        stops = conn.execute("""
            SELECT s.id, s.name, s.latitude, s.longitude, s.default_geofence_radius,
                   (SELECT COUNT(*) FROM route_stops rs WHERE rs.stop_id = s.id) as routes_count
            FROM stops s
            WHERE s.is_deleted = 0 AND s.is_active = 1
            ORDER BY s.id ASC
        """).fetchall()
        return {"stops": [dict(s) for s in stops]}
    finally:
        conn.close()

@app.get("/api/public/geocode/search")
async def geocode_search(q: str = Query(..., min_length=2)):
    """
    Search online map places/stops in Fergana & Uzbekistan via OpenStreetMap Nominatim.
    Prioritizes Fergana coordinates.
    """
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": "SmartSchoolBus-Fergana/2.0 (maktab-avtobus@fergana.uz)"}
    
    # 1st try: Fergana viewbox prioritised
    params = {
        "q": q,
        "format": "json",
        "countrycodes": "uz",
        "viewbox": "71.60,40.48,71.95,40.30",
        "bounded": 0,
        "limit": 8,
        "addressdetails": 1
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(url, params=params, headers=headers)
            if res.status_code == 200:
                results = res.json()
                if results and len(results) > 0:
                    return {"results": results}
            
            # 2nd try if no results: Append 'Fargona'
            if "farg" not in q.lower():
                params["q"] = f"{q}, Farg'ona"
                res2 = await client.get(url, params=params, headers=headers)
                if res2.status_code == 200:
                    results2 = res2.json()
                    if results2:
                        return {"results": results2}
    except Exception as e:
        pass
    return {"results": []}

@app.get("/api/public/geocode/reverse")
async def geocode_reverse(lat: float, lon: float):
    """
    Reverse geocode coordinates to human-readable street/place name.
    """
    url = "https://nominatim.openstreetmap.org/reverse"
    headers = {"User-Agent": "SmartSchoolBus-Fergana/2.0 (maktab-avtobus@fergana.uz)"}
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json"
    }
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(url, params=params, headers=headers)
            if res.status_code == 200:
                data = res.json()
                display_name = data.get("display_name", "")
                name = data.get("name") or display_name.split(",")[0]
                return {"name": name, "display_name": display_name}
    except Exception as e:
        pass
    return {"name": f"Bekat ({lat:.4f}, {lon:.4f})", "display_name": ""}

# ----------------- DRIVER AUTH & PORTAL ENDPOINTS -----------------

@app.post("/api/driver/login")
def driver_login(payload: LoginRequest, request: Request):
    conn = get_db()
    try:
        user = conn.execute("""
            SELECT * FROM users
            WHERE username = ? AND is_active = 1
        """, (payload.username,)).fetchone()

        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Noto'g'ri login yoki parol")

        if user["role"] not in ("driver", "admin"):
            raise HTTPException(status_code=403, detail="Ushbu hisob haydovchi emas")

        # Update last login
        with get_db_cursor() as cur:
            cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))

        # Fetch assigned route and bus
        route = conn.execute("""
            SELECT r.*, b.bus_name, b.plate_number, b.model
            FROM routes r
            LEFT JOIN buses b ON r.bus_id = b.id
            WHERE r.driver_id = ? AND r.is_active = 1 AND r.is_deleted = 0
            LIMIT 1
        """, (user["id"],)).fetchone()

        token = create_access_token({"sub": str(user["id"]), "role": user["role"]})
        
        client_ip = request.client.host if request.client else ""
        log_audit(user["id"], user["username"], "driver_login", "user", str(user["id"]), "Haydovchi tizimga kirdi", client_ip)

        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"]
            },
            "assigned_route": dict(route) if route else None
        }
    finally:
        conn.close()

@app.get("/api/driver/my-route")
def driver_get_my_route(user: dict = Depends(require_driver)):
    conn = get_db()
    try:
        route = conn.execute("""
            SELECT r.*, b.id as bus_id, b.bus_name, b.plate_number, b.model
            FROM routes r
            LEFT JOIN buses b ON r.bus_id = b.id
            WHERE r.driver_id = ? AND r.is_active = 1 AND r.is_deleted = 0
            LIMIT 1
        """, (user["id"],)).fetchone()

        if not route:
            return {"route": None, "stops": [], "active_trip": None}

        stops = conn.execute("""
            SELECT rs.stop_order, rs.estimated_minutes,
                   s.id, s.name, s.latitude, s.longitude, s.default_geofence_radius
            FROM route_stops rs
            JOIN stops s ON rs.stop_id = s.id
            WHERE rs.route_id = ? AND s.is_deleted = 0
            ORDER BY rs.stop_order ASC
        """, (route["id"],)).fetchall()

        # Check for active trip
        active_trip = conn.execute("""
            SELECT t.*, s.name as next_stop_name
            FROM trips t
            LEFT JOIN stops s ON t.next_stop_id = s.id
            WHERE t.driver_id = ? AND t.status = 'active'
            ORDER BY t.id DESC LIMIT 1
        """, (user["id"],)).fetchone()

        return {
            "route": dict(route),
            "stops": [dict(s) for s in stops],
            "active_trip": dict(active_trip) if active_trip else None
        }
    finally:
        conn.close()

@app.post("/api/driver/trip/start")
def driver_start_trip(user: dict = Depends(require_driver)):
    conn = get_db()
    try:
        # Check assigned route
        route = conn.execute("""
            SELECT * FROM routes
            WHERE driver_id = ? AND is_active = 1 AND is_deleted = 0
            LIMIT 1
        """, (user["id"],)).fetchone()

        if not route:
            raise HTTPException(status_code=400, detail="Sizga faol yo'nalish biriktirilmagan")

        if not route["bus_id"]:
            raise HTTPException(status_code=400, detail="Ushbu yo'nalishga avtobus biriktirilmagan")

        # Check if already has active trip
        existing = conn.execute("""
            SELECT * FROM trips WHERE driver_id = ? AND status = 'active'
        """, (user["id"],)).fetchone()

        if existing:
            return {"success": True, "message": "Faol safar mavjud", "trip": dict(existing)}

        # Find first stop in route
        first_stop = conn.execute("""
            SELECT rs.stop_id, rs.stop_order
            FROM route_stops rs
            JOIN stops s ON rs.stop_id = s.id
            WHERE rs.route_id = ? AND s.is_deleted = 0
            ORDER BY rs.stop_order ASC LIMIT 1
        """, (route["id"],)).fetchone()

        first_stop_id = first_stop["stop_id"] if first_stop else None

        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO trips (route_id, bus_id, driver_id, status, next_stop_id, next_stop_order)
                VALUES (?, ?, ?, 'active', ?, 1)
            """, (route["id"], route["bus_id"], user["id"], first_stop_id))
            trip_id = cur.lastrowid

        log_audit(user["id"], user["username"], "trip_start", "trip", str(trip_id), f"Safar boshlandi. Yo'nalish #{route['id']}")

        return {
            "success": True,
            "message": "Safar muvaffaqiyatli boshlandi",
            "trip": {
                "id": trip_id,
                "route_id": route["id"],
                "bus_id": route["bus_id"],
                "driver_id": user["id"],
                "status": "active",
                "next_stop_order": 1
            }
        }
    finally:
        conn.close()

@app.post("/api/driver/trip/gps")
async def driver_send_gps(payload: GPSPayload, user: dict = Depends(require_driver)):
    """
    Driver device regularly submits GPS coordinates.
    Server verifies geofencing against next stop, triggers Telegram arrival alert if reached.
    """
    res = await process_driver_gps(
        trip_id=payload.trip_id,
        driver_id=user["id"],
        latitude=payload.latitude,
        longitude=payload.longitude,
        speed=payload.speed,
        heading=payload.heading,
        accuracy=payload.accuracy
    )
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.post("/api/driver/trip/end")
def driver_end_trip(user: dict = Depends(require_driver)):
    conn = get_db()
    try:
        active_trip = conn.execute("""
            SELECT * FROM trips WHERE driver_id = ? AND status = 'active'
        """, (user["id"],)).fetchone()

        if not active_trip:
            raise HTTPException(status_code=400, detail="Hozirda faol safar mavjud emas")

        with get_db_cursor() as cur:
            cur.execute("""
                UPDATE trips
                SET status = 'completed', end_time = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (active_trip["id"],))

        log_audit(user["id"], user["username"], "trip_end", "trip", str(active_trip["id"]), "Safar yakunlandi")

        return {"success": True, "message": "Safar muvaffaqiyatli yakunlandi"}
    finally:
        conn.close()

# ----------------- ADMIN DASHBOARD & CRUD ENDPOINTS -----------------

@app.post("/api/admin/login")
def admin_login(payload: LoginRequest, request: Request):
    conn = get_db()
    try:
        user = conn.execute("""
            SELECT * FROM users WHERE username = ? AND is_active = 1
        """, (payload.username,)).fetchone()

        if not user or not verify_password(payload.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Noto'g'ri login yoki parol")

        if user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Faqat administrator uchun ruxsat berilgan")

        with get_db_cursor() as cur:
            cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],))

        token = create_access_token({"sub": str(user["id"]), "role": "admin"})

        client_ip = request.client.host if request.client else ""
        log_audit(user["id"], user["username"], "admin_login", "user", str(user["id"]), "Admin paneliga kirildi", client_ip)

        return {
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"]
            }
        }
    finally:
        conn.close()

@app.get("/api/admin/stats")
def get_admin_dashboard_stats(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        total_buses = conn.execute("SELECT COUNT(*) FROM buses WHERE is_deleted = 0").fetchone()[0]
        total_routes = conn.execute("SELECT COUNT(*) FROM routes WHERE is_deleted = 0").fetchone()[0]
        total_stops = conn.execute("SELECT COUNT(*) FROM stops WHERE is_deleted = 0").fetchone()[0]
        
        active_trips_count = conn.execute("SELECT COUNT(*) FROM trips WHERE status = 'active'").fetchone()[0]

        # GPS active buses (updated in last 120s)
        active_buses = conn.execute("""
            SELECT b.id, b.plate_number, b.bus_name, b.model,
                   r.id as route_id, r.route_number, r.name as route_name,
                   u.full_name as driver_name,
                   t.id as trip_id, t.start_time,
                   g.latitude, g.longitude, g.speed, g.timestamp as last_gps_time
            FROM buses b
            LEFT JOIN routes r ON r.bus_id = b.id AND r.is_deleted = 0
            LEFT JOIN users u ON r.driver_id = u.id
            LEFT JOIN trips t ON t.bus_id = b.id AND t.status = 'active'
            LEFT JOIN (
                SELECT trip_id, latitude, longitude, speed, timestamp
                FROM gps_positions
                WHERE id IN (SELECT MAX(id) FROM gps_positions GROUP BY trip_id)
            ) g ON g.trip_id = t.id
            WHERE b.is_deleted = 0
        """).fetchall()

        gps_connected_count = 0
        gps_disconnected_count = 0
        buses_list = []

        now = datetime.utcnow()
        for b in active_buses:
            b_dict = dict(b)
            if b_dict["trip_id"]:
                if b_dict["last_gps_time"]:
                    try:
                        g_time = datetime.fromisoformat(str(b_dict["last_gps_time"]).replace(" ", "T"))
                        diff_sec = (now - g_time).total_seconds()
                        if diff_sec <= GPS_STALE_THRESHOLD_SECONDS:
                            b_dict["gps_status"] = "active"
                            gps_connected_count += 1
                        else:
                            b_dict["gps_status"] = "stale"
                            gps_disconnected_count += 1
                    except Exception:
                        b_dict["gps_status"] = "stale"
                        gps_disconnected_count += 1
                else:
                    b_dict["gps_status"] = "no_data"
                    gps_disconnected_count += 1
            else:
                b_dict["gps_status"] = "idle"

            buses_list.append(b_dict)

        # Today's trips
        today_str = date.today().isoformat()
        today_trips_count = conn.execute("""
            SELECT COUNT(*) FROM trips
            WHERE date(start_time) = date('now')
        """).fetchone()[0]

        # Telegram stats
        tg_sent = conn.execute("SELECT COUNT(*) FROM notification_jobs WHERE status = 'sent'").fetchone()[0]
        tg_failed = conn.execute("SELECT COUNT(*) FROM notification_jobs WHERE status = 'failed'").fetchone()[0]

        return {
            "total_buses": total_buses,
            "total_routes": total_routes,
            "total_stops": total_stops,
            "active_trips_count": active_trips_count,
            "gps_connected_count": gps_connected_count,
            "gps_disconnected_count": gps_disconnected_count,
            "today_trips_count": today_trips_count,
            "telegram_sent": tg_sent,
            "telegram_failed": tg_failed,
            "buses": buses_list
        }
    finally:
        conn.close()

# --- BUSES MANAGEMENT ---

@app.get("/api/admin/buses")
def admin_get_buses(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        buses = conn.execute("""
            SELECT b.*, r.id as route_id, r.name as route_name, r.route_number,
                   u.full_name as driver_name
            FROM buses b
            LEFT JOIN routes r ON r.bus_id = b.id AND r.is_deleted = 0
            LEFT JOIN users u ON r.driver_id = u.id
            WHERE b.is_deleted = 0
            ORDER BY b.id ASC
        """).fetchall()
        return {"buses": [dict(b) for b in buses]}
    finally:
        conn.close()

@app.post("/api/admin/buses")
def admin_create_bus(payload: BusCreateRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        # Check duplicate plate number
        existing = cur.execute("SELECT id, is_deleted FROM buses WHERE plate_number = ?", (payload.plate_number.strip(),)).fetchone()
        if existing:
            if existing["is_deleted"] == 0:
                raise HTTPException(status_code=400, detail="Ushbu davlat raqamli avtobus allaqachon mavjud")
            else:
                # Re-activate and update existing record
                cur.execute("""
                    UPDATE buses
                    SET bus_name = ?, capacity = ?, model = ?, is_active = 1, is_deleted = 0, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (payload.bus_name.strip(), payload.capacity, payload.model.strip(), existing["id"]))
                bus_id = existing["id"]
        else:
            cur.execute("""
                INSERT INTO buses (plate_number, bus_name, capacity, model, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (payload.plate_number.strip(), payload.bus_name.strip(), payload.capacity, payload.model.strip()))
            bus_id = cur.lastrowid

    log_audit(admin["id"], admin["username"], "create_bus", "bus", str(bus_id), f"Avtobus qo'shildi: {payload.bus_name} ({payload.plate_number})")
    return {"success": True, "bus_id": bus_id, "message": "Avtobus muvaffaqiyatli qo'shildi"}

@app.put("/api/admin/buses/{bus_id}")
def admin_update_bus(bus_id: int, payload: BusUpdateRequest, admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        bus = conn.execute("SELECT * FROM buses WHERE id = ? AND is_deleted = 0", (bus_id,)).fetchone()
        if not bus:
            raise HTTPException(status_code=404, detail="Avtobus topilmadi")

        updates = []
        params = []
        if payload.plate_number is not None:
            updates.append("plate_number = ?")
            params.append(payload.plate_number.strip())
        if payload.bus_name is not None:
            updates.append("bus_name = ?")
            params.append(payload.bus_name.strip())
        if payload.capacity is not None:
            updates.append("capacity = ?")
            params.append(payload.capacity)
        if payload.model is not None:
            updates.append("model = ?")
            params.append(payload.model.strip())
        if payload.is_active is not None:
            updates.append("is_active = ?")
            params.append(payload.is_active)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(bus_id)
            with get_db_cursor() as cur:
                cur.execute(f"UPDATE buses SET {', '.join(updates)} WHERE id = ?", params)

        log_audit(admin["id"], admin["username"], "update_bus", "bus", str(bus_id), "Avtobus ma'lumotlari tahrirlandi")
        return {"success": True, "message": "Avtobus ma'lumotlari yangilandi"}
    finally:
        conn.close()

@app.delete("/api/admin/buses/{bus_id}")
def admin_delete_bus(bus_id: int, admin: dict = Depends(require_admin)):
    # Soft delete to preserve historical trips and GPS records
    with get_db_cursor() as cur:
        cur.execute("UPDATE buses SET is_deleted = 1, is_active = 0 WHERE id = ?", (bus_id,))
        cur.execute("UPDATE routes SET bus_id = NULL WHERE bus_id = ?", (bus_id,))

    log_audit(admin["id"], admin["username"], "delete_bus", "bus", str(bus_id), "Avtobus xavfsiz o'chirildi (soft-delete)")
    return {"success": True, "message": "Avtobus tizimdan o'chirildi (tarix saqlab qolindi)"}

@app.get("/api/admin/buses/{bus_id}/history")
def admin_get_bus_history(bus_id: int, admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        trips = conn.execute("""
            SELECT t.*, r.name as route_name, r.route_number, u.full_name as driver_name
            FROM trips t
            JOIN routes r ON t.route_id = r.id
            JOIN users u ON t.driver_id = u.id
            WHERE t.bus_id = ?
            ORDER BY t.id DESC LIMIT 30
        """, (bus_id,)).fetchall()
        return {"trips": [dict(t) for t in trips]}
    finally:
        conn.close()

# --- ROUTES MANAGEMENT ---

@app.get("/api/admin/routes")
def admin_get_routes(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        routes = conn.execute("""
            SELECT r.*, b.bus_name, b.plate_number,
                   u.full_name as driver_name, u.username as driver_username,
                   (SELECT COUNT(*) FROM route_stops rs JOIN stops s ON rs.stop_id = s.id WHERE rs.route_id = r.id AND s.is_deleted = 0) as stops_count
            FROM routes r
            LEFT JOIN buses b ON r.bus_id = b.id
            LEFT JOIN users u ON r.driver_id = u.id
            WHERE r.is_deleted = 0
            ORDER BY r.id ASC
        """).fetchall()
        return {"routes": [dict(r) for r in routes]}
    finally:
        conn.close()

@app.post("/api/admin/routes")
def admin_create_route(payload: RouteCreateRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO routes (route_number, name, description, bus_id, driver_id, telegram_chat_id, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (payload.route_number.strip(), payload.name.strip(), payload.description, payload.bus_id, payload.driver_id, payload.telegram_chat_id))
        route_id = cur.lastrowid

    log_audit(admin["id"], admin["username"], "create_route", "route", str(route_id), f"Yangi yo'nalish: {payload.name}")
    return {"success": True, "route_id": route_id, "message": "Yo'nalish yaratildi"}

@app.put("/api/admin/routes/{route_id}")
def admin_update_route(route_id: int, payload: RouteUpdateRequest, admin: dict = Depends(require_admin)):
    updates = []
    params = []
    if payload.route_number is not None:
        updates.append("route_number = ?")
        params.append(payload.route_number.strip())
    if payload.name is not None:
        updates.append("name = ?")
        params.append(payload.name.strip())
    if payload.description is not None:
        updates.append("description = ?")
        params.append(payload.description)
    if payload.bus_id is not None:
        updates.append("bus_id = ?")
        params.append(payload.bus_id if payload.bus_id != 0 else None)
    if payload.driver_id is not None:
        updates.append("driver_id = ?")
        params.append(payload.driver_id if payload.driver_id != 0 else None)
    if payload.telegram_chat_id is not None:
        updates.append("telegram_chat_id = ?")
        params.append(payload.telegram_chat_id.strip())
    if payload.is_active is not None:
        updates.append("is_active = ?")
        params.append(payload.is_active)

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(route_id)
        with get_db_cursor() as cur:
            cur.execute(f"UPDATE routes SET {', '.join(updates)} WHERE id = ?", params)

    log_audit(admin["id"], admin["username"], "update_route", "route", str(route_id), "Yo'nalish sozlamalari yangilandi")
    return {"success": True, "message": "Yo'nalish yangilandi"}

@app.delete("/api/admin/routes/{route_id}")
def admin_delete_route(route_id: int, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        cur.execute("UPDATE routes SET is_deleted = 1, is_active = 0 WHERE id = ?", (route_id,))
    log_audit(admin["id"], admin["username"], "delete_route", "route", str(route_id), "Yo'nalish o'chirildi")
    return {"success": True, "message": "Yo'nalish tizimdan o'chirildi"}

@app.get("/api/admin/routes/{route_id}/stops")
def admin_get_route_stops(route_id: int, admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        stops = conn.execute("""
            SELECT rs.id as route_stop_id, rs.stop_order, rs.estimated_minutes,
                   s.id as stop_id, s.name, s.latitude, s.longitude, s.default_geofence_radius, s.is_active
            FROM route_stops rs
            JOIN stops s ON rs.stop_id = s.id
            WHERE rs.route_id = ? AND s.is_deleted = 0
            ORDER BY rs.stop_order ASC
        """, (route_id,)).fetchall()
        return {"stops": [dict(s) for s in stops]}
    finally:
        conn.close()

@app.post("/api/admin/routes/{route_id}/stops")
def admin_add_route_stop(route_id: int, payload: RouteStopAddRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        # Check duplicate stop in route
        cur.execute("SELECT 1 FROM route_stops WHERE route_id = ? AND stop_id = ?", (route_id, payload.stop_id))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Bu bekat allaqachon ushbu yo'nalishga qo'shilgan")

        cur.execute("""
            INSERT INTO route_stops (route_id, stop_id, stop_order, estimated_minutes)
            VALUES (?, ?, ?, ?)
        """, (route_id, payload.stop_id, payload.stop_order, payload.estimated_minutes))

    log_audit(admin["id"], admin["username"], "add_route_stop", "route", str(route_id), f"Bekat #{payload.stop_id} qo'shildi")
    return {"success": True, "message": "Bekat yo'nalishga biriktirildi"}

@app.put("/api/admin/routes/{route_id}/stops/reorder")
def admin_reorder_route_stops(route_id: int, payload: RouteStopReorderRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        for item in payload.stop_orders:
            cur.execute("""
                UPDATE route_stops
                SET stop_order = ?
                WHERE route_id = ? AND stop_id = ?
            """, (item["order"], route_id, item["stop_id"]))

    log_audit(admin["id"], admin["username"], "reorder_route_stops", "route", str(route_id), "Bekatlar tartibi yangilandi")
    return {"success": True, "message": "Bekatlar tartibi muvaffaqiyatli yangilandi"}

@app.delete("/api/admin/routes/{route_id}/stops/{stop_id}")
def admin_remove_route_stop(route_id: int, stop_id: int, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        cur.execute("DELETE FROM route_stops WHERE route_id = ? AND stop_id = ?", (route_id, stop_id))
    log_audit(admin["id"], admin["username"], "remove_route_stop", "route", str(route_id), f"Bekat #{stop_id} yo'nalishdan olib tashlandi")
    return {"success": True, "message": "Bekat yo'nalishdan chiqarildi"}

# --- STOPS MANAGEMENT ---

@app.get("/api/admin/stops")
def admin_get_all_stops(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        stops = conn.execute("""
            SELECT s.*,
                   (SELECT COUNT(*) FROM route_stops rs WHERE rs.stop_id = s.id) as routes_count
            FROM stops s
            WHERE s.is_deleted = 0
            ORDER BY s.id DESC
        """).fetchall()
        return {"stops": [dict(s) for s in stops]}
    finally:
        conn.close()

@app.post("/api/admin/stops")
def admin_create_stop(payload: StopCreateRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO stops (name, latitude, longitude, default_geofence_radius, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (payload.name.strip(), payload.latitude, payload.longitude, payload.default_geofence_radius))
        stop_id = cur.lastrowid

    log_audit(admin["id"], admin["username"], "create_stop", "stop", str(stop_id), f"Yangi bekat: {payload.name}")
    return {"success": True, "stop_id": stop_id, "message": "Bekat muvaffaqiyatli saqlandi"}

@app.put("/api/admin/stops/{stop_id}")
def admin_update_stop(stop_id: int, payload: StopUpdateRequest, admin: dict = Depends(require_admin)):
    updates = []
    params = []
    if payload.name is not None:
        updates.append("name = ?")
        params.append(payload.name.strip())
    if payload.latitude is not None:
        updates.append("latitude = ?")
        params.append(payload.latitude)
    if payload.longitude is not None:
        updates.append("longitude = ?")
        params.append(payload.longitude)
    if payload.default_geofence_radius is not None:
        updates.append("default_geofence_radius = ?")
        params.append(payload.default_geofence_radius)
    if payload.is_active is not None:
        updates.append("is_active = ?")
        params.append(payload.is_active)

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(stop_id)
        with get_db_cursor() as cur:
            cur.execute(f"UPDATE stops SET {', '.join(updates)} WHERE id = ?", params)

    log_audit(admin["id"], admin["username"], "update_stop", "stop", str(stop_id), "Bekat koordinatalari/nomi yangilandi")
    return {"success": True, "message": "Bekat ma'lumotlari yangilandi"}

@app.delete("/api/admin/stops/{stop_id}")
def admin_delete_stop(stop_id: int, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        cur.execute("UPDATE stops SET is_deleted = 1, is_active = 0 WHERE id = ?", (stop_id,))
        cur.execute("DELETE FROM route_stops WHERE stop_id = ?", (stop_id,))

    log_audit(admin["id"], admin["username"], "delete_stop", "stop", str(stop_id), "Bekat tizimdan o'chirildi")
    return {"success": True, "message": "Bekat o'chirildi"}

# --- DRIVERS & ACCOUNTS MANAGEMENT ---

@app.get("/api/admin/drivers")
def admin_get_drivers(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        drivers = conn.execute("""
            SELECT u.id, u.username, u.full_name, u.phone, u.role, u.is_active, u.last_login, u.created_at,
                   r.id as assigned_route_id, r.name as assigned_route_name, r.route_number,
                   b.id as assigned_bus_id, b.bus_name as assigned_bus_name, b.plate_number
            FROM users u
            LEFT JOIN routes r ON r.driver_id = u.id AND r.is_deleted = 0
            LEFT JOIN buses b ON r.bus_id = b.id
            WHERE u.role = 'driver'
            ORDER BY u.id ASC
        """).fetchall()
        return {"drivers": [dict(d) for d in drivers]}
    finally:
        conn.close()

@app.post("/api/admin/drivers")
def admin_create_driver(payload: DriverCreateRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        cur.execute("SELECT 1 FROM users WHERE username = ?", (payload.username.strip(),))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Ushbu login band")

        p_hash = hash_password(payload.password)
        cur.execute("""
            INSERT INTO users (username, password_hash, role, full_name, phone, is_active)
            VALUES (?, ?, 'driver', ?, ?, 1)
        """, (payload.username.strip(), p_hash, payload.full_name.strip(), payload.phone.strip()))
        driver_id = cur.lastrowid

        # Bind route if given
        if payload.route_id:
            cur.execute("UPDATE routes SET driver_id = ? WHERE id = ?", (driver_id, payload.route_id))
            if payload.bus_id:
                cur.execute("UPDATE routes SET bus_id = ? WHERE id = ?", (payload.bus_id, payload.route_id))

    log_audit(admin["id"], admin["username"], "create_driver", "user", str(driver_id), f"Yangi haydovchi: {payload.full_name} ({payload.username})")
    return {"success": True, "driver_id": driver_id, "message": "Haydovchi hisobi yaratildi"}

@app.put("/api/admin/drivers/{driver_id}")
def admin_update_driver(driver_id: int, payload: DriverUpdateRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        updates = []
        params = []
        if payload.full_name is not None:
            updates.append("full_name = ?")
            params.append(payload.full_name.strip())
        if payload.phone is not None:
            updates.append("phone = ?")
            params.append(payload.phone.strip())
        if payload.is_active is not None:
            updates.append("is_active = ?")
            params.append(payload.is_active)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(driver_id)
            cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)

        if payload.route_id is not None:
            # Clear old route assignment
            cur.execute("UPDATE routes SET driver_id = NULL WHERE driver_id = ?", (driver_id,))
            if payload.route_id > 0:
                cur.execute("UPDATE routes SET driver_id = ? WHERE id = ?", (driver_id, payload.route_id))
                if payload.bus_id and payload.bus_id > 0:
                    cur.execute("UPDATE routes SET bus_id = ? WHERE id = ?", (payload.bus_id, payload.route_id))

    log_audit(admin["id"], admin["username"], "update_driver", "user", str(driver_id), "Haydovchi ma'lumotlari yangilandi")
    return {"success": True, "message": "Haydovchi ma'lumotlari yangilandi"}

@app.post("/api/admin/drivers/{driver_id}/reset-password")
def admin_reset_driver_password(driver_id: int, payload: PasswordResetRequest, admin: dict = Depends(require_admin)):
    new_hash = hash_password(payload.new_password)
    with get_db_cursor() as cur:
        cur.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_hash, driver_id))

    log_audit(admin["id"], admin["username"], "reset_password", "user", str(driver_id), "Haydovchi paroli xavfsiz yangilandi (bcrypt)")
    return {"success": True, "message": "Parol muvaffaqiyatli o'zgartirildi"}

# --- TELEGRAM SETTINGS & LOGS ---

@app.get("/api/admin/telegram/settings")
def admin_get_telegram_settings(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        token_row = conn.execute("SELECT value FROM system_settings WHERE key = 'telegram_bot_token'").fetchone()
        chat_row = conn.execute("SELECT value FROM system_settings WHERE key = 'telegram_default_chat_id'").fetchone()
        
        bot_token = token_row["value"] if token_row else TELEGRAM_BOT_TOKEN
        chat_id = chat_row["value"] if chat_row else DEFAULT_TELEGRAM_CHAT_ID

        # Mask token for security
        masked = bot_token[:8] + "..." + bot_token[-6:] if len(bot_token) > 14 else ("O'rnatilgan" if bot_token else "Kiritilmagan")

        return {
            "has_token": bool(bot_token),
            "masked_token": masked,
            "default_chat_id": chat_id
        }
    finally:
        conn.close()

@app.post("/api/admin/telegram/settings")
def admin_save_telegram_settings(payload: TelegramSettingsRequest, admin: dict = Depends(require_admin)):
    with get_db_cursor() as cur:
        cur.execute("INSERT OR REPLACE INTO system_settings (key, value, description) VALUES ('telegram_bot_token', ?, 'Telegram Bot Token')", (payload.bot_token.strip(),))
        cur.execute("INSERT OR REPLACE INTO system_settings (key, value, description) VALUES ('telegram_default_chat_id', ?, 'Telegram Default Chat ID')", (payload.default_chat_id.strip(),))

    log_audit(admin["id"], admin["username"], "update_telegram", "system", "telegram", "Telegram bot sozlamalari yangilandi")
    return {"success": True, "message": "Telegram sozlamalari saqlandi"}

@app.post("/api/admin/telegram/test")
async def admin_test_telegram(payload: TelegramTestRequest, admin: dict = Depends(require_admin)):
    msg = payload.message or (
        "🔔 <b>TEST BILDIRISHNOMA</b>\n\n"
        "Smart School Bus tizimidan sinov xabari muvaffaqiyatli yetib bordi!\n"
        f"Vaqt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    ok, err = await send_telegram_message(payload.chat_id, msg)
    if not ok:
        raise HTTPException(status_code=400, detail=f"Telegram xatosi: {err}")
    return {"success": True, "message": "Sinov xabari Telegramga muvaffaqiyatli yuborildi"}

@app.get("/api/admin/telegram/logs")
def admin_get_telegram_logs(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        logs = conn.execute("""
            SELECT nj.*, r.name as route_name, s.name as stop_name
            FROM notification_jobs nj
            LEFT JOIN trips t ON nj.trip_id = t.id
            LEFT JOIN routes r ON t.route_id = r.id
            LEFT JOIN stops s ON nj.stop_id = s.id
            ORDER BY nj.id DESC LIMIT 50
        """).fetchall()
        return {"logs": [dict(l) for l in logs]}
    finally:
        conn.close()

# --- TRIPS & AUDIT LOGS ---

@app.get("/api/admin/trips")
def admin_get_trips(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        trips = conn.execute("""
            SELECT t.*, r.name as route_name, r.route_number,
                   b.bus_name, b.plate_number,
                   u.full_name as driver_name,
                   (SELECT COUNT(*) FROM stop_arrivals WHERE trip_id = t.id) as arrived_stops_count
            FROM trips t
            JOIN routes r ON t.route_id = r.id
            JOIN buses b ON t.bus_id = b.id
            JOIN users u ON t.driver_id = u.id
            ORDER BY t.id DESC LIMIT 50
        """).fetchall()
        return {"trips": [dict(t) for t in trips]}
    finally:
        conn.close()

@app.get("/api/admin/audit-logs")
def admin_get_audit_logs(admin: dict = Depends(require_admin)):
    conn = get_db()
    try:
        logs = conn.execute("""
            SELECT * FROM audit_logs
            ORDER BY id DESC LIMIT 100
        """).fetchall()
        return {"logs": [dict(l) for l in logs]}
    finally:
        conn.close()

# --- STATIC FILES & SPA SERVING ---

os.makedirs(BASE_DIR / "static", exist_ok=True)
os.makedirs(BASE_DIR / "static" / "css", exist_ok=True)
os.makedirs(BASE_DIR / "static" / "js", exist_ok=True)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/")
def serve_index():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/parent")
def serve_parent():
    return FileResponse(BASE_DIR / "static" / "parent.html")

@app.get("/driver")
def serve_driver():
    return FileResponse(BASE_DIR / "static" / "driver.html")

@app.get("/admin")
def serve_admin():
    return FileResponse(BASE_DIR / "static" / "admin.html")
