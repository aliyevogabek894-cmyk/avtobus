import asyncio
import logging
import httpx
from datetime import datetime
from database import get_db, get_db_cursor
from config import TELEGRAM_BOT_TOKEN, DEFAULT_TELEGRAM_CHAT_ID

logger = logging.getLogger("telegram_service")

def get_telegram_config():
    bot_token = TELEGRAM_BOT_TOKEN
    default_chat_id = DEFAULT_TELEGRAM_CHAT_ID
    
    conn = get_db()
    try:
        row1 = conn.execute("SELECT value FROM system_settings WHERE key = 'telegram_bot_token'").fetchone()
        if row1 and row1["value"]:
            bot_token = row1["value"]
        row2 = conn.execute("SELECT value FROM system_settings WHERE key = 'telegram_default_chat_id'").fetchone()
        if row2 and row2["value"]:
            default_chat_id = row2["value"]
    finally:
        conn.close()
        
    return bot_token, default_chat_id

async def send_telegram_message(chat_id: str, message_text: str, trip_id: int | None = None, stop_id: int | None = None) -> tuple[bool, str]:
    bot_token, default_chat_id = get_telegram_config()
    target_chat = chat_id or default_chat_id
    
    if not bot_token or not target_chat:
        msg = "Telegram bot token yoki chat_id sozlanmagan"
        logger.warning(msg)
        return False, msg

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": message_text,
        "parse_mode": "HTML"
    }
    
    # Insert pending notification job
    job_id = None
    with get_db_cursor() as cur:
        cur.execute("""
            INSERT INTO notification_jobs (trip_id, stop_id, chat_id, message_text, status, attempts)
            VALUES (?, ?, ?, ?, 'pending', 0)
        """, (trip_id, stop_id, str(target_chat), message_text))
        job_id = cur.lastrowid

    # Try sending with retry up to 3 times
    success = False
    last_err = ""
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(url, json=payload)
                data = res.json()
                if res.status_code == 200 and data.get("ok"):
                    success = True
                    with get_db_cursor() as cur:
                        cur.execute("""
                            UPDATE notification_jobs
                            SET status = 'sent', attempts = ?, sent_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (attempt, job_id))
                    return True, "Yuborildi"
                else:
                    last_err = data.get("description", str(data))
        except Exception as e:
            last_err = str(e)
        
        await asyncio.sleep(1.0 * attempt)

    # If reached here, failed
    with get_db_cursor() as cur:
        cur.execute("""
            UPDATE notification_jobs
            SET status = 'failed', attempts = 3, error_message = ?
            WHERE id = ?
        """, (last_err, job_id))
    return False, last_err

def format_arrival_message(route_name: str, bus_name: str, stop_name: str, time_str: str) -> str:
    return (
        f"🚌 <b>MAKTAB AVTOBUSI</b>\n\n"
        f"<b>Yo‘nalish:</b> {route_name}\n"
        f"<b>Avtobus:</b> {bus_name}\n"
        f"<b>Bekat:</b> {stop_name}\n"
        f"<b>Holat:</b> Bekatga yetib keldi\n"
        f"<b>Vaqt:</b> {time_str}\n\n"
        f"<i>GPS orqali avtomatik aniqlandi.</i>"
    )
