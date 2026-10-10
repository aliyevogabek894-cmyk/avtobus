import os
import uvicorn
from database import init_db
from seed_data import seed_database

if __name__ == "__main__":
    print("=" * 60)
    print("SMART SCHOOL BUS — BOSHQARUV VA GPS KUZATUV TIZIMI")
    print("=" * 60)
    
    # Initialize and seed database if not already seeded
    init_db()
    seed_database()

    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    print("\nServer ishga tushmoqda:")
    print(f" -> Asosiy Hub:        http://{host}:{port}")
    print(f" -> Ota-onalar Sayti:  http://{host}:{port}/parent")
    print(f" -> Haydovchi Paneli:  http://{host}:{port}/driver")
    print(f" -> Admin Paneli:      http://{host}:{port}/admin")
    print(f" -> API Hujjatlari:    http://{host}:{port}/docs\n")
    print("To'xtatish uchun: Ctrl + C bosing.")
    print("=" * 60)

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,
        access_log=False,
        timeout_keep_alive=65,
        limit_concurrency=1000
    )
