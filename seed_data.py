import os
import sqlite3
from database import get_db, get_db_cursor, init_db
from auth import hash_password

def seed_database():
    init_db()

    with get_db_cursor() as cur:
        # Check if already seeded with Fergana (check a route name)
        chk = cur.execute("SELECT name FROM routes WHERE name LIKE '%Qirguli%'").fetchone()
        if chk:
            print("Database already seeded with Fergana routes.")
            return

        print("Seeding/updating database with Farg'ona routes and coordinates...")

        # Clear old mock data to cleanly switch to Fergana
        cur.execute("DELETE FROM stop_arrivals")
        cur.execute("DELETE FROM gps_positions")
        cur.execute("DELETE FROM notification_jobs")
        cur.execute("DELETE FROM trips")
        cur.execute("DELETE FROM route_stops")
        cur.execute("DELETE FROM stops")
        cur.execute("DELETE FROM routes")
        cur.execute("DELETE FROM buses")
        cur.execute("DELETE FROM users")

        # 1. Admin user
        admin_pass = hash_password("Admin2026!")
        cur.execute("""
            INSERT INTO users (id, username, password_hash, role, full_name, phone, is_active)
            VALUES (1, 'admin', ?, 'admin', 'Bosh Administrator', '+998901234567', 1)
        """, (admin_pass,))

        # 2. Driver accounts (11 drivers)
        driver_names = [
            ("haydovchi1", "Rustam Karimov (Farg'ona)", "+998901112201"),
            ("haydovchi2", "Jasur Aliyev (Farg'ona)", "+998901112202"),
            ("haydovchi3", "Otabek Norov (Farg'ona)", "+998901112203"),
            ("haydovchi4", "Sherzod Qosimov (Farg'ona)", "+998901112204"),
            ("haydovchi5", "Bahrom Saidov (Farg'ona)", "+998901112205"),
            ("haydovchi6", "Dilshod Rahimov (Farg'ona)", "+998901112206"),
            ("haydovchi7", "Farrux Tursunov (Farg'ona)", "+998901112207"),
            ("haydovchi8", "Mansur Jalilov (Farg'ona)", "+998901112208"),
            ("haydovchi9", "Azamat Vohidov (Farg'ona)", "+998901112209"),
            ("haydovchi10", "Sanjar Umarov (Farg'ona)", "+998901112210"),
            ("haydovchi11", "Ilhom Yusupov (Farg'ona)", "+998901112211"),
        ]
        driver_pass = hash_password("Haydovchi2026!")
        driver_ids = {}
        for username, name, phone in driver_names:
            cur.execute("""
                INSERT INTO users (username, password_hash, role, full_name, phone, is_active)
                VALUES (?, ?, 'driver', ?, ?, 1)
            """, (username, driver_pass, name, phone))
            driver_ids[username] = cur.lastrowid

        # 3. Buses (11 buses) with Fergana plates 40 | ...
        buses_data = [
            ("40 | 701 SAA", "Avtobus 01", 32, "Isuzu SAZ NP 37"),
            ("40 | 702 SAA", "Avtobus 02", 32, "Isuzu SAZ NP 37"),
            ("40 | 703 SAA", "Avtobus 03", 35, "Yutong ZK6890HG"),
            ("40 | 704 SAA", "Avtobus 04", 32, "Isuzu SAZ NP 37"),
            ("40 | 705 SAA", "Avtobus 05", 35, "Yutong ZK6890HG"),
            ("40 | 706 SAA", "Avtobus 06", 32, "Isuzu SAZ NP 37"),
            ("40 | 707 SAA", "Avtobus 07", 32, "Isuzu SAZ NP 37"),
            ("40 | 708 SAA", "Avtobus 08", 35, "Yutong ZK6890HG"),
            ("40 | 709 SAA", "Avtobus 09", 32, "Isuzu SAZ NP 37"),
            ("40 | 710 SAA", "Avtobus 10", 35, "Yutong ZK6890HG"),
            ("40 | 711 SAA", "Avtobus 11", 32, "Isuzu SAZ NP 37"),
        ]
        bus_ids = []
        for plate, name, cap, model in buses_data:
            cur.execute("""
                INSERT INTO buses (plate_number, bus_name, capacity, model, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (plate, name, cap, model))
            bus_ids.append(cur.lastrowid)

        # 4. Central School in Fergana City
        school_lat, school_lon = 40.386400, 71.786400  # Farg'ona shahri, Sayilgoh/Al-Farg'oniy ko'chasi

        # 5. Define 11 Real Fergana Routes with accurate stops
        fergana_routes = [
            {
                "num": "1-yo‘nalish",
                "name": "Qirguli – Maktab",
                "desc": "Qirguli mavzesi, Neftchilar saroyi, Mustaqillik shoh ko‘chasi orqali",
                "driver": "haydovchi1",
                "bus_idx": 0,
                "stops": [
                    ("Qirguli mavzesi bekati", 40.428500, 71.758000),
                    ("Neftchilar madaniyat saroyi", 40.419200, 71.764500),
                    ("FarPI (Politexnika instituti)", 40.404500, 71.771200),
                    ("Viloyat Musiqa teatri", 40.392400, 71.781500),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "2-yo‘nalish",
                "name": "Aeroport – Maktab",
                "desc": "Farg'ona Xalqaro Aeroporti, Yangi Asr ko'chasi orqali",
                "driver": "haydovchi2",
                "bus_idx": 1,
                "stops": [
                    ("Farg‘ona Aeroporti bekati", 40.360100, 71.745000),
                    ("Murabbiylar ko‘chasi", 40.368500, 71.758200),
                    ("Yangi Asr shoh ko‘chasi", 40.375400, 71.771000),
                    ("Al-Farg‘oniy milliy bog‘i", 40.382100, 71.782000),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "3-yo‘nalish",
                "name": "FarDU – Maktab",
                "desc": "Farg'ona Davlat Universiteti, B.Marg'iloniy, Sayilgoh orqali",
                "driver": "haydovchi3",
                "bus_idx": 2,
                "stops": [
                    ("FarDU bosh binosi", 40.381200, 71.792000),
                    ("Burhoniddin Marg‘iloniy ko‘chasi", 40.383500, 71.788500),
                    ("Viloyat San’at saroyi", 40.385200, 71.784500),
                    ("Markaziy Sayilgoh", 40.386000, 71.785200),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "4-yo‘nalish",
                "name": "Markaziy Bozor – Maktab",
                "desc": "Farg'ona dehqon bozori, Ma'rifat ko'chasi orqali",
                "driver": "haydovchi4",
                "bus_idx": 3,
                "stops": [
                    ("Markaziy Dehqon bozori", 40.392500, 71.781000),
                    ("Istiqlol stadioni yo‘li", 40.390500, 71.783200),
                    ("Ma’rifat ko‘chasi bekati", 40.388200, 71.784800),
                    ("Markaziy shahar xiyoboni", 40.387100, 71.785500),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "5-yo‘nalish",
                "name": "Oydin mavzesi – Maktab",
                "desc": "Oydin massivi, Do'stlik bog'i, Farg'ona shoh ko'chasi",
                "driver": "haydovchi5",
                "bus_idx": 4,
                "stops": [
                    ("Oydin mavzesi 1-bekat", 40.375000, 71.805000),
                    ("Do‘stlik sayilgohi", 40.378500, 71.798500),
                    ("Ahmad Yassaviy ko‘chasi", 40.382000, 71.792500),
                    ("Viloyat Hokimligi bekati", 40.385500, 71.788000),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "6-yo‘nalish",
                "name": "Beshbola – Maktab",
                "desc": "Beshbola mavzesi, Al-Xorazmiy ko'chasi orqali",
                "driver": "haydovchi6",
                "bus_idx": 5,
                "stops": [
                    ("Beshbola markazi", 40.365000, 71.775000),
                    ("Al-Xorazmiy bekati", 40.372000, 71.778000),
                    ("Yoshlar xiyoboni", 40.379000, 71.781500),
                    ("O‘zbekiston ko‘chasi", 40.384000, 71.784500),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "7-yo‘nalish",
                "name": "Marg‘ilon Yo‘li – Maktab",
                "desc": "Farg'ona-Marg'ilon shoh ko'chasi, Toshloq aylanmasi orqali",
                "driver": "haydovchi7",
                "bus_idx": 6,
                "stops": [
                    ("Marg‘ilon darvozasi", 40.415000, 71.745000),
                    ("G‘alaba shoh ko‘chasi", 40.405000, 71.758000),
                    ("Taraqqiyot bekati", 40.395000, 71.772000),
                    ("Shahar Markaziy kutubxonasi", 40.388500, 71.783000),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "8-yo‘nalish",
                "name": "Chekshuvar – Maktab",
                "desc": "Chekshuvar mahallasi, Shifokorlar shaharchasi orqali",
                "driver": "haydovchi8",
                "bus_idx": 7,
                "stops": [
                    ("Chekshuvar mahallasi", 40.398000, 71.815000),
                    ("Viloyat Ko‘p tarmoqli shifoxonasi", 40.393000, 71.802000),
                    ("Ziyokorlar ko‘chasi", 40.389000, 71.794000),
                    ("Markaziy Istirohat bog‘i", 40.387500, 71.788500),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "9-yo‘nalish",
                "name": "Yangi Zamon – Maktab",
                "desc": "Yangi Zamon massivi, Mustaqillik ko'chasi orqali",
                "driver": "haydovchi9",
                "bus_idx": 8,
                "stops": [
                    ("Yangi Zamon 1-mavze", 40.370000, 71.820000),
                    ("Temiryo‘l vokzali bekati", 40.375000, 71.812000),
                    ("Farg‘ona ko‘chasi bekati", 40.381000, 71.798000),
                    ("Amir Temur ko‘chasi", 40.385000, 71.789000),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "10-yo‘nalish",
                "name": "Avtovokzal – Maktab",
                "desc": "Farg'ona Markaziy avtovokzali, Quva yo'li orqali",
                "driver": "haydovchi10",
                "bus_idx": 9,
                "stops": [
                    ("Markaziy Avtovokzal", 40.402000, 71.795000),
                    ("Quvasoy yo‘li chorrahasi", 40.396000, 71.791000),
                    ("Sanoat kolleji bekati", 40.391000, 71.787000),
                    ("Shahar markaziy stadioni", 40.387800, 71.785800),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            },
            {
                "num": "11-yo‘nalish",
                "name": "Yangi Chek – Maktab",
                "desc": "Yangi Chek mahallasi, Universitet filiali orqali",
                "driver": "haydovchi11",
                "bus_idx": 10,
                "stops": [
                    ("Yangi Chek markazi", 40.410000, 71.805000),
                    ("Gidroliz shaharchasi bekati", 40.402000, 71.798000),
                    ("Navoiy ko‘chasi", 40.394000, 71.790000),
                    ("Bobur ko‘chasi", 40.388000, 71.786500),
                    ("Smart Maktab (Farg‘ona)", school_lat, school_lon)
                ]
            }
        ]

        # Insert routes and stops
        for r in fergana_routes:
            bus_id = bus_ids[r["bus_idx"]]
            driver_id = driver_ids[r["driver"]]
            cur.execute("""
                INSERT INTO routes (route_number, name, description, bus_id, driver_id, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (r["num"], r["name"], r["desc"], bus_id, driver_id))
            route_id = cur.lastrowid

            for order, (stop_name, lat, lon) in enumerate(r["stops"], start=1):
                cur.execute("""
                    INSERT INTO stops (name, latitude, longitude, default_geofence_radius, is_active)
                    VALUES (?, ?, ?, 100, 1)
                """, (stop_name, lat, lon))
                stop_id = cur.lastrowid

                cur.execute("""
                    INSERT INTO route_stops (route_id, stop_id, stop_order, estimated_minutes)
                    VALUES (?, ?, ?, ?)
                """, (route_id, stop_id, order, 5))

        # Default system settings
        settings_defaults = [
            ("school_name", "SMART MAKTAB FARG‘ONA", "Maktabning rasmiy nomi"),
            ("city", "Farg‘ona", "Shahar"),
            ("telegram_bot_token", "", "Telegram Bot API tokeni"),
            ("telegram_default_chat_id", "", "Asosiy umumiy Telegram guruh yoki kanal ID"),
            ("geofence_radius", "100", "Standart bekat geofence radiusi (metrda)"),
            ("gps_update_interval", "4", "Haydovchi GPS yangilanish intervali (soniyada)")
        ]
        for k, v, d in settings_defaults:
            cur.execute("""
                INSERT OR REPLACE INTO system_settings (key, value, description)
                VALUES (?, ?, ?)
            """, (k, v, d))

        print("Farg'ona shahri ma'lumotlari muvaffaqiyatli o'rnatildi! (11 ta yo'nalish, 55 ta bekat, 11 ta avtobus).")

if __name__ == "__main__":
    seed_database()
