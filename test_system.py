import os
from starlette.testclient import TestClient
from main import app
from database import get_db, init_db
from seed_data import seed_database

# Ensure database is initialized & seeded
seed_database()

# Reset test users to known passwords and complete leftover trips for idempotent testing
from auth import hash_password
with get_db() as _conn:
    _conn.execute("UPDATE users SET password_hash = ? WHERE username = 'haydovchi1'", (hash_password("Haydovchi2026!"),))
    _conn.execute("UPDATE users SET password_hash = ? WHERE username = 'haydovchi2'", (hash_password("Haydovchi2026!"),))
    _conn.execute("UPDATE trips SET status = 'completed' WHERE status = 'active'")
    _conn.commit()

client = TestClient(app)

def test_full_system_flow():
    print("\n--- TEST 1: Admin Login ---")
    res = client.post("/api/admin/login", json={"username": "admin", "password": "Admin2026!"})
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    admin_token = res.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print("Admin login success. Token obtained.")

    print("\n--- TEST 2: Admin Dashboard Stats ---")
    res = client.get("/api/admin/stats", headers=admin_headers)
    assert res.status_code == 200
    stats = res.json()
    assert stats["total_buses"] >= 11
    assert stats["total_routes"] >= 11
    assert stats["total_stops"] >= 55
    print(f"Stats verified: {stats['total_buses']} buses, {stats['total_routes']} routes, {stats['total_stops']} stops.")

    print("\n--- TEST 3: Admin Add & Soft-Delete Bus ---")
    res = client.post("/api/admin/buses", json={
        "plate_number": "01 | 999 TST",
        "bus_name": "Sinov Avtobusi",
        "capacity": 30,
        "model": "Isuzu NP 37"
    }, headers=admin_headers)
    assert res.status_code == 200
    new_bus_id = res.json()["bus_id"]
    print(f"Bus created: ID #{new_bus_id}")

    # Soft delete
    res = client.delete(f"/api/admin/buses/{new_bus_id}", headers=admin_headers)
    assert res.status_code == 200
    print("Bus soft-deleted successfully (history preserved).")

    print("\n--- TEST 4: Driver 1 Login & Route Isolation ---")
    res = client.post("/api/driver/login", json={"username": "haydovchi1", "password": "Haydovchi2026!"})
    assert res.status_code == 200
    driver1_token = res.json()["token"]
    driver1_headers = {"Authorization": f"Bearer {driver1_token}"}
    driver1_user = res.json()["user"]
    print(f"Driver 1 login success: {driver1_user['full_name']}")

    # Get Driver's assigned route
    res = client.get("/api/driver/my-route", headers=driver1_headers)
    assert res.status_code == 200
    d_data = res.json()
    assert d_data["route"] is not None
    assert d_data["route"]["route_number"] == "1-yo‘nalish"
    assert len(d_data["stops"]) >= 4
    first_stop = d_data["stops"][0]
    second_stop = d_data["stops"][1]
    print(f"Driver 1 isolated to route: '{d_data['route']['name']}' with {len(d_data['stops'])} stops.")

    print("\n--- TEST 5: Driver Starts Trip ---")
    res = client.post("/api/driver/trip/start", headers=driver1_headers)
    assert res.status_code == 200
    trip = res.json()["trip"]
    trip_id = trip["id"]
    print(f"Trip started with ID #{trip_id}")

    print("\n--- TEST 6: GPS Geofencing Arrival Detection ---")
    # Send GPS coordinates matching first stop location
    res = client.post("/api/driver/trip/gps", json={
        "trip_id": trip_id,
        "latitude": first_stop["latitude"],
        "longitude": first_stop["longitude"],
        "speed": 30.0,
        "heading": 45.0,
        "accuracy": 5.0
    }, headers=driver1_headers)
    assert res.status_code == 200
    gps_res = res.json()
    assert gps_res["arrival_triggered"] is True
    assert gps_res["arrived_stop_name"] == first_stop["name"]
    print(f"Geofence arrival successfully triggered: '{gps_res['arrived_stop_name']}'")

    print("\n--- TEST 7: Deduplication Prevention ---")
    # Send same GPS again - should NOT trigger duplicate arrival!
    res = client.post("/api/driver/trip/gps", json={
        "trip_id": trip_id,
        "latitude": first_stop["latitude"],
        "longitude": first_stop["longitude"],
        "speed": 30.0,
        "heading": 45.0,
        "accuracy": 5.0
    }, headers=driver1_headers)
    assert res.status_code == 200
    gps_res2 = res.json()
    assert gps_res2["arrival_triggered"] is False
    print("Deduplication confirmed: No duplicate arrival was sent.")

    print("\n--- TEST 8: Public Parent Route Tracking ---")
    res = client.get(f"/api/public/routes/{d_data['route']['id']}")
    assert res.status_code == 200
    p_data = res.json()
    assert p_data["trip"] is not None
    assert p_data["trip"]["status"] == "active"
    assert first_stop["id"] in p_data["visited_stop_ids"]
    assert p_data["latest_gps"] is not None
    print("Parent live tracking verified: Bus is live, visited stop marked, coordinates live.")

    print("\n--- TEST 9: Driver Ends Trip ---")
    res = client.post("/api/driver/trip/end", headers=driver1_headers)
    assert res.status_code == 200
    print("Trip ended successfully.")

    print("\n--- TEST 10: Admin Password Reset with Bcrypt ---")
    conn = get_db()
    d2_id = conn.execute("SELECT id FROM users WHERE username = 'haydovchi2'").fetchone()[0]
    conn.close()

    # Reset driver 2 password
    res = client.post(f"/api/admin/drivers/{d2_id}/reset-password", json={
        "new_password": "NewSecret2026!"
    }, headers=admin_headers)
    assert res.status_code == 200

    # Old password must fail
    res = client.post("/api/driver/login", json={"username": "haydovchi2", "password": "Haydovchi2026!"})
    assert res.status_code == 401

    # New password must succeed
    res = client.post("/api/driver/login", json={"username": "haydovchi2", "password": "NewSecret2026!"})
    assert res.status_code == 200
    print("Bcrypt password reset verified: Old password rejected, new password authenticated.")

    print("\n--- TEST 11: Audit Logs Verification ---")
    res = client.get("/api/admin/audit-logs", headers=admin_headers)
    assert res.status_code == 200
    logs = res.json()["logs"]
    assert len(logs) > 0
    print(f"Audit logs verified: {len(logs)} actions securely logged.")

    print("\n==========================================")
    print("ALL 11 INTEGRATION TESTS PASSED WITH 100% SUCCESS!")
    print("==========================================")

if __name__ == "__main__":
    test_full_system_flow()
