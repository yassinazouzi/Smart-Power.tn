import pymysql
import json
import uuid
import secrets
import hashlib
import time
import socket
import urllib.request
import urllib.parse
from datetime import datetime

DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",
    "database": "smartpower_dev",
    "port": 3306,
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# Catalog pricing & specs in Tunisian Dinars (TND / DT)
DEVICE_CATALOG = {
    "SP-SW1": {
        "name": "SmartPower Interrupteur 1-Canal",
        "type": "SWITCH",
        "channels": 1,
        "max_amp": 10,
        "price_tnd": 45.000,
        "desc": "Interrupteur encastrable Wi-Fi 10A / 2300W"
    },
    "SP-SW4": {
        "name": "SmartPower Module 4-Canaux DIN",
        "type": "SWITCH_MULTI",
        "channels": 4,
        "max_amp": 16,
        "price_tnd": 89.000,
        "desc": "Tableau électrique rail DIN 4 sorties indépendantes"
    },
    "SP-PLUG-16A": {
        "name": "SmartPower Prise Connectée 16A",
        "type": "PLUG",
        "channels": 1,
        "max_amp": 16,
        "price_tnd": 55.000,
        "desc": "Prise intelligente avec mesure kWh et protection surcharge"
    },
    "SP-TH": {
        "name": "SmartPower Capteur Température & Humidité",
        "type": "SENSOR_TH",
        "channels": 0,
        "max_amp": 0,
        "price_tnd": 39.000,
        "desc": "Capteur d'ambiance ultra basse consommation"
    },
    "SP-DIM-1": {
        "name": "SmartPower Variateur Triac",
        "type": "DIMMER",
        "channels": 1,
        "max_amp": 5,
        "price_tnd": 49.000,
        "desc": "Variateur d'intensité lumineuse pour ampoules LED dimmables"
    },
    "SP-RGB-LED": {
        "name": "SmartPower Contrôleur LED RGB",
        "type": "RGB_LIGHT",
        "channels": 3,
        "max_amp": 6,
        "price_tnd": 59.000,
        "desc": "Contrôleur Wi-Fi pour ruban LED WS2812 / 12V 5050"
    }
}

DEVICE_IP_MAP = {
    "F2ED08": "192.168.0.119",
}

def get_connection():
    try:
        return pymysql.connect(**DB_CONFIG)
    except Exception:
        return None

def init_db():
    conn = get_connection()
    if not conn:
        return False, "Impossible de se connecter au serveur MySQL WAMP (port 3306)."
    try:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS esp32_device_configs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                device_id VARCHAR(64) UNIQUE NOT NULL,
                device_name VARCHAR(191) DEFAULT 'SmartPower ESP32',
                wifi_ssid VARCHAR(191) DEFAULT 'SWEET-HOME',
                wifi_password VARCHAR(191) DEFAULT '',
                mqtt_host VARCHAR(191) DEFAULT '192.168.1.10',
                mqtt_port INT DEFAULT 1883,
                led_color VARCHAR(32) DEFAULT '#22C55E',
                led_mode VARCHAR(32) DEFAULT 'solid',
                relay_state TINYINT(1) DEFAULT 0,
                ip_address VARCHAR(64) DEFAULT NULL,
                notes TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """)

            try:
                cur.execute("ALTER TABLE esp32_device_configs ADD COLUMN ip_address VARCHAR(64) DEFAULT NULL")
            except Exception:
                pass

            conn.commit()
        conn.close()
        return True, "Base de données initialisée avec succès."
    except Exception as e:
        return False, str(e)

def get_device_config(device_id="F2ED08"):
    conn = get_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM esp32_device_configs WHERE device_id = %s", (device_id,))
            row = cur.fetchone()
        conn.close()
        return row
    except Exception:
        return None

def save_device_config(data):
    conn = get_connection()
    if not conn:
        return False, "MySQL non connecté"
    try:
        device_id = data.get("device_id", "F2ED08")
        name = data.get("device_name", "ESP32 Device")
        ssid = data.get("wifi_ssid", "SWEET-HOME")
        password = data.get("wifi_password", "")
        mqtt_host = data.get("mqtt_host", "192.168.1.10")
        mqtt_port = int(data.get("mqtt_port", 1883))
        led_color = data.get("led_color", "#22C55E")
        led_mode = data.get("led_mode", "solid")
        ip_addr = data.get("ip_address", DEVICE_IP_MAP.get(device_id))

        with conn.cursor() as cur:
            cur.execute("""
            INSERT INTO esp32_device_configs 
            (device_id, device_name, wifi_ssid, wifi_password, mqtt_host, mqtt_port, led_color, led_mode, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                device_name = VALUES(device_name),
                wifi_ssid = VALUES(wifi_ssid),
                wifi_password = IF(VALUES(wifi_password) != '', VALUES(wifi_password), wifi_password),
                mqtt_host = VALUES(mqtt_host),
                mqtt_port = VALUES(mqtt_port),
                led_color = VALUES(led_color),
                led_mode = VALUES(led_mode),
                ip_address = COALESCE(VALUES(ip_address), ip_address),
                updated_at = NOW()
            """, (device_id, name, ssid, password, mqtt_host, mqtt_port, led_color, led_mode, ip_addr))
            conn.commit()
        conn.close()
        return True, "Configuration sauvegardée dans MySQL"
    except Exception as e:
        return False, str(e)

# --- MULTI-TENANT / CLIENTS & MAISONS CONNECTÉES ---

def list_all_homes_with_stats():
    """
    Returns all homes registered in Tunisia with owner information, device counts, and online stats (for Super-Admin).
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("""
            SELECT 
                h.id AS home_id,
                h.name AS home_name,
                h.currency,
                h.tariffPerKwh,
                h.createdAt,
                u.id AS owner_id,
                u.email AS owner_email,
                (SELECT COUNT(*) FROM sp_devices d WHERE d.homeId = h.id) AS total_devices,
                (SELECT COUNT(*) FROM sp_devices d WHERE d.homeId = h.id AND d.online = 1) AS online_devices,
                (SELECT COUNT(*) FROM sp_rooms r WHERE r.homeId = h.id) AS room_count
            FROM sp_homes h
            LEFT JOIN sp_home_members m ON h.id = m.homeId AND m.role = 'OWNER'
            LEFT JOIN sp_users u ON m.userId = u.id
            ORDER BY h.createdAt DESC
            """)
            rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print("[list_all_homes_with_stats error]", e)
        return []

def get_available_rooms(home_id=None):
    conn = get_connection()
    if not conn:
        return ["Salon", "Chambre", "Cuisine", "Bureau", "Salle de bain", "Jardin"]
    try:
        with conn.cursor() as cur:
            if home_id and home_id != "all":
                cur.execute("SELECT DISTINCT name FROM sp_rooms WHERE homeId = %s ORDER BY sort ASC, name ASC", (home_id,))
            else:
                cur.execute("SELECT DISTINCT name FROM sp_rooms ORDER BY name ASC")
            rows = cur.fetchall()
        conn.close()
        names = [r["name"] for r in rows if r["name"]]
        return names if names else ["Salon", "Chambre", "Cuisine", "Bureau", "Jardin"]
    except Exception:
        return ["Salon", "Chambre", "Cuisine", "Bureau", "Jardin"]

def list_all_modules(home_id=None):
    """
    Returns smart home devices.
    If home_id is passed and != 'all', filters strictly for that client's home.
    If home_id is 'all' or None, returns all devices for Super-Admin view.
    """
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            sql = """
            SELECT 
                d.id,
                COALESCE(d.name, c.device_name, d.id) AS name,
                d.type,
                COALESCE(d.model, 'SP-SW1') AS model,
                d.channels,
                d.online,
                d.lastSeenAt,
                d.state,
                d.claimCode,
                d.firmware,
                d.homeId,
                d.roomId,
                h.name AS home_name,
                u.email AS owner_email,
                r.name AS room_name,
                c.wifi_ssid,
                c.ip_address,
                c.led_color
            FROM sp_devices d
            LEFT JOIN sp_rooms r ON d.roomId = r.id
            LEFT JOIN sp_homes h ON d.homeId = h.id
            LEFT JOIN sp_home_members m ON h.id = m.homeId AND m.role = 'OWNER'
            LEFT JOIN sp_users u ON m.userId = u.id
            LEFT JOIN esp32_device_configs c ON d.id = c.device_id
            """
            params = []
            if home_id and home_id != "all":
                sql += " WHERE d.homeId = %s"
                params.append(home_id)
            sql += " ORDER BY d.createdAt DESC"

            cur.execute(sql, tuple(params))
            raw_modules = cur.fetchall()
        conn.close()

        modules = []
        for row in raw_modules:
            dev_id = row["id"]
            model = row.get("model") or "SP-SW1"
            catalog_item = DEVICE_CATALOG.get(model, DEVICE_CATALOG.get("SP-SW1"))

            # Parse JSON state
            raw_state = row.get("state")
            state_dict = {}
            if isinstance(raw_state, str):
                try:
                    state_dict = json.loads(raw_state)
                except Exception:
                    state_dict = {}
            elif isinstance(raw_state, dict):
                state_dict = raw_state

            # Compute relay switch state
            relay_active = False
            if "switch" in state_dict:
                relay_active = (str(state_dict["switch"]).lower() == "on")
            elif "switches" in state_dict and isinstance(state_dict["switches"], list):
                relay_active = any(str(s.get("switch", "")).lower() == "on" for s in state_dict["switches"])

            # Power metrics
            power_w = float(state_dict.get("power", 0.0))
            voltage_v = float(state_dict.get("voltage", 230.0))
            current_a = float(state_dict.get("current", 0.0))
            temp_c = state_dict.get("temperature")
            humidity_pct = state_dict.get("humidity")
            battery_pct = state_dict.get("battery")

            ip_addr = row.get("ip_address") or DEVICE_IP_MAP.get(dev_id)

            modules.append({
                "id": dev_id,
                "name": row.get("name") or f"Module {dev_id}",
                "type": row.get("type") or "SWITCH",
                "model": model,
                "model_name": catalog_item["name"],
                "desc": catalog_item["desc"],
                "channels": row.get("channels") or catalog_item["channels"],
                "home_id": row.get("homeId"),
                "home_name": row.get("home_name") or "Maison Principale",
                "owner_email": row.get("owner_email") or "admin@smartpower.tn",
                "room": row.get("room_name") or "Non assigné",
                "online": bool(row.get("online")),
                "relay_state": relay_active,
                "state": state_dict,
                "power_watts": power_w,
                "voltage": voltage_v,
                "current_amp": current_a,
                "temperature": temp_c,
                "humidity": humidity_pct,
                "battery": battery_pct,
                "price_tnd": catalog_item["price_tnd"],
                "ip": ip_addr,
                "claim_code": row.get("claimCode") or f"{dev_id}CL",
                "firmware": row.get("firmware") or "1.4.0",
                "wifi_ssid": row.get("wifi_ssid") or "SWEET-HOME"
            })
        return modules
    except Exception as e:
        print("[list_all_modules error]", e)
        return []

def add_new_module(data):
    """
    Creates and registers a new module in sp_devices and esp32_device_configs.
    Supports assigning directly to a specific client home (homeId).
    """
    conn = get_connection()
    if not conn:
        return False, "MySQL non accessible."

    try:
        dev_id = (data.get("id") or "").strip()
        if not dev_id:
            dev_id = "sp" + secrets.token_hex(5)

        name = (data.get("name") or f"SmartPower {dev_id}").strip()
        m_type = data.get("type", "SWITCH").upper()
        model = data.get("model", "SP-SW1")
        if model not in DEVICE_CATALOG:
            type_to_model = {
                "SWITCH": "SP-SW1",
                "PLUG": "SP-PLUG-16A",
                "SWITCH_MULTI": "SP-SW4",
                "SENSOR_TH": "SP-TH",
                "DIMMER": "SP-DIM-1",
                "RGB_LIGHT": "SP-RGB-LED"
            }
            model = type_to_model.get(m_type, "SP-SW1")

        cat_info = DEVICE_CATALOG[model]
        room_name = (data.get("room") or "Salon").strip()
        home_id = (data.get("home_id") or data.get("homeId") or "").strip()
        ip_addr = (data.get("ip") or "").strip()
        if ip_addr:
            DEVICE_IP_MAP[dev_id] = ip_addr

        claim_code = (data.get("claim_code") or f"{dev_id}CL").upper()
        raw_secret = f"secret_{dev_id}_{secrets.token_hex(4)}"
        secret_hash = "$2a$10$" + hashlib.sha256(raw_secret.encode()).hexdigest()[:53]

        with conn.cursor() as cur:
            # If home_id not provided or 'all', pick first home
            if not home_id or home_id == "all":
                cur.execute("SELECT id FROM sp_homes LIMIT 1")
                h_row = cur.fetchone()
                home_id = h_row["id"] if h_row else "home_" + uuid.uuid4().hex[:16]

            # Get or create roomId in this home
            cur.execute("SELECT id FROM sp_rooms WHERE homeId = %s AND name = %s LIMIT 1", (home_id, room_name))
            r_row = cur.fetchone()
            if not r_row:
                room_id = "room_" + uuid.uuid4().hex[:16]
                cur.execute("INSERT INTO sp_rooms (id, homeId, name, icon, sort) VALUES (%s, %s, %s, 'sofa', 0)", (room_id, home_id, room_name))
            else:
                room_id = r_row["id"]

            init_state = {"switch": "off"}
            if m_type == "PLUG":
                init_state = {"switch": "off", "power": 0, "voltage": 230.0, "current": 0}
            elif m_type == "SWITCH_MULTI":
                init_state = {"switches": [{"ch": i, "switch": "off"} for i in range(cat_info["channels"])]}
            elif m_type == "SENSOR_TH":
                init_state = {"temperature": 23.5, "humidity": 48, "battery": 95}

            cur.execute("""
            INSERT INTO sp_devices 
                (id, secretHash, claimCode, type, model, channels, firmware, homeId, roomId, name, online, lastSeenAt, state, createdAt, claimedAt)
            VALUES 
                (%s, %s, %s, %s, %s, %s, '1.4.0', %s, %s, %s, 1, NOW(), %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                type = VALUES(type),
                model = VALUES(model),
                channels = VALUES(channels),
                roomId = VALUES(roomId),
                homeId = VALUES(homeId),
                online = 1,
                lastSeenAt = NOW()
            """, (dev_id, secret_hash, claim_code, m_type, model, cat_info["channels"], home_id, room_id, name, json.dumps(init_state)))

            cur.execute("""
            INSERT INTO esp32_device_configs 
                (device_id, device_name, wifi_ssid, mqtt_host, ip_address, notes)
            VALUES 
                (%s, %s, 'SWEET-HOME', '192.168.1.10', %s, %s)
            ON DUPLICATE KEY UPDATE
                device_name = VALUES(device_name),
                ip_address = COALESCE(VALUES(ip_address), ip_address),
                notes = VALUES(notes),
                updated_at = NOW()
            """, (dev_id, name, ip_addr if ip_addr else None, f"Module type {m_type} ({model}) - Prix catalogue: {cat_info['price_tnd']} DT"))

            conn.commit()
        conn.close()
        return True, {
            "id": dev_id,
            "name": name,
            "type": m_type,
            "model": model,
            "room": room_name,
            "home_id": home_id,
            "price_tnd": cat_info["price_tnd"],
            "claim_code": claim_code
        }
    except Exception as e:
        return False, str(e)

def client_claim_module(claim_code, home_id, room_name="Salon", custom_name=None):
    """
    The easiest client claiming wizard:
    Client enters the claim code on the box/sticker (ex: F2ED08CL), selects room, and names it.
    Attaches the device to the client's home!
    """
    conn = get_connection()
    if not conn:
        return False, "MySQL non accessible."

    code_clean = (claim_code or "").strip().upper()
    if not code_clean:
        return False, "Veuillez saisir le code de réclamation (QR / Sticker)."

    try:
        with conn.cursor() as cur:
            # 1. Look up device by claimCode or id
            cur.execute("SELECT * FROM sp_devices WHERE claimCode = %s OR id = %s LIMIT 1", (code_clean, code_clean.replace("CL", "")))
            dev = cur.fetchone()

            dev_id = dev["id"] if dev else code_clean.replace("CL", "")
            m_name = custom_name if custom_name else (dev["name"] if dev and dev.get("name") else f"Module {dev_id}")
            
            # Detect device type & model from brand / name if fresh
            if dev and dev.get("model"):
                model = dev["model"]
                m_type = dev.get("type", "SWITCH")
            elif "PURIFICATEUR" in m_name.upper() or "AIRPURIFIER" in m_name.upper():
                model = "zhimi.airpurifier"
                m_type = "AIR_PURIFIER"
            elif "LAMPE" in m_name.upper() or "YEELIGHT" in m_name.upper() or "BULB" in m_name.upper():
                model = "yeelight.bulb"
                m_type = "LIGHT_RGB"
            else:
                model = "SP-SW1"
                m_type = "SWITCH"

            # 2. Get or create room in customer's home
            cur.execute("SELECT id FROM sp_rooms WHERE homeId = %s AND name = %s LIMIT 1", (home_id, room_name))
            r_row = cur.fetchone()
            if not r_row:
                room_id = "room_" + uuid.uuid4().hex[:16]
                cur.execute("INSERT INTO sp_rooms (id, homeId, name, icon, sort) VALUES (%s, %s, %s, 'sofa', 0)", (room_id, home_id, room_name))
            else:
                room_id = r_row["id"]

            # 3. Update device to attach to customer's home
            if dev:
                cur.execute("""
                UPDATE sp_devices 
                SET homeId = %s, roomId = %s, name = %s, online = 1, lastSeenAt = NOW(), claimedAt = NOW()
                WHERE id = %s
                """, (home_id, room_id, m_name, dev_id))
            else:
                # If device was fresh out of factory
                raw_secret = f"secret_{dev_id}_{secrets.token_hex(4)}"
                secret_hash = "$2a$10$" + hashlib.sha256(raw_secret.encode()).hexdigest()[:53]
                cur.execute("""
                INSERT INTO sp_devices 
                    (id, secretHash, claimCode, type, model, channels, firmware, homeId, roomId, name, online, lastSeenAt, state, createdAt, claimedAt)
                VALUES 
                    (%s, %s, %s, %s, %s, 1, '1.4.0', %s, %s, %s, 1, NOW(), '{\"switch\":\"off\"}', NOW(), NOW())
                """, (dev_id, secret_hash, code_clean, m_type, model, home_id, room_id, m_name))

            conn.commit()
        conn.close()
        return True, {
            "id": dev_id,
            "name": m_name,
            "room": room_name,
            "home_id": home_id
        }
    except Exception as e:
        return False, str(e)

def create_client_home(email, home_name, city="Tunis"):
    """
    Creates a new customer account and connects their home in Tunisia.
    """
    conn = get_connection()
    if not conn:
        return False, "MySQL non accessible."

    clean_email = email.strip().lower()
    clean_home = home_name.strip()

    try:
        with conn.cursor() as cur:
            # Check if user exists
            cur.execute("SELECT id FROM sp_users WHERE email = %s LIMIT 1", (clean_email,))
            u_row = cur.fetchone()
            if not u_row:
                user_id = "usr_" + uuid.uuid4().hex[:16]
                dummy_hash = "$2a$10$w8T0s3rE4h.47Q3.j4h05u9c4e2v8Y1u"
                cur.execute("INSERT INTO sp_users (id, email, passwordHash, role, createdAt) VALUES (%s, %s, %s, 'CUSTOMER', NOW())", (user_id, clean_email, dummy_hash))
            else:
                user_id = u_row["id"]

            # Create home
            home_id = "home_" + uuid.uuid4().hex[:16]
            cur.execute("""
            INSERT INTO sp_homes (id, name, timezone, currency, tariffPerKwh, createdAt)
            VALUES (%s, %s, 'Africa/Tunis', 'TND', 0.181, NOW())
            """, (home_id, clean_home))

            # Link owner
            cur.execute("""
            INSERT INTO sp_home_members (homeId, userId, role)
            VALUES (%s, %s, 'OWNER')
            """, (home_id, user_id))

            # Create standard default rooms for this home
            for rname in ["Salon", "Chambre", "Cuisine", "Salle de bain"]:
                rid = "room_" + uuid.uuid4().hex[:16]
                cur.execute("INSERT INTO sp_rooms (id, homeId, name, icon, sort) VALUES (%s, %s, %s, 'sofa', 0)", (rid, home_id, rname))

            conn.commit()
        conn.close()
        return True, {"home_id": home_id, "home_name": clean_home, "owner_email": clean_email}
    except Exception as e:
        return False, str(e)

def list_all_users_with_assignments():
    """
    Returns full multi-tenant client and hardware assignment matrix:
    List of users, their homes, and for each home, the list of real connected devices.
    """
    conn = get_connection()
    if not conn:
        return {"users": [], "unassigned_devices": [], "total_users": 0, "total_devices": 0}
    try:
        with conn.cursor() as cur:
            # 1. Fetch all users and homes
            cur.execute("""
            SELECT u.id as user_id, u.email, u.name as user_name, u.role, u.createdAt as user_created,
                   h.id as home_id, h.name as home_name, h.currency, h.tariffPerKwh
            FROM sp_users u
            LEFT JOIN sp_home_members hm ON u.id = hm.userId
            LEFT JOIN sp_homes h ON hm.homeId = h.id
            ORDER BY (u.role = 'ADMIN') DESC, u.email ASC
            """)
            rows = cur.fetchall()

            # 2. Fetch all devices
            cur.execute("""
            SELECT d.id, d.name, d.model, d.type, d.homeId, d.roomId, r.name as room_name,
                   d.online, d.lastSeenAt, d.claimedAt, d.claimCode
            FROM sp_devices d
            LEFT JOIN sp_rooms r ON d.roomId = r.id
            ORDER BY d.claimedAt DESC
            """)
            devices = cur.fetchall()

            dev_by_home = {}
            for d in devices:
                hid = d.get("homeId") or "unassigned"
                if hid not in dev_by_home:
                    dev_by_home[hid] = []
                dev_by_home[hid].append(d)

            user_list = []
            for r in rows:
                hid = r.get("home_id")
                assigned_devs = dev_by_home.get(hid, []) if hid else []
                user_list.append({
                    "user_id": r["user_id"],
                    "email": r["email"],
                    "name": r["user_name"] or r["email"].split("@")[0].capitalize(),
                    "role": r["role"],
                    "home_id": hid,
                    "home_name": r["home_name"] or "Aucune maison",
                    "device_count": len(assigned_devs),
                    "devices": assigned_devs
                })

            unassigned = dev_by_home.get("unassigned", [])
            return {
                "users": user_list,
                "unassigned_devices": unassigned,
                "total_users": len(user_list),
                "total_devices": len(devices)
            }
    except Exception as e:
        print("[DB ERROR] list_all_users_with_assignments:", e)
        return {"users": [], "unassigned_devices": [], "total_users": 0, "total_devices": 0}
    finally:
        conn.close()

def reassign_device_to_home(device_id, target_home_id, room_name="Salon"):
    """
    Reassigns / transfers any hardware device in real life to another client's home in MySQL.
    """
    conn = get_connection()
    if not conn:
        return False, "MySQL non accessible."
    try:
        with conn.cursor() as cur:
            # 1. Verify target home
            cur.execute("SELECT id, name FROM sp_homes WHERE id = %s LIMIT 1", (target_home_id,))
            home_row = cur.fetchone()
            if not home_row:
                return False, f"Maison cible '{target_home_id}' introuvable."

            # 2. Find or create room in target home
            cur.execute("SELECT id FROM sp_rooms WHERE homeId = %s AND name = %s LIMIT 1", (target_home_id, room_name))
            r_row = cur.fetchone()
            if not r_row:
                room_id = "room_" + uuid.uuid4().hex[:16]
                cur.execute("INSERT INTO sp_rooms (id, homeId, name, icon, sort) VALUES (%s, %s, %s, 'sofa', 0)", (room_id, target_home_id, room_name))
            else:
                room_id = r_row["id"]

            # 3. Update device assignment
            cur.execute("""
            UPDATE sp_devices
            SET homeId = %s, roomId = %s, claimedAt = NOW()
            WHERE id = %s
            """, (target_home_id, room_id, device_id))
            conn.commit()

        return True, {
            "device_id": device_id,
            "home_id": target_home_id,
            "home_name": home_row["name"],
            "room": room_name
        }
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_module(device_id):
    conn = get_connection()
    if not conn:
        return False, "MySQL non accessible."
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sp_timers WHERE deviceId = %s", (device_id,))
            cur.execute("DELETE FROM sp_devices WHERE id = %s", (device_id,))
            cur.execute("DELETE FROM esp32_device_configs WHERE device_id = %s", (device_id,))
            conn.commit()
        conn.close()
        if device_id in DEVICE_IP_MAP:
            del DEVICE_IP_MAP[device_id]
        return True, f"Module '{device_id}' supprimé avec succès."
    except Exception as e:
        return False, str(e)

def toggle_module_relay(device_id, target_state=None):
    conn = get_connection()
    if not conn:
        return False, "MySQL non accessible", False

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, type, model, state, (SELECT ip_address FROM esp32_device_configs WHERE device_id = sp_devices.id) as ip FROM sp_devices WHERE id = %s", (device_id,))
            dev = cur.fetchone()
            if not dev:
                conn.close()
                return False, f"Module '{device_id}' introuvable.", False

            raw_state = dev.get("state")
            state_dict = {}
            if isinstance(raw_state, str):
                try:
                    state_dict = json.loads(raw_state)
                except Exception:
                    state_dict = {}
            elif isinstance(raw_state, dict):
                state_dict = raw_state

            current_switch = str(state_dict.get("switch", "off")).lower() == "on"

            if target_state is not None:
                new_switch = bool(target_state)
            else:
                new_switch = not current_switch

            str_new = "on" if new_switch else "off"
            state_dict["switch"] = str_new
            if dev["type"] == "PLUG":
                state_dict["power"] = 1450.0 if new_switch else 0.0
                state_dict["current"] = 6.3 if new_switch else 0.0

            cur.execute("UPDATE sp_devices SET state = %s, online = 1, lastSeenAt = NOW() WHERE id = %s", (json.dumps(state_dict), device_id))
            cur.execute("UPDATE esp32_device_configs SET relay_state = %s, updated_at = NOW() WHERE device_id = %s", (1 if new_switch else 0, device_id))
            conn.commit()
        conn.close()

        ip_addr = dev.get("ip") or DEVICE_IP_MAP.get(device_id)
        if ip_addr:
            try:
                url = f"http://{ip_addr}/zeroconf/switch"
                payload = json.dumps({"switch": str_new, "data": {"switch": str_new}}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=0.6)
            except Exception:
                try:
                    url2 = f"http://{ip_addr}/api/relay?state={1 if new_switch else 0}"
                    urllib.request.urlopen(url2, timeout=0.5)
                except Exception:
                    pass
            # Synchroniser la LED RGB physique sur la carte en temps réel
            try:
                r, g, b = (249, 115, 22) if new_switch else (0, 15, 30)
                urllib.request.urlopen(f"http://{ip_addr}/api/led?r={r}&g={g}&b={b}", timeout=0.5)
            except Exception:
                pass

        return True, f"Relais {str_new.upper()}", new_switch
    except Exception as e:
        return False, str(e), False

def scan_lan_for_devices():
    discovered = []
    candidate_ips = ["192.168.0.119", "192.168.4.1", "192.168.0.105"]

    conn = get_connection()
    dev_map = {}
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                SELECT d.id, d.name, d.claimCode, d.model, d.type, d.homeId, h.name as home_name, u.email as owner_email
                FROM sp_devices d
                LEFT JOIN sp_homes h ON d.homeId = h.id
                LEFT JOIN sp_home_members hm ON (h.id = hm.homeId AND hm.role = 'OWNER')
                LEFT JOIN sp_users u ON hm.userId = u.id
                """)
                for row in cur.fetchall():
                    dev_map[row["id"]] = row
        except Exception:
            pass
        finally:
            conn.close()

    for ip in candidate_ips:
        try:
            req = urllib.request.Request(f"http://{ip}/", headers={"User-Agent": "SmartPower-Scanner"})
            with urllib.request.urlopen(req, timeout=0.45) as response:
                if response.status == 200:
                    html = response.read().decode("utf-8", errors="ignore")
                    dev_id = "F2ED08" if ("F2ED08" in html or ip == "192.168.0.119") else f"ESP_{ip.split('.')[-1]}"
                    claim_code = f"{dev_id}CL"
                    db_info = dev_map.get(dev_id)
                    already_associated = bool(db_info and db_info.get("homeId"))

                    discovered.append({
                        "ip": ip,
                        "id": dev_id,
                        "claim_code": claim_code,
                        "type": db_info["type"] if db_info else "SWITCH",
                        "model": db_info["model"] if db_info else "SP-SW1",
                        "name": db_info["name"] if db_info else f"Module SmartPower ({dev_id})",
                        "status": "Déjà associé" if already_associated else "Prêt à associer",
                        "already_associated": already_associated,
                        "current_home": db_info["home_name"] if db_info else None,
                        "current_owner": db_info["owner_email"] if db_info else None,
                        "signal": "-54 dBm",
                        "latency_ms": 110,
                        "connection": "Wi-Fi LAN" if ip != "192.168.4.1" else "Point d'Accès (AP)"
                    })
        except Exception:
            pass

    return discovered

def set_device_online_status(device_id, is_online):
    """Met à jour le statut en ligne/hors ligne d'un périphérique dans MySQL"""
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE sp_devices SET online = %s, lastSeenAt = NOW() WHERE id = %s", (1 if is_online else 0, device_id))
            conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
