import socket
import subprocess
import re
import time
import threading
import json
import mysql_manager

OUI_DATABASE = {
    "84:46:93": ("Xiaomi", "AIR_PURIFIER", "Purificateur d'air Xiaomi"),
    "50:EC:50": ("Xiaomi", "AIR_PURIFIER", "Purificateur d'air Xiaomi"),
    "04:CF:8C": ("Xiaomi", "SMART_DEVICE", "Équipement Xiaomi Mi"),
    "64:90:C1": ("Xiaomi", "SMART_DEVICE", "Équipement Xiaomi Mi"),
    "7C:49:EB": ("Xiaomi", "SMART_DEVICE", "Équipement Xiaomi Mi"),
    "F0:B4:29": ("Xiaomi", "SMART_DEVICE", "Équipement Xiaomi Mi"),
    "00:15:8D": ("Aqara / Xiaomi", "SENSOR_HUB", "Passerelle / Capteur Aqara"),
    "0C:B8:15": ("Espressif / SmartPower", "ESP32_HUB", "Module SmartPower ESP32"),
    "24:0A:C4": ("Espressif / Sonoff", "SWITCH", "Interrupteur Sonoff DIY"),
    "24:FB:E3": ("Espressif / Sonoff", "SWITCH", "Interrupteur Sonoff Wi-Fi"),
    "EC:FA:BC": ("Sonoff / ITEAD", "SWITCH", "Interrupteur Sonoff Basic"),
    "60:01:94": ("Sonoff / ITEAD", "SWITCH", "Interrupteur Sonoff Basic"),
    "5C:CF:7F": ("Espressif / Sonoff", "SWITCH", "Interrupteur Sonoff Basic"),
    "DC:4F:22": ("Espressif / Sonoff", "SWITCH", "Interrupteur Sonoff Basic"),
    "18:B9:05": ("Espressif Systems", "IOT_MODULE", "Module Espressif IoT"),
    "AC:D5:64": ("Espressif Systems", "IOT_MODULE", "Module Espressif IoT"),
    "24:62:AB": ("Tuya Smart", "SMART_SWITCH", "Interrupteur Tuya / SmartLife"),
    "48:55:19": ("Tuya Smart", "SMART_PLUG", "Prise Connectée Tuya"),
    "D4:A6:51": ("Tuya Smart", "SMART_DEVICE", "Équipement Tuya Smart"),
    "00:17:88": ("Philips Hue", "LIGHT_RGB", "Ampoule Philips Hue"),
    "EC:B5:FA": ("Yeelight", "LIGHT_RGB", "Lampe / Ampoule Yeelight"),
    "B4:60:77": ("Yeelight", "LIGHT_RGB", "Lampe / Plafonnier Yeelight"),
    "58:02:03": ("Xiaomi / Yeelight", "LIGHT_RGB", "Lampe Connectée Xiaomi"),
}

def get_arp_table():
    entries = {}
    try:
        out = subprocess.check_output("arp -a", shell=True, text=True, errors='ignore')
        for line in out.splitlines():
            m = re.search(r'(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F\-]{17})', line.strip())
            if m:
                ip = m.group(1)
                mac = m.group(2).replace('-', ':').upper()
                entries[ip] = mac
    except Exception as e:
        print("ARP error:", e)
    return entries

def get_active_subnets():
    subnets = set()
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                parts = ip.split(".")
                if len(parts) == 4:
                    subnets.add(f"{parts[0]}.{parts[1]}.{parts[2]}")
    except Exception:
        pass
    # Toujours inclure les plages du réseau local Badira et standards
    subnets.update(["172.16.50", "172.16.51", "192.168.0", "192.168.1"])
    return list(subnets)

def ping_subnet_quick():
    """Quick ultra-fast parallel ping sweep using thread pool to populate ARP table."""
    import concurrent.futures
    def ping(ip):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.04)
            s.connect((ip, 54321))
            s.send(b'')
            s.close()
        except:
            pass

    all_ips = []
    for subnet in get_active_subnets():
        for i in range(1, 255):
            all_ips.append(f"{subnet}.{i}")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as executor:
            list(executor.map(ping, all_ips, timeout=0.8))
    except Exception:
        pass

def discover_lan():
    ping_subnet_quick()
    arp_entries = get_arp_table()
    discovered_map = {}

    # 1. miIO UDP Handshake (Xiaomi)
    miio_hello = bytes.fromhex('21310020ffffffffffffffffffffffffffffffffffffffffffffffffffffffff')
    sock_miio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_miio.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock_miio.settimeout(0.8)

    broadcast_addrs = ['255.255.255.255', '192.168.0.255']
    for bcast in broadcast_addrs:
        try:
            sock_miio.sendto(miio_hello, (bcast, 54321))
        except:
            pass

    for ip in arp_entries:
        try:
            sock_miio.sendto(miio_hello, (ip, 54321))
        except:
            pass

    start = time.time()
    while time.time() - start < 1.2:
        try:
            data, addr = sock_miio.recvfrom(2048)
            ip = addr[0]
            if len(data) >= 32 and data[0:2] == b'\x21\x31' and ip not in discovered_map:
                did_hex = data[8:12].hex()
                did_int = int(did_hex, 16)
                mac = arp_entries.get(ip, "Inconnue")
                
                # Check MAC vendor prefix for details
                prefix = mac[:8] if mac != "Inconnue" else ""
                vendor = "Xiaomi"
                dev_type = "AIR_PURIFIER"
                dev_name = f"Purificateur d'air Xiaomi ({ip})"
                icon = "💨"

                discovered_map[ip] = {
                    "id": f"XIAOMI_{did_hex.upper()}",
                    "name": dev_name,
                    "brand": vendor,
                    "type": dev_type,
                    "model": "zhimi.airpurifier (miIO)",
                    "protocol": "miIO UDP 54321",
                    "ip": ip,
                    "mac": mac,
                    "device_id": str(did_int),
                    "icon": icon,
                    "online": True
                }
        except socket.timeout:
            break
        except Exception:
            pass
    sock_miio.close()

    # 2. Yeelight SSDP Discovery
    ssdp_msg = "M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nST: wifi_bulb\r\n\r\n"
    sock_ssdp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock_ssdp.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock_ssdp.settimeout(0.8)
    try:
        sock_ssdp.sendto(ssdp_msg.encode('utf-8'), ('239.255.255.250', 1900))
        start = time.time()
        while time.time() - start < 1.2:
            try:
                data, addr = sock_ssdp.recvfrom(2048)
                ip = addr[0]
                if ip not in discovered_map:
                    text = data.decode(errors='ignore')
                    model = "yeelight.bulb"
                    m_model = re.search(r'model:\s*([^\r\n]+)', text)
                    if m_model:
                        model = m_model.group(1).strip()
                    m_id = re.search(r'id:\s*([^\r\n]+)', text)
                    did = m_id.group(1).strip() if m_id else ip.replace('.', '')
                    
                    discovered_map[ip] = {
                        "id": f"YEELIGHT_{did.replace('0x', '')[-8:].upper()}",
                        "name": f"Lampe Connectée Yeelight ({ip})",
                        "brand": "Xiaomi / Yeelight",
                        "type": "LIGHT_RGB",
                        "model": model,
                        "protocol": "Yeelight SSDP / TCP 55443",
                        "ip": ip,
                        "mac": arp_entries.get(ip, "Inconnue"),
                        "device_id": did,
                        "icon": "💡",
                        "online": True
                    }
            except socket.timeout:
                break
            except Exception:
                pass
    except:
        pass
    finally:
        sock_ssdp.close()

    # 3. Check remaining ARP entries against OUI database
    for ip, mac in arp_entries.items():
        if ip in discovered_map or ip.endswith('.1') or ip.endswith('.255'):
            continue
        prefix = mac[:8]
        if prefix in OUI_DATABASE:
            brand, dev_type, default_name = OUI_DATABASE[prefix]
            icon = "💡" if "LIGHT" in dev_type else ("💨" if "PURIFIER" in dev_type else ("🔌" if "PLUG" in dev_type else "⚡"))
            discovered_map[ip] = {
                "id": f"DEV_{mac.replace(':', '')[-6:]}",
                "name": f"{default_name} ({ip})",
                "brand": brand,
                "type": dev_type,
                "model": f"OUI-{prefix}",
                "protocol": "LAN / ARP Discovery",
                "ip": ip,
                "mac": mac,
                "device_id": mac.replace(':', ''),
                "icon": icon,
                "online": True
            }

    # 4. Check status against MySQL database
    registered_ids = set()
    registered_ips = set()
    try:
        conn = mysql_manager.get_connection()
        if conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM sp_devices")
                for row in cur.fetchall():
                    registered_ids.add(row["id"].upper())
                cur.execute("SELECT ip_address FROM esp32_device_configs WHERE ip_address IS NOT NULL")
                for row in cur.fetchall():
                    registered_ips.add(row["ip_address"])
            conn.close()
    except Exception as e:
        print("DB check error:", e)

    results = []
    for ip, dev in discovered_map.items():
        dev_id = dev["id"].upper()
        # Check if already in DB
        dev["is_registered"] = (dev_id in registered_ids or dev["ip"] in registered_ips or dev["id"].replace("DEV_", "") in registered_ids)
        results.append(dev)

    return results

def register_discovered_device(dev_info, target_home_id="cmvjogkxo0002zcpxv7tixnp1", room_id=None):
    """
    Inserts or claims an auto-discovered device into sp_devices and esp32_device_configs.
    """
    conn = mysql_manager.get_connection()
    if not conn:
        return False, "Impossible de se connecter à MySQL"

    try:
        dev_id = dev_info.get("id", f"DEV_{int(time.time())}")
        name = dev_info.get("name", "Équipement Connecté")
        dev_type = dev_info.get("type", "SWITCH")
        if dev_type == "LIGHT_RGB":
            dev_type = "RGB_LIGHT"
        model = dev_info.get("model", "SmartDevice")
        ip = dev_info.get("ip", "")
        brand = dev_info.get("brand", "Xiaomi")

        # Pick default room if none
        with conn.cursor() as cur:
            if not room_id:
                cur.execute("SELECT id FROM sp_rooms WHERE homeId = %s LIMIT 1", (target_home_id,))
                room = cur.fetchone()
                if room:
                    room_id = room["id"]

            state_data = {
                "switch": "on",
                "ip": ip,
                "brand": brand,
                "online": True
            }
            if dev_type == "AIR_PURIFIER":
                state_data.update({"pm25": 14, "mode": "auto", "favorite_level": 3})
            elif dev_type in ["RGB_LIGHT", "LIGHT_RGB"]:
                state_data.update({"brightness": 80, "rgb": "#FFA500"})

            cur.execute("""
            INSERT INTO sp_devices 
                (id, secretHash, claimCode, type, model, channels, firmware, homeId, roomId, name, online, lastSeenAt, state, createdAt, claimedAt)
            VALUES 
                (%s, 'auto_discovered', %s, %s, %s, 1, '1.0.0', %s, %s, %s, 1, NOW(), %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                type = VALUES(type),
                model = VALUES(model),
                online = 1,
                state = VALUES(state),
                lastSeenAt = NOW()
            """, (dev_id, f"CL-{dev_id[-6:]}", dev_type, model, target_home_id, room_id, name, json.dumps(state_data)))

            cur.execute("""
            INSERT INTO esp32_device_configs 
                (device_id, device_name, ip_address, notes)
            VALUES 
                (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                device_name = VALUES(device_name),
                ip_address = VALUES(ip_address)
            """, (dev_id, name, ip, f"Découverte automatique LAN {brand}"))

            conn.commit()

        mysql_manager.DEVICE_IP_MAP[dev_id] = ip
        return True, f"Équipement '{name}' ajouté avec succès au système !"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

if __name__ == '__main__':
    res = discover_lan()
    print("Discovered devices with DB status:")
    for d in res:
        print(f" -> {d['name']} | IP: {d['ip']} | Type: {d['type']} | Registered: {d['is_registered']}")
