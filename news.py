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

def check_spread_reminder():
    now_wat = datetime.now(WAT_TZ)
    # Mon-Fri corresponds to weekday numbers 0 to 4
    if now_wat.weekday() <= 4:
        if now_wat.hour == 9 and 45 <= now_wat.minute < 50:
            msg = (
                "⚠️ *DAILY SPREAD REMINDER* ⚠️\n\n"
                "• *Time:* 09:45 AM WAT\n"
                "• *Action:* Check your market spreads and liquidity before entering trades today!"
            )
            send_telegram_message(msg)
            print("Spread reminder sent successfully.")

def check_and_alert():
    # 1. Run daily spread reminder check
    check_spread_reminder()

    # 2. Check Forex Factory Red Folder News
    now_wat = datetime.now(WAT_TZ)
    print(f"Checking Forex Factory calendar at {now_wat.strftime('%Y-%m-%d %H:%M:%S')} WAT...")
    try:
        response = requests.get(FF_CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch calendar: Status {response.status_code}")
            return
        
        events = response.json()
        ALERT_THRESHOLDS = [60, 30, 15, 5]
        alerts_sent = 0

        for event in events:
            if event.get("impact") == "High":
                event_iso = event.get("date")
                if not event_iso:
                    continue
                
                utc_dt = datetime.fromisoformat(event_iso.replace("Z", "+00:00"))
                event_wat = utc_dt.astimezone(WAT_TZ)
                
                minutes_left = (event_wat - now_wat).total_seconds() / 60.0

                for target_min in ALERT_THRESHOLDS:
                    if (target_min - 2.5) <= minutes_left <= target_min:
                        time_str = event_wat.strftime("%I:%M %p")
                        msg = (
                            f"🚨 *RED FOLDER ALERT ({target_min} MINS)* 🚨\n\n"
                            f"• *Currency:* `{event.get('country')}`\n"
                            f"• *Event:* {event.get('title')}\n"
                            f"• *Release Time:* {time_str} WAT\n"
                            f"• *Forecast:* `{event.get('forecast') or 'N/A'}` | *Previous:* `{event.get('previous') or 'N/A'}`"
                        )
                        send_telegram_message(msg)
                        alerts_sent += 1

        print(f"Check complete. High-impact alerts sent: {alerts_sent}")
    except Exception as e:
        print(f"Error checking calendar: {e}")

if __name__ == "__main__":
    check_and_alert()
