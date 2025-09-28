# main.py
import os
import time
import threading
import hashlib
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from datetime import datetime

app = Flask(__name__)

# Konfiguráció (Render-en ENV változókból állítjuk)
URL = os.environ.get("URL", "https://forma1club.hu/")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))  # másodpercben
STATE_FILE = os.environ.get("STATE_FILE", "last_hash.txt")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TEST_KEY = os.environ.get("TEST_KEY", "")

status = {
    "last_check": None,
    "last_hash": None,
    "last_change_at": None,
    "last_message": None
}

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram nincs beállítva (ENV hiányzik). Üzenet nem küldve.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
        print("Telegram üzenet elküldve.")
        status["last_message"] = datetime.utcnow().isoformat() + "Z"
        return True
    except Exception as e:
        print("Telegram küldési hiba:", e)
        return False

def get_page_hash(url):
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    content = soup.get_text(separator=" ", strip=True)
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return h, content

def read_last_hash(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return f.read().strip()
        except:
            return None
    return None

def write_last_hash(path, h):
    with open(path, "w") as f:
        f.write(h)

def watcher():
    print("Watcher thread elindult, figyelt:", URL)
    last = read_last_hash(STATE_FILE)
    if last:
        status["last_hash"] = last
    while True:
        try:
            h, content = get_page_hash(URL)
            status["last_check"] = datetime.utcnow().isoformat() + "Z"
            if last is None:
                write_last_hash(STATE_FILE, h)
                last = h
                status["last_hash"] = h
                print("Első ellenőrzés - hash elmentve.")
            elif h != last:
                print("Változás észlelve!")
                snippet = content[:800]
                msg = f"VÁLTOZÁS észlelve: {URL}\n\n{snippet}"
                if send_telegram(msg):
                    status["last_change_at"] = datetime.utcnow().isoformat() + "Z"
                write_last_hash(STATE_FILE, h)
                last = h
                status["last_hash"] = h
            else:
                print("Nincs változás.")
        except Exception as e:
            print("Watcher hiba:", e)
        time.sleep(CHECK_INTERVAL)

# watcher indítása külön szálon (gunicorn importáláskor lefut)
threading.Thread(target=watcher, daemon=True).start()

@app.route("/")
def home():
    return jsonify({
        "status": "running",
        "watched_url": URL,
        "last_check": status["last_check"],
        "last_hash": status["last_hash"],
        "last_change_at": status["last_change_at"],
    })

# Teszt végpont: hívhatod: https://<your-service>/test?key=TESZT_KULCS
@app.route("/test")
def test():
    key = request.args.get("key", "")
    if not TEST_KEY or key != TEST_KEY:
        return "Unauthorized (set TEST_KEY env var and call /test?key=...)", 401
    send_telegram("TESZT ÜZENET: a bot sikeresen működik! ✅")
    return "Teszt üzenet elküldve."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
