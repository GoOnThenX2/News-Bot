import os
import json
import time
import requests
import threading
from datetime import datetime
import pytz
from flask import Flask, jsonify

# Flask Web Server setup
app = Flask(__name__)

# ==========================================
# CONFIGURATION & CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
WAT_TZ = pytz.timezone("Africa/Lagos")
STATE_FILE = "sent_alerts.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"sent_events": [], "spread_dates": []}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"Error saving state file: {e}")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram credentials not found in environment variables.")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message: {e}")
        return False

def check_spread_reminder(state):
    now_wat = datetime.now(WAT_TZ)
    today_str = now_wat.strftime("%Y-%m-%d")
    
    if now_wat.weekday() <= 4 and now_wat.hour == 9 and 45 <= now_wat.minute <= 59:
        if today_str not in state.get("spread_dates", []):
            msg = (
                "⚠️ *DAILY SPREAD REMINDER* ⚠️\n\n"
                "• *Time:* 09:45 AM WAT\n"
                "• *Action:* Check your market spreads and liquidity before entering trades today!"
            )
            if send_telegram_message(msg):
                state.setdefault("spread_dates", []).append(today_str)
                print("Spread reminder sent successfully.")

def check_and_alert():
    state = load_state()
    check_spread_reminder(state)

    now_wat = datetime.now(WAT_TZ)
    try:
        response = requests.get(FF_CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if response.status_code != 200:
            return
        
        events = response.json()
        ALERT_THRESHOLDS = [60, 30, 15, 5]

        for event in events:
            if event.get("impact") == "High":
                event_iso = event.get("date")
                title = event.get("title")
                country = event.get("country")
                if not event_iso or not title:
                    continue
                
                utc_dt = datetime.fromisoformat(event_iso.replace("Z", "+00:00"))
                event_wat = utc_dt.astimezone(WAT_TZ)
                
                minutes_left = (event_wat - now_wat).total_seconds() / 60.0

                for target_min in ALERT_THRESHOLDS:
                    unique_key = f"{country}-{title}-{event_wat.strftime('%Y%m%d%H%M')}-{target_min}m"
                    
                    if (target_min - 5.0) <= minutes_left <= target_min:
                        if unique_key not in state.get("sent_events", []):
                            time_str = event_wat.strftime("%I:%M %p")
                            msg = (
                                f"🚨 *RED FOLDER ALERT ({target_min} MINS)* 🚨\n\n"
                                f"• *Currency:* `{country}`\n"
                                f"• *Event:* {title}\n"
                                f"• *Release Time:* {time_str} WAT\n"
                                f"• *Forecast:* `{event.get('forecast') or 'N/A'}` | *Previous:* `{event.get('previous') or 'N/A'}`"
                            )
                            if send_telegram_message(msg):
                                state.setdefault("sent_events", []).append(unique_key)

        save_state(state)
    except Exception as e:
        print(f"Error checking calendar: {e}")

# Continuous Background Loop (Runs every 60 seconds)
def start_bot_loop():
    while True:
        try:
            check_and_alert()
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(60)

# Web Server Route for Uptime pings
@app.route('/')
def home():
    return jsonify({"status": "running", "bot": "Forex News Alert Bot"})

# Start background thread
threading.Thread(target=start_bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
