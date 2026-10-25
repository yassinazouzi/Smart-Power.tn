import os

sketch_path = r"C:\Users\yassin\Desktop\SmartPower\firmware\esp32_smartpower_dashboard\esp32_smartpower_dashboard.ino"

with open(sketch_path, "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update defaults and defines
if "#define LED_BUILTIN_PIN" not in code:
    code = code.replace(
        "#define RELAY_PIN       26    // Broche Relais",
        "#define RELAY_PIN       26    // Broche Relais\n#define LED_BUILTIN_PIN 2     // LED integree sur ESP32 Dev Module"
    )

# 2. Update default broker to broker.hivemq.com (or LAN)
code = code.replace(
    'String mqttHost = "192.168.0.10";',
    'String mqttHost = "broker.hivemq.com";'
)
code = code.replace(
    'mqttHost = prefs.getString("mqtt_host", "192.168.1.10");',
    'mqttHost = prefs.getString("mqtt_host", "broker.hivemq.com");'
)

# 3. Add relay and MQTT functions
relay_and_mqtt = """
void setRelay(bool on) {
    relayState = on;
    digitalWrite(RELAY_PIN, on ? HIGH : LOW);
    digitalWrite(LED_BUILTIN_PIN, on ? HIGH : LOW);
    Serial.printf("[RELAY] Relais sur GPIO %d : %s\\n", RELAY_PIN, on ? "ALLUME (ON)" : "ETEINT (OFF)");
}

void publishState() {
    String stateTopic = "sp/" + deviceId + "/state";
    String payload = "{\\"switch\\":\\"" + String(relayState ? "on" : "off") + "\\"}";
    mqtt.publish(stateTopic.c_str(), payload.c_str(), true);
}

void onMqttCommand(char* t, byte* payload, unsigned int length) {
    JsonDocument doc;
    if (deserializeJson(doc, payload, length)) {
        Serial.println("[MQTT] Erreur parsing JSON");
        return;
    }
    const char* val = doc["switch"];
    if (val) {
        bool on = (strcmp(val, "on") == 0);
        setRelay(on);
        publishState();
    }
}

void connectMqtt() {
    if (WiFi.status() != WL_CONNECTED) return;
    mqtt.setServer(mqttHost.c_str(), mqttPort);
    mqtt.setCallback(onMqttCommand);
    String willTopic = "sp/" + deviceId + "/status";
    String cmdTopic = "sp/" + deviceId + "/cmd";
    Serial.printf("[MQTT] Connexion a %s:%d...\\n", mqttHost.c_str(), mqttPort);
    if (mqtt.connect(deviceId.c_str(), willTopic.c_str(), 1, true, "offline")) {
        mqtt.publish(willTopic.c_str(), "online", true);
        mqtt.subscribe(cmdTopic.c_str(), 1);
        publishState();
        Serial.println("[MQTT] ✅ Connecte avec succes au broker !");
    } else {
        Serial.printf("[MQTT] ⚠️ Echec connexion (etat %d)\\n", mqtt.state());
    }
}
"""

if "void setRelay(bool on)" not in code:
    code = code.replace("void setup() {", relay_and_mqtt + "\nvoid setup() {")

# 4. In setup, initialize LED_BUILTIN_PIN and RELAY_PIN
if "pinMode(LED_BUILTIN_PIN, OUTPUT);" not in code:
    code = code.replace(
        "pinMode(RGB_PIN, OUTPUT);",
        "pinMode(RGB_PIN, OUTPUT);\n    pinMode(RELAY_PIN, OUTPUT);\n    pinMode(LED_BUILTIN_PIN, OUTPUT);\n    digitalWrite(RELAY_PIN, LOW);\n    digitalWrite(LED_BUILTIN_PIN, LOW);"
    )

# 5. Add Sonoff DIY LAN routes
diy_routes = """
    // Sonoff DIY LAN Mode (ZeroConf HTTP Control)
    server.on("/zeroconf/switch", HTTP_POST, []() {
        if (server.hasArg("plain")) {
            JsonDocument doc;
            deserializeJson(doc, server.arg("plain"));
            const char* s = doc["switch"];
            if (s) {
                bool on = (strcmp(s, "on") == 0);
                setRelay(on);
                publishState();
                server.send(200, "application/json", "{\\"error\\":0,\\"switch\\":\\"" + String(on ? "on" : "off") + "\\"}");
                return;
            }
        }
        server.send(400, "application/json", "{\\"error\\":400}");
    });

    server.on("/zeroconf/info", HTTP_GET, []() {
        String json = "{\\"id\\":\\"" + deviceId + "\\",\\"switch\\":\\"" + String(relayState ? "on" : "off") + "\\",\\"rssi\\":" + String(WiFi.RSSI()) + "}";
        server.send(200, "application/json", json);
    });
"""

if "/zeroconf/switch" not in code:
    code = code.replace("server.begin();", diy_routes + "\n    server.begin();")

# 6. In loop, call mqtt loop and connect
mqtt_loop_code = """
    if (WiFi.status() == WL_CONNECTED) {
        if (!mqtt.connected()) {
            unsigned long now = millis();
            if (now - lastMqttRetry > 8000) {
                lastMqttRetry = now;
                connectMqtt();
            }
        } else {
            mqtt.loop();
        }
    }
"""

if "mqtt.loop();" not in code:
    code = code.replace("server.handleClient();", "server.handleClient();\n" + mqtt_loop_code)

with open(sketch_path, "w", encoding="utf-8") as f:
    f.write(code)

print("SKETCH UPGRADED WITH SONOFF ARCHITECTURE & MQTT!")
