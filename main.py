# main.py
import os
import time
import threading
import hashlib
import requests
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from datetime import datetime

# Deta import (deta csomag szükséges a requirements-ben)
from deta import Deta

app = Flask(__name__)

# --- KONFIG ---
URL = os.environ.get("URL", "https://forma1club.hu/")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))  # másodperc
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TEST_KEY = os.environ.get("TEST_KEY", "")
# --- END KONFIG ---

# Deta init: ha DETA_PROJECT_KEY van környezeti változóban (Deta kezelni fogja),
# akkor deta = Deta() automatikusan csatlakozik
deta = Deta()  # ha nem deployolod Deta-ra, akkor lokálisan error lesz (de lokális teszthez nem kell)
base = deta.Base("site_watcher_state")  # egy Base táblát használunk az állapot tárolására

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

# Deta Base - read/write last_hash
def read_last_hash_from_base():
    try:
        item = base.get("state")  # kulcs: "state"
        if item and "last_hash" in item:
            return item["last_hash"]
    except Exception as e:
        print("Hiba Base olvasáskor:", e)
    return None

def write_last_hash_to_base(h):
    try:
        base.put({"key": "state", "last_hash": h, "updated_at": datetime.utcnow().isoformat() + "Z"})
    except Exception as e:
        print("Hiba Base íráskor:", e)

def watcher():
    print("Watcher thread elindult, figyelt:", URL)
    last = read_last_hash_from_base()
    if last:
        status["last_hash"] = last
    while True:
        try:
            h, content = get_page_hash(URL)
            status["last_check"] = datetime.utcnow().isoformat() + "Z"
            if last is None:
                write_last_hash_to_base(h)
                last = h
                status["last_hash"] = h
                print("Első ellenőrzés - hash elmentve.")
            elif h != last:
                print("Változás észlelve!")
                snippet = content[:800]
                msg = f"VÁLTOZÁS észlelve: {URL}\n\n{snippet}"
                if send_telegram(msg):
                    status["last_change_at"] = datetime.utcnow().isoformat() + "Z"
                write_last_hash_to_base(h)
                last = h
                status["last_hash"] = h
            else:
                print("Nincs változás.")
        except Exception as e:
            print("Watcher hiba:", e)
        time.sleep(CHECK_INTERVAL)

# watcher indítása külön szálon
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

@app.route("/test")
def test():
    key = request.args.get("key", "")
    if not TEST_KEY or key != TEST_KEY:
        return "Unauthorized (set TEST_KEY env var and call /test?key=...)", 401
    send_telegram("TESZT ÜZENET: a bot sikeresen működik! ✅")
    return "Teszt üzenet elküldve."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
