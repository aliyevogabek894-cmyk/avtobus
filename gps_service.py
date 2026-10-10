import math
import logging
from datetime import datetime
from database import get_db, get_db_cursor
from telegram_service import send_telegram_message, format_arrival_message

logger = logging.getLogger("gps_service")

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth in meters.
    """
    R = 6371000.0  # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c

async def process_driver_gps(
    trip_id: int,
    driver_id: int,
    latitude: float,
    longitude: float,
    speed: float = 0.0,
    heading: float = 0.0,
    accuracy: float = 10.0
) -> dict:
    conn = get_db()
    try:
        # Validate active trip and driver ownership
        trip = conn.execute("""
            SELECT t.*, r.name as route_name, r.route_number, r.telegram_chat_id,
                   b.bus_name, b.plate_number
            FROM trips t
            JOIN routes r ON t.route_id = r.id
            JOIN buses b ON t.bus_id = b.id
            WHERE t.id = ? AND t.status = 'active'
        """, (trip_id,)).fetchone()

        if not trip:
            return {"error": "Faol safar topilmadi yoki yakunlangan"}

        if trip["driver_id"] != driver_id:
            return {"error": "Siz bu safarga biriktirilmagansiz"}

        bus_id = trip["bus_id"]
        route_id = trip["route_id"]

        # Record GPS position
        with get_db_cursor() as cur:
            cur.execute("""
                INSERT INTO gps_positions (trip_id, bus_id, latitude, longitude, speed, heading, accuracy)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (trip_id, bus_id, latitude, longitude, speed, heading, accuracy))

        # Get route stops in sequence
        stops_rows = conn.execute("""
            SELECT rs.stop_order, rs.estimated_minutes, s.id as stop_id, s.name as stop_name,
                   s.latitude, s.longitude, s.default_geofence_radius
            FROM route_stops rs
            JOIN stops s ON rs.stop_id = s.id
            WHERE rs.route_id = ? AND s.is_deleted = 0
            ORDER BY rs.stop_order ASC
        """, (route_id,)).fetchall()

        if not stops_rows:
            return {
                "success": True,
                "message": "Yo'nalishda bekatlar mavjud emas",
                "next_stop": None,
                "distance_to_next": None
            }

        next_order = trip["next_stop_order"] or 1
        
        # Find current target stop
        target_stop = None
        for s in stops_rows:
            if s["stop_order"] >= next_order:
                target_stop = s
                break

        arrival_triggered = False
        arrived_stop_name = None
        distance_to_target = None

        if target_stop:
            dist = haversine_distance(latitude, longitude, target_stop["latitude"], target_stop["longitude"])
            distance_to_target = round(dist, 1)
            radius = target_stop["default_geofence_radius"] or 100

            # If within geofence radius
            if dist <= radius:
                stop_id = target_stop["stop_id"]
                # Deduplication check: Has this stop been reached in this trip?
                existing = conn.execute("""
                    SELECT 1 FROM stop_arrivals WHERE trip_id = ? AND stop_id = ?
                """, (trip_id, stop_id)).fetchone()

                if not existing:
                    now_str = datetime.now().strftime("%H:%M")
                    with get_db_cursor() as cur:
                        cur.execute("""
                            INSERT INTO stop_arrivals (trip_id, stop_id, arrived_at, telegram_sent)
                            VALUES (?, ?, CURRENT_TIMESTAMP, 1)
                        """, (trip_id, stop_id))

                        # Advance next stop order
                        new_next_order = target_stop["stop_order"] + 1
                        
                        # Find the subsequent stop ID if any
                        subsequent_stop_id = None
                        for s in stops_rows:
                            if s["stop_order"] == new_next_order:
                                subsequent_stop_id = s["stop_id"]
                                break

                        cur.execute("""
                            UPDATE trips
                            SET current_stop_id = ?, next_stop_id = ?, next_stop_order = ?
                            WHERE id = ?
                        """, (stop_id, subsequent_stop_id, new_next_order, trip_id))

                    arrival_triggered = True
                    arrived_stop_name = target_stop["stop_name"]

                    # Format & send telegram message asynchronously
                    tg_text = format_arrival_message(
                        route_name=trip["route_name"],
                        bus_name=f"{trip['bus_name']} ({trip['plate_number']})",
                        stop_name=target_stop["stop_name"],
                        time_str=now_str
                    )
                    await send_telegram_message(
                        chat_id=trip["telegram_chat_id"],
                        message_text=tg_text,
                        trip_id=trip_id,
                        stop_id=stop_id
                    )

        # Re-fetch next stop info for frontend response
        refetched_trip = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
        current_next_order = refetched_trip["next_stop_order"] if refetched_trip else next_order
        next_target = None
        for s in stops_rows:
            if s["stop_order"] >= current_next_order:
                next_target = {
                    "id": s["stop_id"],
                    "name": s["stop_name"],
                    "order": s["stop_order"],
                    "lat": s["latitude"],
                    "lng": s["longitude"],
                    "distance_meters": round(haversine_distance(latitude, longitude, s["latitude"], s["longitude"]), 1)
                }
                break

        return {
            "success": True,
            "trip_id": trip_id,
            "status": "active",
            "arrival_triggered": arrival_triggered,
            "arrived_stop_name": arrived_stop_name,
            "next_stop": next_target,
            "distance_to_next": next_target["distance_meters"] if next_target else None
        }

    finally:
        conn.close()
