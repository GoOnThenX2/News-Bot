import os
import json
import time
import requests
import threading
from datetime import datetime
import pytz
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==========================================
# CONFIGURATION & CREDENTIALS
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
WAT_TZ = pytz.timezone("Africa/Lagos")
STATE_FILE = "sent_alerts.json"
SUBSCRIBERS_FILE = "subscribers.json"

def load_json_file(filename, default_value):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return default_value

def save_json_file(filename, data):
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Error saving {filename}: {e}")

def send_telegram_message(chat_id, message):
    if not TELEGRAM_BOT_TOKEN:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message to {chat_id}: {e}")
        return False

def broadcast_to_all(message):
    subscribers = load_json_file(SUBSCRIBERS_FILE, [])
    for chat_id in subscribers:
        send_telegram_message(chat_id, message)

def check_spread_reminder(state):
    now_wat = datetime.now(WAT_TZ)
    today_str = now_wat.strftime("%Y-%m-%d")
    
    # 21 represents 9 PM in 24-hour format
    if now_wat.weekday() <= 4 and now_wat.hour == 21 and 45 <= now_wat.minute <= 59:
        if today_str not in state.get("spread_dates", []):
            msg = (
                "⚠️ *DAILY SPREAD REMINDER* ⚠️\n\n"
                "• *Time:* 09:45 PM WAT\n"
                "• *Action:* Check your market spreads and liquidity before entering trades tonight!"
            )
            broadcast_to_all(msg)
            state.setdefault("spread_dates", []).append(today_str)
            print("Spread reminder broadcasted.")

def check_and_alert():
    state = load_json_file(STATE_FILE, {"sent_events": [], "spread_dates": []})
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
                            broadcast_to_all(msg)
                            state.setdefault("sent_events", []).append(unique_key)

        save_json_file(STATE_FILE, state)
    except Exception as e:
        print(f"Error checking calendar: {e}")

# Continuous Background Loop
def start_bot_loop():
    while True:
        try:
            check_and_alert()
        except Exception as e:
            print(f"Loop error: {e}")
        time.sleep(60)

# Web Routes
@app.route('/')
def home():
    return jsonify({"status": "running", "bot": "Forex News Alert Bot"})

# Webhook endpoint for Telegram to send user interactions (/start)
@app.route('/telegram-webhook', methods=['POST'])
def telegram_webhook():
    data = request.get_json()
    if data and "message" in data:
        message = data["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text", "")

        if text.startswith("/start"):
            subscribers = load_json_file(SUBSCRIBERS_FILE, [])
            if chat_id not in subscribers:
                subscribers.append(chat_id)
                save_json_file(SUBSCRIBERS_FILE, subscribers)
            
            welcome_msg = (
                "🤖 *Welcome to the Forex News Alert Bot!* 🤖\n\n"
                "You are now successfully subscribed to receive high-impact Red Folder news and daily spread reminders directly in your private chat."
            )
            send_telegram_message(chat_id, welcome_msg)

    return jsonify({"status": "ok"})

# Start background thread for checking news
threading.Thread(target=start_bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
