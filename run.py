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

    print("\nServer ishga tushmoqda:")
    print(" -> Asosiy Hub:        http://127.0.0.1:8000")
    print(" -> Ota-onalar Sayti:  http://127.0.0.1:8000/parent")
    print(" -> Haydovchi Paneli:  http://127.0.0.1:8000/driver")
    print(" -> Admin Paneli:      http://127.0.0.1:8000/admin")
    print(" -> API Hujjatlari:    http://127.0.0.1:8000/docs\n")
    print("To'xtatish uchun: Ctrl + C bosing.")
    print("=" * 60)

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
