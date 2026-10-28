import os
import json
import time
import threading
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # Persistent backup chat ID
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
WAT_TZ = ZoneInfo("Africa/Lagos")

SUBSCRIBERS_FILE = "subscribers.json"
STATE_FILE = "state.json"

def load_json_file(filepath, default_value):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            return default_value
    return default_value

def save_json_file(filepath, data):
    try:
        with open(filepath, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving {filepath}: {e}")

def send_telegram_message(chat_id, text):
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is not set.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending message to {chat_id}: {e}")
        return False

def broadcast_to_all(text):
    subscribers = load_json_file(SUBSCRIBERS_FILE, [])
    
    # Ensure ADMIN_CHAT_ID is always included
    target_chats = set(subscribers)
    if ADMIN_CHAT_ID:
        try:
            target_chats.add(int(ADMIN_CHAT_ID))
        except ValueError:
            target_chats.add(ADMIN_CHAT_ID)

    for chat_id in target_chats:
        send_telegram_message(chat_id, text)

@app.route("/", methods=["GET"])
def home():
    return "Bot is running 24/7!", 200

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "ignored"}), 200

    message = data.get("message") or data.get("edited_message")
    if message:
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "").strip()

        if chat_id and text.startswith("/start"):
            subscribers = load_json_file(SUBSCRIBERS_FILE, [])
            if chat_id not in subscribers:
                subscribers.append(chat_id)
                save_json_file(SUBSCRIBERS_FILE, subscribers)
            
            welcome_msg = (
                "🟢 *Bot Status: ONLINE & ACTIVE* 🟢\n\n"
                "Welcome! The Forex News Alert Bot is up and running 24/7.\n\n"
                "You are now subscribed to receive:\n"
                "• High-impact Red Folder alerts (60, 30, 15, & 5 mins before release)\n"
                "• Weekly Red Folder schedule digest every Sunday at 1:00 PM WAT\n"
                "• Daily spread reminders at 09:45 PM WAT"
            )
            send_telegram_message(chat_id, welcome_msg)

    return jsonify({"status": "ok"}), 200

def check_spread_reminder(state):
    now_wat = datetime.now(WAT_TZ)
    today_str = now_wat.strftime("%Y-%m-%d")

    # Trigger at 09:45 PM WAT (21:45)
    if now_wat.hour == 21 and 45 <= now_wat.minute <= 50:
        spread_dates = state.get("spread_dates", [])
        if today_str not in spread_dates:
            msg = (
                "⏰ *DAILY SPREAD REMINDER* ⏰\n\n"
                "It's 09:45 PM WAT. Remember to check your broker spreads and liquidity before entering late sessions or holding positions overnight!"
            )
            broadcast_to_all(msg)
            spread_dates.append(today_str)
            
            # Prune old spread dates older than 30 days
            cutoff = (now_wat - timedelta(days=30)).strftime("%Y-%m-%d")
            state["spread_dates"] = [d for d in spread_dates if d >= cutoff]
            save_json_file(STATE_FILE, state)

def check_sunday_weekly_digest(events, state):
    now_wat = datetime.now(WAT_TZ)
    today_str = now_wat.strftime("%Y-%m-%d")

    # Sunday = weekday index 6 | 13:00 to 13:14 WAT window
    if now_wat.weekday() == 6 and now_wat.hour == 13 and 0 <= now_wat.minute <= 14:
        sunday_digests = state.get("sunday_digests", [])
        if today_str not in sunday_digests:
            high_impact_events = []

            for event in events:
                if event.get("impact") == "High":
                    event_iso = event.get("date")
                    title = event.get("title")
                    country = event.get("country")
                    if not event_iso or not title:
                        continue
                    
                    try:
                        utc_dt = datetime.fromisoformat(event_iso.replace("Z", "+00:00"))
                        event_wat = utc_dt.astimezone(WAT_TZ)
                        
                        day_str = event_wat.strftime("%a, %b %d")
                        time_str = event_wat.strftime("%I:%M %p")
                        high_impact_events.append(f"• *{day_str} @ {time_str} WAT* | `{country}` - {title}")
                    except Exception:
                        continue

            if high_impact_events:
                digest_msg = (
                    "📅 *WEEKLY RED FOLDER SCHEDULE* 📅\n\n"
                    "Here are the high-impact economic events scheduled for this week:\n\n"
                    + "\n".join(high_impact_events)
                )
            else:
                digest_msg = "📅 *WEEKLY RED FOLDER SCHEDULE* 📅\n\nNo high-impact Red Folder events scheduled for this week."

            broadcast_to_all(digest_msg)
            sunday_digests.append(today_str)
            
            # Keep only the last 10 Sunday digest records
            state["sunday_digests"] = sunday_digests[-10:]
            save_json_file(STATE_FILE, state)
            print("Sunday weekly digest broadcasted.")

def check_and_alert():
    state = load_json_file(STATE_FILE, {"sent_events": [], "spread_dates": [], "sunday_digests": []})
    check_spread_reminder(state)

    now_wat = datetime.now(WAT_TZ)
    try:
        response = requests.get(FF_CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if response.status_code != 200:
            return
        
        events = response.json()
        check_sunday_weekly_digest(events, state)

        ALERT_THRESHOLDS = [60, 30, 15, 5]
        sent_events = set(state.get("sent_events", []))

        for event in events:
            if event.get("impact") == "High":
                event_iso = event.get("date")
                title = event.get("title")
                country = event.get("country")
                if not event_iso or not title:
                    continue
                
                try:
                    utc_dt = datetime.fromisoformat(event_iso.replace("Z", "+00:00"))
                    event_wat = utc_dt.astimezone(WAT_TZ)
                except Exception:
                    continue
                
                minutes_left = (event_wat - now_wat).total_seconds() / 60.0

                for target_min in ALERT_THRESHOLDS:
                    unique_key = f"{country}-{title}-{event_wat.strftime('%Y%m%d%H%M')}-{target_min}m"
                    
                    if (target_min - 5.0) <= minutes_left <= target_min:
                        if unique_key not in sent_events:
                            time_str = event_wat.strftime("%I:%M %p")
                            msg = (
                                f"🚨 *RED FOLDER ALERT ({target_min} MINS)* 🚨\n\n"
                                f"• *Currency:* `{country}`\n"
                                f"• *Event:* {title}\n"
                                f"• *Release Time:* {time_str} WAT\n"
                                f"• *Forecast:* `{event.get('forecast') or 'N/A'}` | *Previous:* `{event.get('previous') or 'N/A'}`"
                            )
                            broadcast_to_all(msg)
                            sent_events.add(unique_key)

        # Cap sent_events to the latest 500 records to prevent memory leak
        state["sent_events"] = list(sent_events)[-500:]
        save_json_file(STATE_FILE, state)
    except Exception as e:
        print(f"Error checking calendar: {e}")

def background_polling_loop():
    while True:
        try:
            check_and_alert()
        except Exception as e:
            print(f"Unhandled loop error: {e}")
            traceback.print_exc()
        time.sleep(60)

if __name__ == "__main__":
    t = threading.Thread(target=background_polling_loop, daemon=True)
    t.start()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
