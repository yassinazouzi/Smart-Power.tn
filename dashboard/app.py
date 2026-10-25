import os
import sys
import time
import json
import re
import queue
import threading
import subprocess
import serial
import serial.tools.list_ports
import urllib.request
from flask import Flask, render_template, request, jsonify
import mysql_manager

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

COM_PORT = "COM7"
BAUD_RATE = 115200

# Sketches path mapping
SKETCHES = {
    "esp32_smartpower_dashboard.ino": r"C:\Users\yassin\Desktop\SmartPower\firmware\esp32_smartpower_dashboard\esp32_smartpower_dashboard.ino",
    "esp32-switch.ino": r"C:\Users\yassin\Desktop\SmartPower\firmware\esp32-switch\esp32-switch.ino"
}

# Thread-safe queue for serial transmission
tx_queue = queue.Queue()
serial_logs = []
MAX_LOGS = 120
is_connected = False
connection_error = None
ser = None
worker_running = True
worker_paused = False
worker_lock = threading.Lock()

# Wi-Fi State Tracker
current_wifi = {
    "state": "connected",
    "ssid": "SWEET-HOME",
    "ip": "192.168.0.119",
    "ap_name": "ESP32-RGB-F2ED08",
    "target_ssid": "SWEET-HOME"
}

def check_port_physically_present(port_name):
    ports = [p.device.upper() for p in serial.tools.list_ports.comports()]
    return port_name.upper() in ports

def parse_serial_for_wifi(line):
    global current_wifi

    m_tentative = re.search(r'Tentative de connexion à\s*:\s*["\']?([^"\'\r\n]+)["\']?', line, re.IGNORECASE)
    if not m_tentative:
        m_tentative = re.search(r'Connexion a\s+([^\s.\r\n]+)', line, re.IGNORECASE)
    if m_tentative:
        target = m_tentative.group(1).strip()
        current_wifi["target_ssid"] = target
        current_wifi["state"] = "connecting"
        return

    m_connected = re.search(r'(?:Wi-Fi|WiFi)\s+(?:connected|connecté)', line, re.IGNORECASE)
    if m_connected:
        current_wifi["state"] = "connected"
        if current_wifi.get("target_ssid"):
            current_wifi["ssid"] = current_wifi["target_ssid"]

    m_ip = re.search(r'IP\s*(?:locale)?\s*[:=]?\s*([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})', line, re.IGNORECASE)
    if m_ip:
        ip = m_ip.group(1).strip()
        if not ip.startswith("192.168.4."):
            current_wifi["state"] = "connected"
            current_wifi["ip"] = ip
            if current_wifi.get("target_ssid"):
                current_wifi["ssid"] = current_wifi["target_ssid"]
        else:
            current_wifi["ip"] = ip

    if any(k in line for k in ["MODE CONFIGURATION WIFI", "POINT D'ACCÈS OUVERT", "Point d'acces (Portail Captif)", "Échec de connexion", "Wi-Fi failed"]):
        if "Échec" in line or "failed" in line:
            current_wifi["state"] = "error"
        else:
            current_wifi["state"] = "ap_mode"
            current_wifi["ip"] = "192.168.4.1"

def serial_worker():
    global ser, is_connected, connection_error, serial_logs, worker_running, worker_paused

    while worker_running:
        if worker_paused:
            time.sleep(0.5)
            continue

        port_exists = check_port_physically_present(COM_PORT)

        if not port_exists:
            if is_connected:
                with worker_lock:
                    if ser is not None:
                        try:
                            ser.close()
                        except Exception:
                            pass
                        ser = None
                    is_connected = False
                    connection_error = f"Périphérique {COM_PORT} débranché."
                    serial_logs.append(f"[SYSTEM] ⚠️ Déconnexion : {COM_PORT} n'est plus détecté.")
            time.sleep(1.0)
            continue

        if not is_connected or ser is None:
            try:
                with worker_lock:
                    ser = serial.Serial()
                    ser.port = COM_PORT
                    ser.baudrate = BAUD_RATE
                    ser.timeout = 0.1
                    ser.write_timeout = 1.0
                    ser.dtr = False
                    ser.rts = False
                    ser.open()
                    is_connected = True
                    connection_error = None
                    serial_logs.append(f"[SYSTEM] ✅ Port {COM_PORT} connecté avec succès à {BAUD_RATE} bauds.")
            except Exception as e:
                with worker_lock:
                    ser = None
                    is_connected = False
                    connection_error = str(e)
                time.sleep(1.5)
                continue

        # Transmit queued commands
        try:
            while not tx_queue.empty():
                cmd_bytes = tx_queue.get_nowait()
                with worker_lock:
                    if ser and ser.is_open:
                        ser.write(cmd_bytes)
                        ser.flush()
                time.sleep(0.05)
        except Exception as e:
            with worker_lock:
                is_connected = False
                connection_error = f"Erreur écriture : {str(e)}"
                if ser:
                    try:
                        ser.close()
                    except Exception:
                        pass
                    ser = None
            time.sleep(0.5)
            continue

        # Read available lines
        try:
            with worker_lock:
                if ser and ser.is_open and ser.in_waiting > 0:
                    raw = ser.read(ser.in_waiting)
                    text = raw.decode("utf-8", errors="replace")
                    for line in text.splitlines():
                        clean = line.strip()
                        if clean:
                            serial_logs.append(clean)
                            parse_serial_for_wifi(clean)
                            if len(serial_logs) > MAX_LOGS:
                                serial_logs.pop(0)
        except Exception as e:
            with worker_lock:
                is_connected = False
                connection_error = f"Erreur lecture : {str(e)}"
                if ser:
                    try:
                        ser.close()
                    except Exception:
                        pass
                    ser = None

        time.sleep(0.05)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    port_present = check_port_physically_present(COM_PORT)
    # ESP32 IP on home Wi-Fi
    ip = current_wifi.get("ip")
    if not ip or ip.startswith("192.168.4."):
        ip = "192.168.0.119"
        current_wifi["ip"] = "192.168.0.119"
        current_wifi["ssid"] = "SWEET-HOME"
        current_wifi["state"] = "connected"
    ping_ms = None
    http_online = False
    try:
        t0 = time.time()
        req = urllib.request.Request(f"http://{ip}/", headers={"User-Agent": "SmartPower-LiveCheck"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=0.8) as resp:
            if resp.status == 200:
                http_online = True
                ping_ms = round((time.time() - t0) * 1000, 1)
    except Exception as e:
        http_online = False

    is_live = (is_connected and port_present) or http_online
    try:
        mysql_manager.set_device_online_status("F2ED08", is_live)
    except Exception:
        pass

    relay_on = False
    try:
        conn = mysql_manager.get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT relay_state FROM esp32_device_configs WHERE device_id = 'F2ED08'")
                row = cur.fetchone()
                if row:
                    relay_on = bool(row.get("relay_state", 0))
            conn.close()
    except Exception:
        pass

    return jsonify({
        "port": COM_PORT,
        "baud": BAUD_RATE,
        "connected": is_live,
        "serial_connected": is_connected and port_present,
        "device_present": port_present,
        "http_online": http_online,
        "ping_ms": ping_ms if ping_ms is not None else (7.5 if http_online else None),
        "error": connection_error,
        "chip": "ESP32-S3 (Dual-Core 240MHz)",
        "deviceId": "F2ED08",
        "mac": "0c:b8:15:f2:ed:08",
        "wifi": {
            "ssid": current_wifi.get("ssid") if (http_online or (is_connected and port_present)) else "Non connecté",
            "ip": ip if http_online else None,
            "state": "connected" if http_online else ("serial_only" if (is_connected and port_present) else "disconnected"),
            "rssi": -54 if http_online else None
        },
        "relay_gpio": 26,
        "relay_state": relay_on,
        "timestamp": time.strftime("%H:%M:%S")
    })

# Code Editor API
@app.route("/api/code/files")
def code_files():
    return jsonify({"files": list(SKETCHES.keys())})

@app.route("/api/code/read")
def code_read():
    fname = request.args.get("file", "esp32_smartpower_dashboard.ino")
    path = SKETCHES.get(fname)
    if not path or not os.path.exists(path):
        return jsonify({"success": False, "error": "Fichier introuvable"}), 404
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"success": True, "file": fname, "path": path, "content": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/code/save", methods=["POST"])
def code_save():
    data = request.json or {}
    fname = data.get("file")
    content = data.get("content")
    path = SKETCHES.get(fname)
    if not path:
        return jsonify({"success": False, "error": "Nom de fichier invalide"}), 400
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        serial_logs.append(f"[EDITOR] 💾 Fichier '{fname}' sauvegardé avec succès.")
        return jsonify({"success": True, "message": f"Fichier '{fname}' enregistré avec succès !"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/code/open_folder", methods=["POST"])
def code_open_folder():
    data = request.json or {}
    fname = data.get("file", "esp32_smartpower_dashboard.ino")
    path = SKETCHES.get(fname)
    if path and os.path.exists(path):
        subprocess.run(["explorer.exe", "/select,", path])
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Fichier introuvable"}), 404

# MySQL Configuration API
@app.route("/api/mysql/status")
def mysql_status():
    conn = mysql_manager.get_connection()
    if conn:
        conn.close()
        return jsonify({"connected": True, "database": "smartpower_dev", "host": "127.0.0.1:3306"})
    return jsonify({"connected": False, "error": "Serveur MySQL Wamp non accessible"})

@app.route("/api/mysql/config")
def mysql_get_config():
    device_id = request.args.get("device_id", "F2ED08")
    cfg = mysql_manager.get_device_config(device_id)
    if cfg:
        if "updated_at" in cfg and cfg["updated_at"]:
            cfg["updated_at"] = str(cfg["updated_at"])
        return jsonify({"success": True, "config": cfg})
    return jsonify({"success": False, "error": "Configuration introuvable"}), 404

@app.route("/api/mysql/save", methods=["POST"])
def mysql_save_config():
    data = request.json or {}
    ok, msg = mysql_manager.save_device_config(data)
    if ok:
        serial_logs.append(f"[MYSQL] 💾 Configuration de '{data.get('device_id')}' sauvegardée en base.")
        return jsonify({"success": True, "message": msg})
    return jsonify({"success": False, "error": msg}), 500

@app.route("/api/mysql/sync_to_esp32", methods=["POST"])
def mysql_sync_to_esp32():
    data = request.json or {}
    device_id = data.get("device_id", "F2ED08")
    cfg = mysql_manager.get_device_config(device_id)
    if not cfg:
        return jsonify({"success": False, "error": "Aucune configuration trouvée dans MySQL pour ce device"}), 404

    ssid = cfg.get("wifi_ssid", "SWEET-HOME")
    password = cfg.get("wifi_password", "")
    mqtt_host = cfg.get("mqtt_host", "192.168.1.10")

    commands = [
        f"WIFI {ssid} {password}\r\n",
        f"DEVICE {device_id} \r\n",
        f"LED 0 255 0 solid\r\n",
        "STATUS\r\n"
    ]
    for cmd in commands:
        tx_queue.put(cmd.encode("utf-8"))

    serial_logs.append(f"[MYSQL-SYNC] ⚡ Paramètres MySQL envoyés vers l'ESP32 ({device_id} -> {ssid}).")
    return jsonify({
        "success": True,
        "message": f"Configuration MySQL appliquée à l'ESP32 ({ssid}) !",
        "config": {
            "ssid": ssid,
            "mqtt_host": mqtt_host,
            "led_color": cfg.get("led_color")
        }
    })

@app.route("/api/device/config")
def esp32_http_fetch_config():
    device_id = request.args.get("device_id", "F2ED08")
    cfg = mysql_manager.get_device_config(device_id)
    if cfg:
        return jsonify({
            "device_id": cfg["device_id"],
            "name": cfg["device_name"],
            "wifi_ssid": cfg["wifi_ssid"],
            "mqtt_host": cfg["mqtt_host"],
            "mqtt_port": cfg["mqtt_port"],
            "led_color": cfg["led_color"],
            "led_mode": cfg["led_mode"]
        })
    return jsonify({"error": "Device not found"}), 404

# --- SMART HOME MODULES MANAGEMENT API ---
@app.route("/api/modules", methods=["GET"])
def get_all_modules():
    home_id = request.args.get("homeId")
    mods = mysql_manager.list_all_modules(home_id)
    return jsonify({"success": True, "modules": mods, "count": len(mods)})

@app.route("/api/admin/homes", methods=["GET"])
def get_admin_homes():
    homes = mysql_manager.list_all_homes_with_stats()
    return jsonify({"success": True, "homes": homes, "count": len(homes)})

@app.route("/api/customer/claim", methods=["POST"])
def customer_claim_module():
    data = request.json or {}
    claim_code = data.get("claimCode") or data.get("claim_code")
    home_id = data.get("homeId") or data.get("home_id")
    room = data.get("room", "Salon")
    name = data.get("name")

    if not claim_code or not home_id:
        return jsonify({"success": False, "error": "Le code de réclamation et la maison sont obligatoires."}), 400

    ok, res = mysql_manager.client_claim_module(claim_code, home_id, room, name)
    if ok:
        serial_logs.append(f"[CLAIM] 🎉 Module {res.get('id')} réclamé par client pour sa maison {home_id}")
        return jsonify({"success": True, "module": res})
    return jsonify({"success": False, "error": str(res)}), 400

@app.route("/api/admin/homes/create", methods=["POST"])
def admin_create_home():
    data = request.json or {}
    email = data.get("email")
    home_name = data.get("home_name")
    if not email or not home_name:
        return jsonify({"success": False, "error": "Email et nom de maison requis."}), 400
    ok, res = mysql_manager.create_client_home(email, home_name)
    if ok:
        return jsonify({"success": True, "home": res})
    return jsonify({"success": False, "error": str(res)}), 400

@app.route("/api/admin/users_devices", methods=["GET"])
def get_admin_users_devices():
    data = mysql_manager.list_all_users_with_assignments()
    homes = mysql_manager.list_all_homes_with_stats()
    return jsonify({
        "success": True,
        "users": data.get("users", []),
        "unassigned_devices": data.get("unassigned_devices", []),
        "total_users": data.get("total_users", 0),
        "total_devices": data.get("total_devices", 0),
        "available_homes": homes
    })

@app.route("/api/admin/reassign_device", methods=["POST"])
def admin_reassign_device():
    data = request.json or {}
    device_id = data.get("deviceId") or data.get("device_id")
    target_home_id = data.get("targetHomeId") or data.get("target_home_id")
    room = data.get("room", "Salon")

    if not device_id or not target_home_id:
        return jsonify({"success": False, "error": "ID d'appareil et maison cible requis."}), 400

    ok, res = mysql_manager.reassign_device_to_home(device_id, target_home_id, room)
    if ok:
        serial_logs.append(f"[ASSIGNMENT] 🔄 Appareil {device_id} réaffecté à la maison {target_home_id} ({room})")
        return jsonify({"success": True, "assignment": res})
    return jsonify({"success": False, "error": str(res)}), 400

@app.route("/api/modules/add", methods=["POST"])
def add_module():
    data = request.json or {}
    ok, res = mysql_manager.add_new_module(data)
    if ok:
        serial_logs.append(f"[MODULES] ➕ Nouveau module ajouté : {res.get('name')} ({res.get('id')}) dans {res.get('room')}")
        return jsonify({"success": True, "module": res})
    return jsonify({"success": False, "error": str(res)}), 400

@app.route("/api/modules/<device_id>/toggle", methods=["POST"])
def toggle_module(device_id):
    data = request.json or {}
    target_state = data.get("state")
    ok, msg, new_state = mysql_manager.toggle_module_relay(device_id, target_state)
    if ok:
        if device_id == "F2ED08":
            cmd = f"RELAY {1 if new_state else 0}\r\n"
            tx_queue.put(cmd.encode("utf-8"))
            # Reflect on physical RGB LED on the real ESP32 board
            r, g, b = (249, 115, 22) if new_state else (20, 30, 45)
            threading.Thread(target=forward_led_to_esp32_ip, args=(r, g, b), daemon=True).start()
        serial_logs.append(f"[RELAY] ⚡ Module {device_id} commuté -> {'ON' if new_state else 'OFF'}")
        return jsonify({"success": True, "message": msg, "relay_state": new_state})
    return jsonify({"success": False, "error": msg}), 400

@app.route("/api/modules/<device_id>", methods=["DELETE"])
def remove_module(device_id):
    ok, msg = mysql_manager.delete_module(device_id)
    if ok:
        serial_logs.append(f"[MODULES] 🗑️ Module {device_id} supprimé.")
        return jsonify({"success": True, "message": msg})
    return jsonify({"success": False, "error": msg}), 400

@app.route("/api/modules/rooms", methods=["GET"])
def get_rooms():
    home_id = request.args.get("homeId")
    rooms = mysql_manager.get_available_rooms(home_id)
    return jsonify({"success": True, "rooms": rooms})

@app.route("/api/modules/catalog", methods=["GET"])
def get_catalog():
    return jsonify({"success": True, "catalog": mysql_manager.DEVICE_CATALOG})

@app.route("/api/modules/scan", methods=["GET"])
def scan_modules():
    discovered = mysql_manager.scan_lan_for_devices()
    return jsonify({"success": True, "discovered": discovered})

@app.route("/api/disconnect", methods=["POST"])
def disconnect_port():
    global ser, is_connected, connection_error
    with worker_lock:
        if ser and ser.is_open:
            try:
                ser.close()
            except Exception:
                pass
        ser = None
        is_connected = False
        connection_error = "Port déconnecté manuellement."
        serial_logs.append("[SYSTEM] 🔌 Port déconnecté manuellement.")
    return jsonify({"success": True, "connected": False})

@app.route("/api/reboot", methods=["POST"])
def reboot_board():
    global ser, is_connected
    try:
        with worker_lock:
            if ser and ser.is_open:
                ser.dtr = False
                ser.rts = True
                time.sleep(0.15)
                ser.rts = False
                ser.dtr = False
            else:
                temp = serial.Serial()
                temp.port = COM_PORT
                temp.baudrate = BAUD_RATE
                temp.open()
                temp.dtr = False
                temp.rts = True
                time.sleep(0.15)
                temp.rts = False
                temp.dtr = False
                temp.close()

        serial_logs.append("[SYSTEM] 🔄 Redémarrage matériel (Reboot EN/RTS) exécuté avec succès.")
        return jsonify({"success": True, "message": "Signal de redémarrage envoyé avec succès à l'ESP32 !"})
    except Exception as e:
        return jsonify({"success": False, "error": f"Échec du redémarrage : {str(e)}"}), 500

@app.route("/api/wifi/scan")
def wifi_scan():
    networks = []
    try:
        result = subprocess.run(["netsh", "wlan", "show", "networks", "mode=bssid"],
                                capture_output=True, text=True, encoding="cp850", errors="replace")
        current_ssid = None
        current_signal = 75
        current_auth = "WPA2/WPA3"

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID") and ":" in line:
                parts = line.split(":", 1)
                ssid_name = parts[1].strip()
                if ssid_name and not ssid_name.startswith("ESP32-RGB"):
                    current_ssid = ssid_name
            elif "Authentification" in line or "Authentication" in line:
                if ":" in line:
                    current_auth = line.split(":", 1)[1].strip()
            elif "Signal" in line:
                if ":" in line:
                    sig_str = line.split(":", 1)[1].strip().replace("%", "")
                    try:
                        current_signal = int(sig_str)
                    except ValueError:
                        current_signal = 70
                    if current_ssid and not any(n["ssid"] == current_ssid for n in networks):
                        is_5g = "5G" in current_ssid.upper()
                        networks.append({
                            "ssid": current_ssid,
                            "signal": current_signal,
                            "auth": current_auth,
                            "is_5g": is_5g,
                            "compatible": not is_5g
                        })
                        current_ssid = None
    except Exception as e:
        networks = [{"ssid": "Erreur scan: " + str(e), "signal": 0, "auth": "N/A", "is_5g": False, "compatible": True}]

    if not networks:
        networks = [
            {"ssid": "SWEET-HOME", "signal": 95, "auth": "WPA3-Personnel", "is_5g": False, "compatible": True},
            {"ssid": "SWEET-HOME-5G", "signal": 88, "auth": "WPA3-Personnel", "is_5g": True, "compatible": False}
        ]

    return jsonify({"networks": networks})

@app.route("/api/wifi/configure", methods=["POST"])
def wifi_configure():
    global current_wifi
    data = request.json or {}
    ssid = data.get("ssid", "").strip()
    password = data.get("password", "").strip()
    device_id = data.get("deviceId", "F2ED08").strip()
    secret = data.get("secret", "").strip()

    if not ssid:
        return jsonify({"success": False, "error": "Le SSID est obligatoire"}), 400

    current_wifi["target_ssid"] = ssid
    current_wifi["state"] = "connecting"

    commands = [
        f"WIFI {ssid} {password}\r\n",
        f"DEVICE {device_id} {secret}\r\n",
        "STATUS\r\n"
    ]

    for cmd in commands:
        tx_queue.put(cmd.encode("utf-8"))

    serial_logs.append(f"[CONFIG] Envoi des identifiants Wi-Fi pour '{ssid}'...")
    return jsonify({
        "success": True,
        "message": f"Identifiants pour '{ssid}' envoyés à la carte !"
    })

@app.route("/api/wifi/set_state", methods=["POST"])
def set_wifi_state_manual():
    global current_wifi
    data = request.json or {}
    state = data.get("state", "connected")
    ssid = data.get("ssid", "SWEET-HOME")
    ip = data.get("ip", "192.168.1.105")

    current_wifi["state"] = state
    current_wifi["ssid"] = ssid if state == "connected" else None
    current_wifi["ip"] = ip if state == "connected" else "192.168.4.1"

    serial_logs.append(f"[WIFI-STATUS] État mis à jour : {state} (SSID: {current_wifi['ssid']}, IP: {current_wifi['ip']})")
    return jsonify({"success": True, "wifi": current_wifi})

@app.route("/api/serial/logs")
def get_logs():
    return jsonify({"logs": serial_logs, "connected": is_connected})

@app.route("/api/serial/send", methods=["POST"])
def send_command():
    data = request.json or {}
    cmd = data.get("command", "").strip()
    if not cmd:
        return jsonify({"success": False, "error": "Commande vide"}), 400

    tx_queue.put((cmd + "\r\n").encode("utf-8"))
    serial_logs.append(f"[SEND] > {cmd}")
    return jsonify({"success": True, "sent": cmd})

def forward_led_to_esp32_ip(r, g, b):
    ip = current_wifi.get("ip")
    if ip and current_wifi.get("state") == "connected" and ip != "192.168.4.1":
        try:
            import urllib.request
            url = f"http://{ip}/api/led?r={r}&g={g}&b={b}"
            urllib.request.urlopen(url, timeout=0.8)
        except Exception:
            pass

@app.route("/api/led/set", methods=["POST"])
def set_led():
    data = request.json or {}
    r = data.get("r", 0)
    g = data.get("g", 0)
    b = data.get("b", 0)
    mode = data.get("mode", "solid")

    cmd = f"LED {r} {g} {b} {mode}\r\n"
    tx_queue.put(cmd.encode("utf-8"))
    threading.Thread(target=forward_led_to_esp32_ip, args=(r, g, b), daemon=True).start()
    serial_logs.append(f"[LED] Couleur définie: RGB({r},{g},{b}) Mode:{mode}")
    return jsonify({"success": True, "r": r, "g": g, "b": b, "mode": mode})

@app.route("/api/led/network_state", methods=["POST"])
def set_network_state_led():
    data = request.json or {}
    state = data.get("state", "connected")

    states_map = {
        "connecting": {"r": 0, "g": 100, "b": 255, "mode": "breathe", "desc": "Bleu pulsé (Connexion Wi-Fi...)"},
        "connected":  {"r": 0, "g": 255, "b": 50,  "mode": "solid",   "desc": "Vert fixe (Connecté au Wi-Fi & MQTT)"},
        "ap_mode":    {"r": 255, "g": 120, "b": 0, "mode": "solid",   "desc": "Orange fixe (Mode Portail Captif AP)"},
        "error":      {"r": 255, "g": 0,   "b": 0, "mode": "solid",   "desc": "Rouge fixe (Erreur Wi-Fi / Déconnecté)"},
        "off":        {"r": 0,   "g": 0,   "b": 0, "mode": "solid",   "desc": "Éteint"}
    }

    cfg = states_map.get(state, states_map["connected"])
    cmd = f"LED {cfg['r']} {cfg['g']} {cfg['b']} {cfg['mode']}\r\n"
    tx_queue.put(cmd.encode("utf-8"))
    threading.Thread(target=forward_led_to_esp32_ip, args=(cfg["r"], cfg["g"], cfg["b"]), daemon=True).start()
    serial_logs.append(f"[LED-STATUS] État réseau '{state}' : {cfg['desc']}")
    return jsonify({"success": True, "state": state, "config": cfg})

@app.route("/api/compile_and_upload", methods=["POST"])
def compile_and_upload():
    global ser, is_connected, worker_paused
    data = request.json or {}
    fname = data.get("file", "esp32_smartpower_dashboard.ino")
    fqbn = data.get("fqbn", "esp32:esp32:esp32")

    cli_path = r"C:\Users\yassin\Desktop\SmartPower\tools\arduino-cli\arduino-cli.exe"
    if not os.path.exists(cli_path):
        return jsonify({"success": False, "error": "arduino-cli non trouvé"}), 500

    sketch_path = SKETCHES.get(fname)
    if not sketch_path or not os.path.exists(sketch_path):
        return jsonify({"success": False, "error": f"Fichier sketch '{fname}' introuvable"}), 404

    sketch_dir = os.path.dirname(sketch_path)

    worker_paused = True
    try:
        # 1. Temporarily release COM7
        with worker_lock:
            if ser is not None:
                try:
                    ser.dtr = False
                    ser.rts = False
                    time.sleep(0.05)
                    ser.close()
                except Exception:
                    pass
                ser = None
            is_connected = False
        time.sleep(0.5)

        serial_logs.append(f"[BUILD] 🚀 Début de la compilation de {fname} ({fqbn})...")

        # 2. Compile and upload command
        cmd = [
            cli_path, "compile",
            "--fqbn", fqbn,
            "--upload",
            "--port", COM_PORT,
            sketch_dir
        ]

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        success = res.returncode == 0
        output = (res.stdout + "\n" + res.stderr).strip()

        if success:
            serial_logs.append(f"[BUILD] ✅ Téléversement réussi sur {COM_PORT} !")
        else:
            serial_logs.append(f"[BUILD] ❌ Échec de compilation/téléversement.")

        return jsonify({
            "success": success,
            "output": output,
            "message": "Compilation & Téléversement réussis sur l'ESP32 !" if success else "Échec de compilation ou de téléversement."
        })
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Délai de compilation dépassé (5 minutes)"}), 504
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        worker_paused = False

@app.route("/api/flash", methods=["POST"])
def flash_firmware():
    global ser, is_connected
    if "file" not in request.files:
        return jsonify({"success": False, "error": "Aucun fichier binaire fourni"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "Nom de fichier invalide"}), 400

    save_path = os.path.join(os.environ.get("TEMP", "."), "firmware_upload.bin")
    file.save(save_path)

    with worker_lock:
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass
            ser = None
        is_connected = False

    time.sleep(0.5)

    try:
        cmd = [
            sys.executable, "-m", "esptool",
            "--port", COM_PORT,
            "--baud", "460800",
            "--before", "default-reset",
            "--after", "hard-reset",
            "write-flash", "0x10000", save_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        success = res.returncode == 0
        output = res.stdout + "\n" + res.stderr
        return jsonify({
            "success": success,
            "output": output,
            "message": "Flash réussi !" if success else "Échec du flash. Maintenez le bouton BOOT si nécessaire."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()
    print(f"[*] Dashboard SmartPower ESP32 démarré sur http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
