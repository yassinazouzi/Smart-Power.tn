"""
SmartPower MQTT Broker & Service Engine
---------------------------------------
Fournit un serveur (Broker) MQTT intégré haute performance (port 1883)
et un client MQTT pub/sub bidirectionnel synchronisé avec MySQL et le Dashboard.
"""

import asyncio
import threading
import time
import json
import logging
from amqtt.broker import Broker
import paho.mqtt.client as paho_mqtt

# Configurer le logging MQTT
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartPower-MQTT")

BROKER_PORT = 1883
WS_PORT = 9001

broker_instance = None
broker_loop = None
broker_running = False
broker_error = None

mqtt_client = None
mqtt_stats = {
    "broker_active": False,
    "broker_port": BROKER_PORT,
    "ws_port": WS_PORT,
    "messages_received": 0,
    "messages_sent": 0,
    "last_topic": None,
    "last_payload": None,
    "connected_devices": set()
}

_message_callbacks = []

def register_mqtt_message_listener(callback):
    """Permet aux autres modules (Flask app, WebSocket) d'écouter les messages MQTT entrants."""
    _message_callbacks.append(callback)

def start_embedded_broker(bind_host="0.0.0.0", port=BROKER_PORT):
    global broker_instance, broker_loop, broker_running, broker_error, mqtt_stats

    broker_config = {
        'listeners': {
            'default': {
                'type': 'tcp',
                'bind': f'{bind_host}:{port}',
                'max_connections': 100
            },
            'ws': {
                'type': 'ws',
                'bind': f'{bind_host}:{WS_PORT}',
                'max_connections': 50
            }
        },
        'sys_interval': 0,
        'auth': {
            'allow-anonymous': True
        }
    }

    def _broker_worker():
        global broker_loop, broker_instance, broker_running, broker_error
        try:
            broker_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(broker_loop)
            broker_instance = Broker(broker_config, loop=broker_loop)
            broker_loop.run_until_complete(broker_instance.start())
            broker_running = True
            mqtt_stats["broker_active"] = True
            logger.info(f"[MQTT] ✅ Serveur Broker démarré sur TCP 0.0.0.0:{port} et WebSocket {WS_PORT}")
            broker_loop.run_forever()
        except Exception as e:
            broker_running = False
            broker_error = str(e)
            mqtt_stats["broker_active"] = False
            logger.warning(f"[MQTT] ⚠️ Serveur Broker n'a pas pu démarrer (port {port} peut-être déjà occupé): {e}")

    thread = threading.Thread(target=_broker_worker, daemon=True, name="MQTTBrokerThread")
    thread.start()
    time.sleep(0.8)

def init_mqtt_client(broker_host="127.0.0.1", broker_port=BROKER_PORT):
    global mqtt_client

    def on_connect(client, userdata, flags, rc, properties=None):
        logger.info(f"[MQTT-CLIENT] Connecté au Broker (code {rc})")
        client.subscribe("smartpower/#")
        logger.info("[MQTT-CLIENT] Abonné aux topics 'smartpower/#'")

    def on_message(client, userdata, msg):
        global mqtt_stats
        mqtt_stats["messages_received"] += 1
        mqtt_stats["last_topic"] = msg.topic
        payload_str = msg.payload.decode("utf-8", errors="replace")
        mqtt_stats["last_payload"] = payload_str

        # Déduire le deviceId depuis le topic: smartpower/<deviceId>/...
        parts = msg.topic.split('/')
        if len(parts) >= 2:
            dev_id = parts[1]
            mqtt_stats["connected_devices"].add(dev_id)

        # Notifier les écouteurs enregistrés
        for cb in _message_callbacks:
            try:
                cb(msg.topic, payload_str)
            except Exception as e:
                logger.error(f"[MQTT] Erreur callback: {e}")

    try:
        mqtt_client = paho_mqtt.Client(
            paho_mqtt.CallbackAPIVersion.VERSION2,
            client_id="smartpower_core_backend"
        )
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        mqtt_client.connect(broker_host, broker_port, keepalive=60)
        mqtt_client.loop_start()
        logger.info(f"[MQTT] Client backend connecté à {broker_host}:{broker_port}")
    except Exception as e:
        logger.warning(f"[MQTT] Impossible d'initialiser le client interne: {e}")

def publish_mqtt(topic, payload, retain=False):
    global mqtt_client, mqtt_stats
    if mqtt_client:
        try:
            if isinstance(payload, dict):
                payload = json.dumps(payload)
            mqtt_client.publish(topic, payload, qos=1, retain=retain)
            mqtt_stats["messages_sent"] += 1
            return True
        except Exception as e:
            logger.error(f"[MQTT] Échec publication: {e}")
            return False
    return False

def publish_device_command(device_id, state):
    """Envoie une commande ON/OFF standard à l'équipement en MQTT."""
    topic = f"smartpower/{device_id}/set"
    payload = {"switch": "on" if state else "off", "timestamp": int(time.time())}
    return publish_mqtt(topic, payload)

def get_mqtt_service_status():
    global mqtt_stats, broker_running, broker_error
    return {
        "running": broker_running or (mqtt_client is not None),
        "broker_active": broker_running,
        "broker_port": BROKER_PORT,
        "ws_port": WS_PORT,
        "error": broker_error,
        "messages_received": mqtt_stats["messages_received"],
        "messages_sent": mqtt_stats["messages_sent"],
        "connected_devices": list(mqtt_stats["connected_devices"]),
        "last_topic": mqtt_stats["last_topic"],
        "last_payload": mqtt_stats["last_payload"]
    }
