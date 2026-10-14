import os
import requests
from datetime import datetime
import pytz

# ==========================================
# CONFIGURATION & CREDENTIALS (FROM SECRETS)
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
WAT_TZ = pytz.timezone("Africa/Lagos")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram credentials not found in environment variables.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        print(f"Telegram API Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error sending message: {e}")

def check_and_alert():
    send_telegram_message("🧪 *FORCED TEST:* Fetching all upcoming High-Impact Red Folder news for the group check!")

    now_wat = datetime.now(WAT_TZ)
    print(f"Checking Forex Factory calendar at {now_wat.strftime('%Y-%m-%d %H:%M:%S')} WAT...")
    try:
        response = requests.get(FF_CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch calendar: Status {response.status_code}")
            return
        
        events = response.json()
        alerts_sent = 0

        for event in events:
            if event.get("impact") == "High":
                event_iso = event.get("date")
                if not event_iso:
                    continue
                
                utc_dt = datetime.fromisoformat(event_iso.replace("Z", "+00:00"))
                event_wat = utc_dt.astimezone(WAT_TZ)
                time_str = event_wat.strftime("%b %d, %I:%M %p")

                # Force send every high-impact event regardless of time window
                msg = (
                    f"🚨 *FORCED RED FOLDER DUMP* 🚨\n\n"
                    f"• *Currency:* `{event.get('country')}`\n"
                    f"• *Event:* {event.get('title')}\n"
                    f"• *Release Time:* {time_str} WAT\n"
                    f"• *Forecast:* `{event.get('forecast') or 'N/A'}` | *Previous:* `{event.get('previous') or 'N/A'}`"
                )
                send_telegram_message(msg)
                alerts_sent += 1

        print(f"Forced check complete. Total alerts broadcasted: {alerts_sent}")
    except Exception as e:
        print(f"Error checking calendar: {e}")

if __name__ == "__main__":
    check_and_alert()
