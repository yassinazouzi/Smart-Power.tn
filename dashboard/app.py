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
import network_discovery
import mqtt_service

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
    if not port_name:
        return False
    ports = [p.device.upper() for p in serial.tools.list_ports.comports()]
    return port_name.upper() in ports

def get_active_esp_port():
    global COM_PORT
    if check_port_physically_present(COM_PORT):
        return COM_PORT
    for p in serial.tools.list_ports.comports():
        vid = p.vid
        pid = p.pid
        desc = (p.description or "").lower()
        if vid == 0x303A or (vid == 0x10C4 and pid == 0xEA60) or (vid == 0x1A86 and pid == 0x7523):
            COM_PORT = p.device
            return COM_PORT
        if any(k in desc for k in ["cp210", "ch340", "espressif", "usb-serial", "périphérique série usb"]):
            COM_PORT = p.device
            return COM_PORT
    return None

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

        active_port = get_active_esp_port()

        if not active_port:
            if is_connected:
                with worker_lock:
                    if ser is not None:
                        try:
                            ser.close()
                        except Exception:
                            pass
                        ser = None
                    is_connected = False
                    connection_error = "Aucune carte ESP32 détectée sur les ports USB."
                    serial_logs.append("[SYSTEM] ⚠️ Déconnexion : aucune carte ESP32 détectée.")
            time.sleep(1.0)
            continue

        if not is_connected or ser is None:
            try:
                with worker_lock:
                    COM_PORT = active_port
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
                        try:
                            ser.write(cmd_bytes)
                            ser.flush()
                        except Exception:
                            pass
                time.sleep(0.05)
        except Exception:
            pass
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
                            if clean.startswith("[BUTTON]") or clean.startswith("[RELAY]"):
                                is_on = "ON" in clean or "ALLUME" in clean
                                try:
                                    mysql_manager.toggle_module_relay("F2ED08", is_on)
                                except Exception:
                                    pass
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
    dev_id = current_wifi.get("device_id") or "ADA960"
    ip = current_wifi.get("ip")

    # Auto-resolve real active device IP if needed
    if not ip or ip.startswith("192.168.4.") or ip == "192.168.0.119":
        try:
            conn = mysql_manager.get_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT device_id, ip_address, wifi_ssid FROM esp32_device_configs WHERE ip_address IS NOT NULL AND ip_address != '' ORDER BY updated_at DESC LIMIT 1")
                    row = cur.fetchone()
                    if row and row.get("ip_address"):
                        ip = row["ip_address"]
                        dev_id = row["device_id"]
                        current_wifi["ip"] = ip
                        current_wifi["device_id"] = dev_id
                        if row.get("wifi_ssid"):
                            current_wifi["ssid"] = row["wifi_ssid"]
                conn.close()
        except Exception:
            pass

    if not ip:
        ip = "172.16.50.194"
        dev_id = "ADA960"

    ping_ms = None
    http_online = False
    device_rssi = -52
    relay_on = False

    try:
        t0 = time.time()
        req = urllib.request.Request(f"http://{ip}/zeroconf/info", headers={"User-Agent": "SmartPower-LiveCheck"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=1.0) as resp:
            if resp.status == 200:
                http_online = True
                ping_ms = round((time.time() - t0) * 1000, 1)
                try:
                    data = json.loads(resp.read().decode("utf-8"))
                    device_rssi = data.get("rssi", -52)
                    relay_on = (data.get("switch") == "on")
                except Exception:
                    pass
    except Exception:
        try:
            t0 = time.time()
            req = urllib.request.Request(f"http://{ip}/", headers={"User-Agent": "SmartPower-LiveCheck"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=0.8) as resp:
                if resp.status == 200:
                    http_online = True
                    ping_ms = round((time.time() - t0) * 1000, 1)
        except Exception:
            http_online = False

    is_live = (is_connected and port_present) or http_online
    try:
        mysql_manager.set_device_online_status(dev_id, is_live)
    except Exception:
        pass

    # Always ensure relay_on is strictly synchronized with database state
    try:
        conn = mysql_manager.get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT relay_state FROM esp32_device_configs WHERE device_id = %s", (dev_id,))
                row = cur.fetchone()
                if row and row.get("relay_state") is not None:
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
        "chip": "ESP32-S3 (Dual-Core LX7 240MHz + BLE 5.0)",
        "deviceId": dev_id,
        "mac": "b4:3a:45:ad:a9:60" if dev_id == "ADA960" else "0c:b8:15:f2:ed:08",
        "wifi": {
            "ssid": current_wifi.get("ssid") if (http_online or (is_connected and port_present)) else "Non connecté",
            "ip": ip if http_online else None,
            "state": "connected" if http_online else ("serial_only" if (is_connected and port_present) else "disconnected"),
            "rssi": device_rssi if http_online else None
        },
        "relay_gpio": 26,
        "relay_state": relay_on,
        "mqtt": mqtt_service.get_mqtt_service_status(),
        "timestamp": time.strftime("%H:%M:%S")
    })

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

@app.route("/api/mqtt/status", methods=["GET"])
def api_mqtt_status():
    return jsonify({"success": True, "mqtt": mqtt_service.get_mqtt_service_status()})

@app.route("/api/modules/register", methods=["POST"])
def register_ble_module():
    data = request.json or {}
    ok, res = mysql_manager.add_new_module(data)
    if ok:
        dev_id = res.get("id") if isinstance(res, dict) else data.get("id")
        name = res.get("name") if isinstance(res, dict) else data.get("name", dev_id)
        room = res.get("room") if isinstance(res, dict) else data.get("room", "Salon")
        serial_logs.append(f"[BLE-PROVISION] 🎉 Objet sans fil '{name}' ({dev_id}) associé avec succès dans {room} !")
        return jsonify({"success": True, "module": res})
    return jsonify({"success": False, "error": str(res)}), 400


def forward_command_to_sonoff(device_id, state):
    """
    Envoie l'ordre de commutation au module Sonoff physique via HTTP REST (DIY Mode port 8081)
    ou protocole Tasmota / Web (port 80) dès que son adresse IP locale est résolue.
    """
    sonoff_ip = None
    try:
        conn = mysql_manager.get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ip_address FROM esp32_device_configs WHERE device_id = %s", (device_id,))
                row = cur.fetchone()
                if row and row.get("ip_address"):
                    sonoff_ip = row["ip_address"]
            conn.close()
    except Exception:
        pass

    if not sonoff_ip:
        # Scanner automatiquement les IP du sous-réseau local pour détecter l'IP du Sonoff
        try:
            for ip_cand in ["172.16.50.160", "172.16.50.207", "172.16.50.60", "172.16.50.61"]:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.3)
                    if s.connect_ex((ip_cand, 8081)) == 0 or s.connect_ex((ip_cand, 80)) == 0:
                        sonoff_ip = ip_cand
                        s.close()
                        break
                    s.close()
                except Exception:
                    pass
        except Exception:
            pass

    if not sonoff_ip:
        return

    # 1. Envoi REST DIY Mode Sonoff (port 8081 zeroconf)
    try:
        url = f"http://{sonoff_ip}:8081/zeroconf/switch"
        payload = json.dumps({"deviceid": device_id, "data": {"switch": "on" if state else "off"}}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=1.2) as resp:
            if resp.status == 200:
                serial_logs.append(f"[SONOFF-DIY] ⚡ Relais physique commuté via LAN sur {sonoff_ip}:8081")
                return
    except Exception:
        pass

    # 2. Envoi HTTP standard (port 80)
    try:
        url = f"http://{sonoff_ip}/cm?cmnd=Power%20{'ON' if state else 'OFF'}"
        req = urllib.request.Request(url)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=1.0) as resp:
            if resp.status == 200:
                serial_logs.append(f"[SONOFF-HTTP] ⚡ Relais commuté via HTTP sur {sonoff_ip}")
    except Exception:
        pass

@app.route("/api/sonoff/inject_wifi", methods=["POST"])
def inject_sonoff_wifi():
    """Injecte directement les identifiants Wi-Fi dans le point d'accès d'usine du Sonoff (10.10.7.1)"""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    target_ssid = data.get("ssid") or "adminbadira"
    target_pwd = data.get("password") or "Sthh@1245"
    ap_name = data.get("ap_name") or "ITEAD-100076f3fc"

    # 1. Tenter la connexion Windows au Wi-Fi du Sonoff
    try:
        import subprocess
        subprocess.run(f'netsh wlan connect name="{ap_name}"', shell=True, timeout=6)
        time.sleep(3.0)
    except Exception:
        pass

    # 2. Envoi de la requête de configuration HTTP POST vers 10.10.7.1/ap
    success = False
    err_detail = ""
    for attempt in range(3):
        try:
            url = "http://10.10.7.1/ap"
            payload = json.dumps({
                "version": 4,
                "ssid": target_ssid,
                "password": target_pwd,
                "serverName": "172.16.50.138",
                "port": 8080
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=3.0) as resp:
                if resp.status in (200, 204):
                    success = True
                    break
        except Exception as e:
            err_detail = str(e)
            time.sleep(1.0)

    # 3. Reconnexion automatique du PC à sa box Wi-Fi principale
    try:
        subprocess.run('netsh wlan connect name="adminbadira"', shell=True, timeout=6)
    except Exception:
        pass

    if success:
        serial_logs.append(f"[SONOFF-SETUP] 🎉 Identifiants Wi-Fi '{target_ssid}' injectés avec succès dans le Sonoff !")
        return jsonify({"success": True, "message": f"Identifiants Wi-Fi injectés avec succès ! Le Sonoff se connecte à '{target_ssid}'."})
    return jsonify({
        "success": False, 
        "error": f"Le Sonoff n'a pas répondu sur 10.10.7.1 ({err_detail}). Assurez-vous que sa LED clignote rapidement et que vous êtes à proximité."
    }), 400

@app.route("/api/modules/<device_id>/toggle", methods=["POST"])
def toggle_module(device_id):
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    target_state = data.get("state")
    ok, msg, new_state = mysql_manager.toggle_module_relay(device_id, target_state)
    if ok:
        # Commande physique ESP32 (Série COM + HTTP)
        if device_id in ("F2ED08", "ADA960"):
            cmd = f"RELAY {1 if new_state else 0}\r\n"
            tx_queue.put(cmd.encode("utf-8"))
            r, g, b = (249, 115, 22) if new_state else (20, 30, 45)
            threading.Thread(target=forward_led_to_esp32_ip, args=(r, g, b), daemon=True).start()

        # Commande physique Sonoff (Wi-Fi LAN DIY / HTTP)
        if "sonoff" in device_id.lower():
            threading.Thread(target=forward_command_to_sonoff, args=(device_id, new_state), daemon=True).start()

        # Publication MQTT (topics standard SmartPower + Sonoff)
        mqtt_service.publish_device_command(device_id, new_state)
        try:
            mqtt_service.publish(f"cmnd/{device_id}/POWER", "ON" if new_state else "OFF")
            mqtt_service.publish(f"sonoff/{device_id}/set", json.dumps({"switch": "on" if new_state else "off"}))
        except Exception:
            pass

        tag = "[SONOFF]" if "sonoff" in device_id.lower() else "[RELAY]"
        serial_logs.append(f"{tag} ⚡ Module {device_id} commuté -> {'ON' if new_state else 'OFF'}")
        return jsonify({"success": True, "message": msg, "relay_state": new_state})
    return jsonify({"success": False, "error": msg}), 400


# --- DEVICE TIMERS & REMOTE CONTROL SUITE ---
active_device_timers = {}


# --- USER ACCOUNT & CUSTOMIZATION API ---
@app.route("/api/user/account", methods=["GET"])
def get_user_account_api():
    email = request.args.get("email")
    acc = mysql_manager.get_user_account(email)
    if acc:
        return jsonify({"success": True, "account": acc})
    return jsonify({"success": False, "error": "Compte utilisateur introuvable"}), 404

@app.route("/api/user/account", methods=["POST"])
def update_user_account_api():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    user_id = data.get("userId") or data.get("id")
    name = data.get("name")
    email = data.get("email")
    home_name = data.get("homeName") or data.get("home_name")
    if not user_id or not name or not email:
        return jsonify({"success": False, "error": "ID, nom et email sont requis."}), 400
    ok, msg = mysql_manager.update_user_account(user_id, name, email, home_name)
    if ok:
        serial_logs.append(f"[USER] 👤 Compte de {name} ({email}) mis à jour en base SQL.")
        return jsonify({"success": True, "message": msg})
    return jsonify({"success": False, "error": msg}), 500

@app.route("/api/modules/<device_id>/update", methods=["POST"])
def update_module_api(device_id):
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    new_name = data.get("name")
    new_room = data.get("room")
    if not new_name and not new_room:
        return jsonify({"success": False, "error": "Nom ou pièce requis."}), 400
    ok, msg = mysql_manager.update_module_details(device_id, new_name, new_room)
    if ok:
        serial_logs.append(f"[MODULES] ✏️ Module {device_id} renommé -> '{new_name}' (Pièce: {new_room})")
        return jsonify({"success": True, "message": msg, "id": device_id, "name": new_name, "room": new_room})
    return jsonify({"success": False, "error": msg}), 400

@app.route("/api/rooms/create", methods=["POST"])
def create_room_api():
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    home_id = data.get("homeId") or data.get("home_id") or "cmvjogkxo0002zcpxv7tixnp1"
    room_name = data.get("name")
    icon = data.get("icon", "sofa")
    if not room_name:
        return jsonify({"success": False, "error": "Nom de la pièce requis."}), 400
    ok, res = mysql_manager.create_room_in_home(home_id, room_name, icon)
    if ok:
        serial_logs.append(f"[ROOMS] 🚪 Nouvelle pièce '{room_name}' ajoutée dans la maison.")
        return jsonify({"success": True, "room": res})
    return jsonify({"success": False, "error": str(res)}), 400

@app.route("/api/settings", methods=["GET"])
def get_system_settings():
    return jsonify({
        "success": True,
        "mqtt": mqtt_service.get_mqtt_service_status(),
        "wifi": current_wifi,
        "database": {"connected": True, "name": "smartpower_dev", "host": "127.0.0.1:3306"},
        "active_device": current_wifi.get("device_id", "ADA960"),
        "active_ip": current_wifi.get("ip", "172.16.50.194")
    })

@app.route("/api/modules/<device_id>/led", methods=["POST"])
def module_led_control(device_id):
    data = request.json or {}
    r = int(data.get("r", 249))
    g = int(data.get("g", 115))
    b = int(data.get("b", 22))
    mode = data.get("mode", "solid")
    brightness = int(data.get("brightness", 100))
    
    # Scale r, g, b by brightness
    if 0 <= brightness < 100:
        factor = max(0.05, brightness / 100.0)
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
        
    ip = None
    try:
        conn = mysql_manager.get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ip_address FROM esp32_device_configs WHERE device_id = %s", (device_id,))
                row = cur.fetchone()
                if row and row.get("ip_address"):
                    ip = row["ip_address"]
            conn.close()
    except Exception:
        pass
        
    if not ip:
        ip = mysql_manager.DEVICE_IP_MAP.get(device_id) or ("172.16.50.194" if device_id == "ADA960" else None)
        
    forwarded = False
    if ip:
        try:
            req = urllib.request.Request(f"http://{ip}/api/led?r={r}&g={g}&b={b}")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    forwarded = True
        except Exception as e:
            print(f"[LED forward error to {ip}]: {e}")
            
    try:
        tx_queue.put(f"LED {r} {g} {b} {mode}\r\n".encode("utf-8"))
    except Exception:
        pass
        
    try:
        mqtt_service.publish_mqtt_sync(f"smartpower/{device_id}/led", json.dumps({"r": r, "g": g, "b": b, "mode": mode}))
    except Exception:
        pass

    try:
        conn = mysql_manager.get_connection()
        if conn:
            with conn.cursor() as cur:
                hex_col = f"#{r:02x}{g:02x}{b:02x}"
                cur.execute("UPDATE esp32_device_configs SET led_color = %s WHERE device_id = %s", (hex_col, device_id))
                conn.commit()
            conn.close()
    except Exception:
        pass
        
    serial_logs.append(f"[REMOTE-LED] 🎨 LED {device_id} -> RGB({r},{g},{b}) [{mode}] sur {ip or 'Serial'}")
    return jsonify({"success": True, "r": r, "g": g, "b": b, "mode": mode, "forwarded": forwarded, "ip": ip})

@app.route("/api/modules/<device_id>/telemetry", methods=["GET"])
def module_telemetry(device_id):
    ip = None
    name = device_id
    room = "Salon"
    relay_on = False
    try:
        conn = mysql_manager.get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT d.id, d.name, d.state, (SELECT name FROM sp_rooms WHERE id = d.roomId) as room_name,
                           c.ip_address, c.relay_state, c.wifi_ssid
                    FROM sp_devices d
                    LEFT JOIN esp32_device_configs c ON c.device_id = d.id
                    WHERE d.id = %s
                """, (device_id,))
                row = cur.fetchone()
                if row:
                    ip = row.get("ip_address")
                    name = row.get("name") or device_id
                    room = row.get("room_name") or "Salon"
                    relay_on = bool(row.get("relay_state", 0))
            conn.close()
    except Exception:
        pass

    if not ip:
        ip = mysql_manager.DEVICE_IP_MAP.get(device_id) or ("172.16.50.194" if device_id == "ADA960" else None)

    online = False
    rssi = -52
    ping_ms = None
    if ip:
        try:
            t0 = time.time()
            req = urllib.request.Request(f"http://{ip}/zeroconf/info", headers={"User-Agent": "SmartPower-Ping"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:
                if resp.status == 200:
                    online = True
                    ping_ms = round((time.time() - t0) * 1000, 1)
                    data = json.loads(resp.read().decode("utf-8"))
                    rssi = data.get("rssi", -52)
                    raw_switch = data.get("switch", "off")
                    relay_on = (raw_switch == "on")
        except Exception:
            pass

    timer_info = active_device_timers.get(device_id)
    rem_timer = max(0, int(timer_info["end_time"] - time.time())) if timer_info else 0

    return jsonify({
        "success": True,
        "id": device_id,
        "name": name,
        "room": room,
        "ip": ip,
        "online": online,
        "rssi": rssi,
        "ping_ms": ping_ms if ping_ms is not None else 8.2,
        "switch": "on" if relay_on else "off",
        "relay_state": relay_on,
        "timer_remaining_seconds": rem_timer,
        "timer_active": bool(rem_timer > 0)
    })

@app.route("/api/modules/<device_id>/timer", methods=["POST", "GET"])
def module_timer(device_id):
    global active_device_timers
    if request.method == "GET":
        info = active_device_timers.get(device_id)
        if info:
            rem = max(0, int(info["end_time"] - time.time()))
            return jsonify({"success": True, "active": True, "remaining_seconds": rem, "minutes": info["minutes"]})
        return jsonify({"success": True, "active": False, "remaining_seconds": 0})

    data = request.json or {}
    minutes = float(data.get("minutes", 0))

    # Cancel previous timer if any
    if device_id in active_device_timers:
        try:
            active_device_timers[device_id]["timer"].cancel()
        except Exception:
            pass
        del active_device_timers[device_id]

    if minutes <= 0:
        serial_logs.append(f"[TIMER] ⏹️ Minuterie annulée pour {device_id}")
        return jsonify({"success": True, "active": False, "message": "Minuterie annulée avec succès."})

    seconds = minutes * 60.0
    end_time = time.time() + seconds

    def auto_turn_off():
        print(f"[TIMER] ⏰ Minuterie écoulée : extinction automatique de {device_id}")
        try:
            mysql_manager.toggle_module_relay(device_id, target_state=False)
            serial_logs.append(f"[TIMER] ⏰ Minuterie achevée -> {device_id} éteint automatiquement.")
        except Exception as e:
            print(f"[TIMER ERROR]: {e}")
        if device_id in active_device_timers:
            del active_device_timers[device_id]

    t = threading.Timer(seconds, auto_turn_off)
    t.daemon = True
    t.start()

    active_device_timers[device_id] = {
        "end_time": end_time,
        "timer": t,
        "minutes": minutes
    }
    serial_logs.append(f"[TIMER] ⏱️ Extinction de {device_id} programmée dans {int(minutes)} min.")
    return jsonify({
        "success": True,
        "active": True,
        "remaining_seconds": int(seconds),
        "target_timestamp": int(end_time),
        "message": f"Minuterie activée : coupure automatique dans {int(minutes)} minutes."
    })

@app.route("/api/modules/<device_id>/reboot", methods=["POST"])
def module_reboot(device_id):
    try:
        tx_queue.put(b"REBOOT\r\n")
    except Exception:
        pass
    ip = mysql_manager.DEVICE_IP_MAP.get(device_id) or ("172.16.50.194" if device_id == "ADA960" else None)
    if ip:
        try:
            req = urllib.request.Request(f"http://{ip}/api/reboot", data=b"{}")
            urllib.request.urlopen(req, timeout=0.8)
        except Exception:
            pass
    serial_logs.append(f"[REBOOT] 🔄 Commande redémarrage envoyée à {device_id}")
    return jsonify({"success": True, "message": f"Signal de redémarrage envoyé avec succès au module {device_id} !"})


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
    discovered = []
    # 1. First run the real LAN auto-discovery engine (Xiaomi miIO, Yeelight SSDP, ARP OUI)
    try:
        lan_devs = network_discovery.discover_lan()
        for d in lan_devs:
            dev_id = d["id"]
            is_reg = d.get("is_registered", False)
            claim_c = f"CL-{dev_id.replace('DEV_', '').replace('XIAOMI_', '')[-6:]}"
            discovered.append({
                "ip": d["ip"],
                "mac": d.get("mac", ""),
                "id": dev_id,
                "claim_code": claim_c,
                "type": d["type"],
                "model": d["model"],
                "brand": d.get("brand", "Xiaomi"),
                "name": d["name"],
                "status": "Déjà associé" if is_reg else "Nouveau (Prêt à associer)",
                "already_associated": is_reg,
                "signal": "-48 dBm",
                "latency_ms": 14,
                "icon": d.get("icon", "⚡"),
                "connection": d.get("protocol", "Wi-Fi LAN")
            })
    except Exception as e:
        print("[SCAN] Error in network_discovery:", e)

    # 2. Merge with any HTTP scanned devices from mysql_manager
    existing_ips = {d["ip"] for d in discovered}
    for dev in mysql_manager.scan_lan_for_devices():
        if dev["ip"] not in existing_ips:
            discovered.append(dev)

    # 3. Check for nearby Sonoff / ITEAD Soft-AP networks
    try:
        import subprocess
        wlan_out = subprocess.check_output("netsh wlan show networks", shell=True).decode("cp1252", errors="ignore")
        for line in wlan_out.splitlines():
            line_str = line.strip()
            if line_str.startswith("SSID") and ":" in line_str:
                ssid_val = line_str.split(":", 1)[1].strip()
                if ssid_val.upper().startswith("ITEAD-") or "SONOFF" in ssid_val.upper():
                    discovered.append({
                        "ip": "10.10.7.1",
                        "mac": "",
                        "id": f"SONOFF_{ssid_val[-6:]}",
                        "claim_code": f"CL-{ssid_val[-6:]}",
                        "type": "SWITCH",
                        "model": "SONOFF-BASIC-R2",
                        "brand": "Sonoff",
                        "name": f"Module Sonoff ({ssid_val})",
                        "status": "Point d'accès détecté (Prêt pour configuration)",
                        "already_associated": False,
                        "signal": "-38 dBm (Très fort)",
                        "latency_ms": 4,
                        "icon": "⚡",
                        "connection": f"Wi-Fi AP ({ssid_val})"
                    })
    except Exception as e:
        print("[SCAN] Error scanning Wi-Fi networks for Sonoff:", e)

    return jsonify({"success": True, "discovered": discovered})

@app.route("/api/disconnect", methods=["POST"])
def disconnect_port():
    global ser, is_connected, connection_error, worker_paused
    worker_paused = True
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

@app.route("/api/connect", methods=["POST"])
def connect_port():
    global worker_paused
    worker_paused = False
    return jsonify({"success": True, "connected": True})

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
    ip = current_wifi.get("ip") or "172.16.50.194"
    if ip and ip != "192.168.4.1":
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

        # 2. Compile to output-dir
        build_dir = os.path.join(os.path.dirname(sketch_dir), "build")
        os.makedirs(build_dir, exist_ok=True)
        compile_cmd = [
            cli_path, "compile",
            "--fqbn", fqbn,
            "--output-dir", build_dir,
            sketch_dir
        ]

        c_res = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=240)
        if c_res.returncode != 0:
            serial_logs.append(f"[BUILD] ❌ Échec de la compilation.")
            return jsonify({
                "success": False,
                "output": c_res.stdout + "\n" + c_res.stderr,
                "message": "Erreur lors de la compilation."
            }), 400

        serial_logs.append(f"[BUILD] ⚡ Compilation réussie. Téléversement haute vitesse (460 800 bauds)...")

        # 3. Upload via modern esptool
        bin_app = os.path.join(build_dir, f"{fname}.bin")
        bin_boot = os.path.join(build_dir, f"{fname}.bootloader.bin")
        bin_part = os.path.join(build_dir, f"{fname}.partitions.bin")

        chip_type = "esp32s3" if ("s3" in fqbn.lower() or "s3" in fname.lower()) else "esp32"
        boot_offset = "0x0000" if chip_type == "esp32s3" else "0x1000"

        flash_args = [
            sys.executable, "-m", "esptool",
            "--chip", chip_type,
            "--port", COM_PORT,
            "--baud", "460800",
            "--before", "default-reset",
            "--after", "hard-reset",
            "write-flash",
            "--flash-mode", "dio",
            "--flash-freq", "80m",
            "--flash-size", "4MB"
        ]
        if os.path.exists(bin_boot) and os.path.exists(bin_part):
            flash_args.extend([boot_offset, bin_boot, "0x8000", bin_part, "0x10000", bin_app])
        else:
            flash_args.extend(["0x10000", bin_app])

        u_res = subprocess.run(flash_args, capture_output=True, text=True, timeout=60)
        success = u_res.returncode == 0
        output = (c_res.stdout + "\n" + u_res.stdout + "\n" + u_res.stderr).strip()

        if success:
            serial_logs.append(f"[BUILD] ✅ Téléversement réussi sur {COM_PORT} !")
        else:
            serial_logs.append(f"[BUILD] ❌ Échec du téléversement esptool.")

        return jsonify({
            "success": success,
            "output": output,
            "message": "Compilation & Téléversement réussis sur l'ESP32 !" if success else "Échec du téléversement sur la carte."
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

# ==========================================
# LAN AUTO-DISCOVERY (Xiaomi, Yeelight, etc.)
# ==========================================
@app.route("/api/network/discover", methods=["GET"])
def api_network_discover():
    try:
        devices = network_discovery.discover_lan()
        return jsonify({
            "success": True,
            "devices": devices,
            "count": len(devices)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "devices": []}), 500

@app.route("/api/network/add_device", methods=["POST"])
def api_network_add_device():
    try:
        data = request.get_json() or {}
        dev_info = data.get("device")
        if not dev_info:
            return jsonify({"success": False, "error": "Aucune information d'équipement fournie."}), 400
        
        home_id = data.get("homeId", "cmvjogkxo0002zcpxv7tixnp1")
        room_id = data.get("roomId", None)
        success, msg = network_discovery.register_discovered_device(dev_info, target_home_id=home_id, room_id=room_id)
        return jsonify({"success": success, "message": msg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()

    # Démarrage du Broker MQTT local (Port 1883) & Client interne
    try:
        mqtt_service.start_embedded_broker()
        mqtt_service.init_mqtt_client()
        def handle_mqtt_msg(topic, payload_str):
            try:
                parts = topic.split('/')
                if len(parts) >= 3 and parts[2] == 'state':
                    dev_id = parts[1]
                    data = json.loads(payload_str)
                    if "switch" in data:
                        is_on = data["switch"] == "on"
                        mysql_manager.toggle_module_relay(dev_id, is_on)
            except Exception:
                pass
        mqtt_service.register_mqtt_message_listener(handle_mqtt_msg)
    except Exception as me:
        print("[MQTT] Erreur démarrage service MQTT:", me)

    print(f"[*] Dashboard SmartPower ESP32 démarré sur http://localhost:8080")
    app.run(host="0.0.0.0", port=8080, debug=False)
