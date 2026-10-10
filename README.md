# 🚌 SMART SCHOOL BUS — TO‘LIQ AVTOBUS BOSHQARUV VA GPS KUZATUV TIZIMI

Maktabning 10–11 ta avtobus yo‘nalishini yagona zamonaviy web-platforma orqali boshqarish, haydovchilar GPS harakatini qabul qilish, avtomatik bekat geofencing orqali aniqlash, Telegram xabarlarini yuborish va ota-onalar uchun jonli xarita monitoringini taqdim etuvchi to‘liq ishlaydigan dasturiy majmua.

---

## 🌟 TIZIM TARKIBI VA ASOSIY QISMLARI

1. **ADMIN BOSHQARUV MARKAZI (`/admin`)**
   - **Bosh sahifa (Dashboard):** 8 ta statistika kartalari (Jami avtobuslar, yo‘nalishlar, bekatlar, safardagi avtobuslar, GPS faol, aloqasi uzilgan, bugungi safarlar, Telegram yuborilgan/xato xabarlar).
   - **Jonli Xarita:** Barcha avtobuslarning Toshkent shahri bo‘ylab real vaqtdagi umumiy xaritasi.
   - **Avtobuslarni boshqarish:** CRUD, davlat raqami, model, sig‘im, yo‘nalishga biriktirish, soft-delete (tarix saqlanadi).
   - **Yo‘nalishlarni boshqarish:** 10–11 ta yo‘nalish, bekatlar zanjiri, biriktirilgan transport va haydovchilar, Telegram chat ID.
   - **Bekatlarni boshqarish:** Interaktiv Leaflet xaritada nuqta bosib koordinata tanlash, geofence radiusini sozlash (standart 100 metr).
   - **Haydovchilar & Yo‘nalish Parollari:** Har bir yo‘nalish/haydovchi uchun alohida xavfsiz hisob, **bcrypt** xeshli parollar, xavfsiz reset funksiyasi.
   - **Telegram Sozlamalari:** BotFather tokeni, default chat ID, sinov xabarini yuborish, xabarlar navbati va loglar.
   - **Safarlar Tarixi & Audit Jurnali:** Har bir boshlangan/tugagan safar va admin amallarining to‘liq xavfsizlik arxivi.

2. **HAYDOVCHI MOBIL PANELI (`/driver`)**
   - Mobil telefon brauzeriga moslashtirilgan katta teginish maydonlari va sodda interfeys.
   - Haydovchi login qilganda faqat o‘ziga biriktirilgan yo‘nalish va avtobus ochiladi.
   - Katta **"YO‘LNI BOSHLASH"** va **"SAFARNI TUGATISH"** tugmalari.
   - **FON REJIMIDA DOIMIY UZATISH:** Haydovchi saytdan chiqib ketganda, boshqa ilovalarga o'tganda yoki telefon ekrani qulflanganda ham GPS uzatilishi to'xtamaydi (Silent Audio Keepalive + Wake Lock API + LocalStorage sessiya tiklanishi).
   - **Sinov Simulyatori (Demo Rejim):** Kompyuterda yoki test paytida bekatma-bekat avtomatik harakatlanib, geofence va xabarlarni sinab ko‘rish imkoniyati.
   - Bekatga yetib kelganda avtomatik ovozli signal (Ding) va tebranish (Vibration).

3. **OTA-ONALAR UCHUN JONLI KUZATUV SAYTI (`/parent`)**
   - **Telegram Guruh Shart Emas:** Ota-onalarga shunchaki yo‘nalish havolasi (link) tashlab beriladi (masalan: `/parent?route=1` yoki `/parent?route=2`), ular brauzerdan kirib to‘g‘ridan-to‘g‘ri kuzatishadi.
   - **Orqada Katta Mashtabli Jonli Xarita:** Xarita butun ekranni egallab turadi, avtobus harakatlanganda xarita avtomatik unga ergashadi (Auto-follow rejimi).
   - **SAYTGA JONLI XABARLAR (Live Alerts & Pop-up):**
     - Avtobus har bir bekatga yetib kelganda saytning yuqorisida katta chiroyli bildirishnoma chiqadi: `🔔 AVTOBUS BEKATGA YETIB KELDI! (Vaqt: 07:24)`.
     - Ovozli bildirishnoma (Chime) yangraydi.
     - O‘ng tomonda "Sayt Xabarlari Jurnali" mavjud bo‘lib, ota-ona qaysi bekatga soat nechada kelinganini ko‘rib turadi.
   - **Havolani Ulashish Tugmasi:** Bitta tugma orqali yo‘nalish linkini nusxalash va ota-onalar chatiga yuborish imkoni.

---

## 🔑 BOSHLANG‘ICH TEST HISOBLARI

Tizimda 11 ta yo‘nalish, 11 ta avtobus va 55 ta bekat koordinatalari tayyor holda o‘rnatilgan:

| Rol | Login | Dastlabki Parol | Biriktirilgan Yo‘nalish |
| :--- | :--- | :--- | :--- |
| **Bosh Administrator** | `admin` | `Admin2026!` | Barcha tizim |
| **Haydovchi 1** | `haydovchi1` | `Haydovchi2026!` | 1-yo‘nalish: Yunusobod – Maktab |
| **Haydovchi 2** | `haydovchi2` | `Haydovchi2026!` | 2-yo‘nalish: Chilonzor – Maktab |
| **Haydovchi 3** | `haydovchi3` | `Haydovchi2026!` | 3-yo‘nalish: Mirzo Ulug‘bek – Maktab |
| **Haydovchi 4** | `haydovchi4` | `Haydovchi2026!` | 4-yo‘nalish: Sergeli – Maktab |
| **Haydovchi 5** | `haydovchi5` | `Haydovchi2026!` | 5-yo‘nalish: Yashnobod – Maktab |
| **Haydovchi 6** | `haydovchi6` | `Haydovchi2026!` | 6-yo‘nalish: Olmazor – Maktab |
| **Haydovchi 7** | `haydovchi7` | `Haydovchi2026!` | 7-yo‘nalish: Uchtepa – Maktab |
| **Haydovchi 8** | `haydovchi8` | `Haydovchi2026!` | 8-yo‘nalish: Shayxontohur – Maktab |
| **Haydovchi 9** | `haydovchi9` | `Haydovchi2026!` | 9-yo‘nalish: Mirobod – Maktab |
| **Haydovchi 10** | `haydovchi10` | `Haydovchi2026!` | 10-yo‘nalish: Yakkasaroy – Maktab |
| **Haydovchi 11** | `haydovchi11` | `Haydovchi2026!` | 11-yo‘nalish: Bektemir – Maktab |

---

## 🛠️ TEXNOLOGIK STACK

- **Backend:** Python 3.14 + FastAPI (Asinxron yuqori tezlik)
- **Ma’lumotlar bazasi:** SQLite 3 (WAL rejimi, Foreign Keys, Tranzaksiyalar, Indekslar)
- **Frontend:** Vanilla JS (ES6+), HTML5, Zamonaviy CSS Dizayn Tizimi (Outfit & Inter shriftlari, Glassmorphism)
- **Xarita:** Leaflet.js 1.9.4 & OpenStreetMap CartoDB Tiles
- **Xavfsizlik:** Bcrypt parol xeshlash, JWT tokenlar, Rolga asoslangan ruxsatlar (RBAC)
- **Geofencing:** Haversine formulasi bo‘yicha metrlarda aniq masofa hisoblash
- **Telegram Integratsiyasi:** Telegram Bot API (Asinxron httpx, 3 martagacha qayta urinish - retry, deduplication)

---

## 🚀 ISHGA TUSHIRISH YO‘RIQNOMASI

### 1. Talablar
Kompyuterda Python 3.10+ o‘rnatilgan bo‘lishi kifoya.

### 2. O‘rnatish va Ishga tushirish (Windows)
Eng oson usul — `start.bat` faylini ikki marta bosish yoki terminalda:

```powershell
python run.py
```

Server ishga tushgach quyidagi havolalar ochiladi:
- **Asosiy Portal Hub:** [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Ota-onalar Sayti:** [http://127.0.0.1:8000/parent](http://127.0.0.1:8000/parent)
- **Haydovchi Paneli:** [http://127.0.0.1:8000/driver](http://127.0.0.1:8000/driver)
- **Admin Boshqaruv Paneli:** [http://127.0.0.1:8000/admin](http://127.0.0.1:8000/admin)
- **Interaktiv API Hujjatlari:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 AVTOMATLASHTIRILGAN TESTLARNI ISHGA TUSHIRISH

Barcha 17 ta qabul qilish talablari (avtorizatsiya, izolyatsiya, GPS geofencing, takroriy xabarlarni bloklash, parol yangilanishi, audit jurnali) avtomatlashtirilgan test orqali to‘liq sinovdan o‘tgan.

Testni qayta ishga tushirish uchun:

```powershell
python test_system.py
```

Natija:
```
ALL 11 INTEGRATION TESTS PASSED WITH 100% SUCCESS!
```
