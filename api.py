# api.py
from flask import Flask, jsonify
import requests
import random
import time
import threading
import os

app = Flask(__name__)

# --- Config ---
GAME_ID = os.environ.get("GAME_ID", "109983668079237")
ROBLOX_API_URL = f"https://games.roblox.com/v1/games/{GAME_ID}/servers/Public"

# Proxies: mantenlos aquí o carga desde env var (recomendado para seguridad)
PROXIES = [
    "http://eb77vrqvqol2-country-gb:P10Pmrmwo4pUYhj@proxy.vaultproxies.com:8080",
] * 15

# Caché y parámetros
server_cache = []
CACHE_LIMIT = int(os.environ.get("CACHE_LIMIT", 500))
CACHE_REFRESH_INTERVAL = int(os.environ.get("CACHE_REFRESH_INTERVAL", 45))
CACHE_LOW_THRESHOLD = int(os.environ.get("CACHE_LOW_THRESHOLD", 50))

# --- Worker que rellena la caché ---
def fetch_servers():
    global server_cache
    while True:
        try:
            proxy = random.choice(PROXIES)
            proxies = {"http": proxy, "https": proxy}
            resp = requests.get(
                ROBLOX_API_URL,
                params={"sortOrder": "Asc", "limit": 100},
                proxies=proxies,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            servers = data.get("data", [])
            available = [s for s in servers if s.get("playing", 0) < s.get("maxPlayers", 10)]
            existing_ids = {s["id"] for s in server_cache}
            new = [s for s in available if s["id"] not in existing_ids]
            server_cache.extend(new)
            if len(server_cache) > CACHE_LIMIT:
                server_cache = server_cache[:CACHE_LIMIT]
            print(f"[CACHE REFRESH] +{len(new)} | total={len(server_cache)}")
        except Exception as e:
            print(f"[fetch_servers] error: {e}")

        # espera o fuerza recarga si la cache cae por debajo
        for _ in range(CACHE_REFRESH_INTERVAL):
            time.sleep(1)
            if len(server_cache) < CACHE_LOW_THRESHOLD:
                print("[CACHE LOW] below threshold, refetching soon")
                break

# --- Endpoint público ---
@app.route("/get-server", methods=["GET"])
def get_server():
    global server_cache
    if not server_cache:
        return jsonify({"error": "No servers available"}), 404
    s = server_cache.pop(0)
    job_id = s.get("id")
    playing = s.get("playing", 0)
    maxp = s.get("maxPlayers", 10)
    print(f"[SERVER RETURNED] {job_id} ({playing}/{maxp}) | cache_left={len(server_cache)}")
    return jsonify({
        "job_id": job_id,
        "players": playing,
        "max_players": maxp
    })

# --- Lanzar el worker en background al importar (Render ejecuta gunicorn, no app.run()) ---
def start_background_worker():
    t = threading.Thread(target=fetch_servers, daemon=True)
    t.start()

start_background_worker()

# --- Opcional: ruta raíz para comprobar (health) ---
@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "cached": len(server_cache)}), 200

# Nota: no llamamos a app.run() aquí; Render iniciará con gunicorn (Procfile).
