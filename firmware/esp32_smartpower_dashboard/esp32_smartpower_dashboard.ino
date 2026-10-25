/*
 * SmartPower — ESP32-S3-Zero Firmware avec Web Dashboard & Portail Captif WiFi
 * 
 * Fonctionnalités intégrées :
 *  1. Portail Captif WiFi (WiFiManager) autonome (AP: ESP32-RGB-XXXXXX à 192.168.4.1)
 *  2. Scan en direct des réseaux Wi-Fi environnants
 *  3. Sauvegarde permanente des identifiants Wi-Fi et MQTT dans la mémoire Flash (NVS)
 *  4. Serveur Web embarqué accessible sur http://smartpower.local ou http://<IP_ESP32>
 *  5. Mise à jour du Firmware sans fil (OTA Web Updater)
 *  6. Contrôle de la LED RGB intégrée (WS2812 sur GPIO 21)
 *  7. Intégration complète au protocole SmartPower MQTT
 */

#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Update.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Définitions matérielles
#define RGB_PIN         21    // LED RGB WS2812 intégrée sur ESP32-S3-Zero
#define RELAY_PIN       26    // Broche Relais
#define LED_BUILTIN_PIN 2     // LED integree sur ESP32 Dev Module
#define DNS_PORT        53

// Objets globaux
WebServer server(80);
DNSServer dnsServer;
Preferences prefs;
WiFiClient espClient;
PubSubClient mqtt(espClient);

// Configuration et état
String wifiSsid = "SWEET-HOME";
String wifiPass = "Joury@2027";
String deviceId = "F2ED08";
String deviceSecret = "";
String mqttHost = "broker.hivemq.com";
uint16_t mqttPort = 1883;

bool isApMode = false;
bool relayState = false;
unsigned long lastMqttRetry = 0;

// Simple pilote RMT / NeoPixel bas niveau ou simulation
void setRgbColor(uint8_t r, uint8_t g, uint8_t b) {
    neopixelWrite(RGB_PIN, r, g, b); // Support natif ESP32-S3 Arduino Core
}

// Page HTML embarquée pour le Portail Captif et le Web Dashboard
const char PAGE_INDEX[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SmartPower ESP32-S3 Dashboard</title>
    <style>
        :root { --primary: #6366f1; --bg: #0f172a; --card: #1e293b; --text: #f8fafc; }
        body { font-family: -apple-system, system-ui, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
        .container { max-width: 480px; margin: 0 auto; }
        .card { background: var(--card); border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.08); }
        h1 { font-size: 20px; margin-top: 0; color: #fff; text-align: center; }
        h2 { font-size: 16px; margin-top: 0; color: var(--primary); }
        label { display: block; font-size: 13px; margin-bottom: 6px; color: #94a3b8; }
        input, select { width: 100%; box-sizing: border-box; background: #090d16; border: 1px solid #334155; border-radius: 10px; color: #fff; padding: 12px; margin-bottom: 16px; font-size: 14px; }
        button { width: 100%; background: var(--primary); color: white; border: none; padding: 12px; border-radius: 10px; font-weight: 600; cursor: pointer; transition: 0.2s; font-size: 14px; }
        button:hover { opacity: 0.9; }
        .btn-scan { background: #334155; margin-bottom: 16px; }
        .status-badge { display: inline-block; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: bold; background: #22c55e20; color: #4ade80; }
        .color-row { display: flex; gap: 8px; margin-bottom: 16px; }
        .color-btn { flex: 1; height: 36px; border-radius: 8px; border: none; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card" style="text-align: center;">
            <h1>⚡ SmartPower ESP32-S3</h1>
            <span class="status-badge" id="statusBadge">Mode Configuration (AP)</span>
        </div>

        <div class="card">
            <h2>📶 Configuration du Wi-Fi</h2>
            <button class="btn-scan" onclick="scanWifi()">🔍 Capter les réseaux Wi-Fi</button>
            <form action="/save_wifi" method="POST">
                <label>Réseau Wi-Fi (SSID)</label>
                <select id="ssidSelect" onchange="document.getElementById('ssidInput').value = this.value">
                    <option value="">Sélectionnez un réseau détecté</option>
                </select>
                <input type="text" id="ssidInput" name="ssid" placeholder="Ou tapez le SSID manuellement" required>

                <label>Mot de passe</label>
                <input type="password" name="password" placeholder="Mot de passe du Wi-Fi" required>

                <label>Adresse Serveur MQTT SmartPower (Optionnel)</label>
                <input type="text" name="mqtt_host" value="192.168.1.10">

                <button type="submit">💾 Enregistrer & Connecter</button>
            </form>
        </div>

        <div class="card">
            <h2>🎨 Contrôle LED RGB (WS2812)</h2>
            <div class="color-row">
                <button class="color-btn" style="background:#ef4444" onclick="setLed(255,0,0)"></button>
                <button class="color-btn" style="background:#22c55e" onclick="setLed(0,255,0)"></button>
                <button class="color-btn" style="background:#3b82f6" onclick="setLed(0,100,255)"></button>
                <button class="color-btn" style="background:#eab308" onclick="setLed(255,200,0)"></button>
                <button class="color-btn" style="background:#a855f7" onclick="setLed(168,85,247)"></button>
                <button class="color-btn" style="background:#1e293b; color:#fff" onclick="setLed(0,0,0)">OFF</button>
            </div>
        </div>

        <div class="card">
            <h2>📦 Mise à jour du Firmware (OTA)</h2>
            <form method="POST" action="/update" enctype="multipart/form-data">
                <input type="file" name="update" accept=".bin" required>
                <button type="submit" style="background: #0ea5e9;">🚀 Flasher le binaire (.bin)</button>
            </form>
        </div>
    </div>

    <script>
        async function scanWifi() {
            const btn = document.querySelector('.btn-scan');
            btn.textContent = '⏳ Scan en cours...';
            try {
                const res = await fetch('/api/scan');
                const list = await res.json();
                const sel = document.getElementById('ssidSelect');
                sel.innerHTML = '<option value="">-- Réseaux détectés --</option>';
                list.forEach(item => {
                    const opt = document.createElement('option');
                    opt.value = item.ssid;
                    opt.textContent = `${item.ssid} (${item.rssi} dBm)`;
                    sel.appendChild(opt);
                });
            } catch(e) {
                alert('Erreur lors du scan Wi-Fi');
            }
            btn.textContent = '🔍 Capter les réseaux Wi-Fi';
        }

        function setLed(r, g, b) {
            fetch(`/api/led?r=${r}&g=${g}&b=${b}`);
        }
    </script>
</body>
</html>
)rawliteral";

void handleRoot() {
    server.send(200, "text/html", PAGE_INDEX);
}

void handleScan() {
    int n = WiFi.scanNetworks();
    String json = "[";
    for (int i = 0; i < n; ++i) {
        if (i) json += ",";
        json += "{\"ssid\":\"" + WiFi.SSID(i) + "\",\"rssi\":" + String(WiFi.RSSI(i)) + "}";
    }
    json += "]";
    server.send(200, "application/json", json);
}

void handleSaveWifi() {
    if (server.hasArg("ssid") && server.hasArg("password")) {
        wifiSsid = server.arg("ssid");
        wifiPass = server.arg("password");
        if (server.hasArg("mqtt_host") && server.arg("mqtt_host").length() > 0) {
            mqttHost = server.arg("mqtt_host");
        }

        prefs.putString("ssid", wifiSsid);
        prefs.putString("pass", wifiPass);
        prefs.putString("mqtt_host", mqttHost);

        String msg = "<html><body style='font-family:sans-serif;text-align:center;padding:40px;background:#0f172a;color:#fff;'>";
        msg += "<h2>Parametres enregistres !</h2><p>L'ESP32 redemarre et se connecte a " + wifiSsid + "...</p></body></html>";
        server.send(200, "text/html", msg);
        delay(1500);
        ESP.restart();
    } else {
        server.send(400, "text/plain", "Champs manquants");
    }
}

void handleLedApi() {
    uint8_t r = server.arg("r").toInt();
    uint8_t g = server.arg("g").toInt();
    uint8_t b = server.arg("b").toInt();
    setRgbColor(r, g, b);
    server.send(200, "text/plain", "OK");
}


void setRelay(bool on) {
    relayState = on;
    digitalWrite(RELAY_PIN, on ? HIGH : LOW);
    digitalWrite(LED_BUILTIN_PIN, on ? HIGH : LOW);
    Serial.printf("[RELAY] Relais sur GPIO %d : %s\n", RELAY_PIN, on ? "ALLUME (ON)" : "ETEINT (OFF)");
}

void publishState() {
    String stateTopic = "sp/" + deviceId + "/state";
    String payload = "{\"switch\":\"" + String(relayState ? "on" : "off") + "\"}";
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
    Serial.printf("[MQTT] Connexion a %s:%d...\n", mqttHost.c_str(), mqttPort);
    if (mqtt.connect(deviceId.c_str(), willTopic.c_str(), 1, true, "offline")) {
        mqtt.publish(willTopic.c_str(), "online", true);
        mqtt.subscribe(cmdTopic.c_str(), 1);
        publishState();
        Serial.println("[MQTT] ✅ Connecte avec succes au broker !");
    } else {
        Serial.printf("[MQTT] ⚠️ Echec connexion (etat %d)\n", mqtt.state());
    }
}

void setup() {
    Serial.begin(115200);
    pinMode(RGB_PIN, OUTPUT);
    pinMode(RELAY_PIN, OUTPUT);
    pinMode(LED_BUILTIN_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, LOW);
    digitalWrite(LED_BUILTIN_PIN, LOW);
    setRgbColor(0, 0, 20); // Bleu discret au démarrage

    prefs.begin("smartpower", false);
    wifiSsid = prefs.getString("ssid", wifiSsid);
    prefs.putString("ssid", wifiSsid);
    wifiPass = prefs.getString("pass", wifiPass);
    prefs.putString("pass", wifiPass);
    mqttHost = prefs.getString("mqtt_host", "broker.hivemq.com");

    Serial.println("\n--- Demarrage SmartPower ESP32-S3 ---");

    if (wifiSsid.length() > 0) {
        Serial.printf("Connexion a %s...\n", wifiSsid.c_str());
        WiFi.mode(WIFI_STA);
        WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
        
        int timeout = 0;
        while (WiFi.status() != WL_CONNECTED && timeout < 20) {
            delay(500);
            Serial.print(".");
            timeout++;
        }
        Serial.println();
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.print("Connecte ! IP locale : ");
        Serial.println(WiFi.localIP());
        setRgbColor(0, 50, 0); // Vert = Connecté
        isApMode = false;
    } else {
        Serial.println("Activation du mode Point d'acces (Portail Captif)...");
        isApMode = true;
        WiFi.mode(WIFI_AP_STA);
        String apName = "ESP32-RGB-" + deviceId;
        WiFi.softAP(apName.c_str());
        
        dnsServer.start(DNS_PORT, "*", WiFi.softAPIP());
        Serial.print("AP actif : ");
        Serial.println(apName);
        Serial.print("IP Portail : ");
        Serial.println(WiFi.softAPIP());
        setRgbColor(50, 20, 0); // Orange/Jaune = Mode AP
    }

    // Configuration serveur Web
    server.on("/", handleRoot);
    server.on("/api/scan", handleScan);
    server.on("/save_wifi", HTTP_POST, handleSaveWifi);
    server.on("/api/led", handleLedApi);

    // OTA Flasher Web
    server.on("/update", HTTP_POST, []() {
        server.sendHeader("Connection", "close");
        server.send(200, "text/plain", (Update.hasError()) ? "Echec MAJ" : "MAJ reussie ! Redemarrage...");
        ESP.restart();
    }, []() {
        HTTPUpload& upload = server.upload();
        if (upload.status == UPLOAD_FILE_START) {
            Serial.printf("MAJ OTA debut: %s\n", upload.filename.c_str());
            if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
                Update.printError(Serial);
            }
        } else if (upload.status == UPLOAD_FILE_WRITE) {
            if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
                Update.printError(Serial);
            }
        } else if (upload.status == UPLOAD_FILE_END) {
            if (Update.end(true)) {
                Serial.printf("MAJ finie: %u octets. Redemarrage...\n", upload.totalSize);
            }
        }
    });

    
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
                server.send(200, "application/json", "{\"error\":0,\"switch\":\"" + String(on ? "on" : "off") + "\"}");
                return;
            }
        }
        server.send(400, "application/json", "{\"error\":400}");
    });

    server.on("/zeroconf/info", HTTP_GET, []() {
        String json = "{\"id\":\"" + deviceId + "\",\"switch\":\"" + String(relayState ? "on" : "off") + "\",\"rssi\":" + String(WiFi.RSSI()) + "}";
        server.send(200, "application/json", json);
    });

    server.begin();
    Serial.println("Serveur Web demarre !");
}


void checkSerialProvisioning() {
    if (Serial.available()) {
        String l = Serial.readStringUntil('\n');
        l.trim();
        if (l.startsWith("WIFI ")) {
            int sp1 = l.indexOf(' ');
            int sp2 = l.indexOf(' ', sp1 + 1);
            if (sp2 > sp1) {
                wifiSsid = l.substring(sp1 + 1, sp2);
                wifiPass = l.substring(sp2 + 1);
                prefs.putString("ssid", wifiSsid);
                prefs.putString("pass", wifiPass);
                Serial.printf("[WIFI] Reconfiguration vers '%s'\n", wifiSsid.c_str());
                WiFi.disconnect();
                WiFi.mode(WIFI_STA);
                WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
                int t = 0;
                while (WiFi.status() != WL_CONNECTED && t < 25) {
                    delay(500);
                    Serial.print(".");
                    t++;
                }
                if (WiFi.status() == WL_CONNECTED) {
                    Serial.printf("\nWi-Fi connecte ! IP : %s\n", WiFi.localIP().toString().c_str());
                    setRgbColor(0, 50, 0);
                    isApMode = false;
                } else {
                    Serial.println("\nEchec connexion Wi-Fi");
                }
            }
        } else if (l == "STATUS") {
            if (WiFi.status() == WL_CONNECTED) {
                Serial.printf("Wi-Fi connecte ! SSID: %s, IP: %s\n", WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
            } else {
                Serial.printf("Mode AP : IP %s\n", WiFi.softAPIP().toString().c_str());
            }
        } else if (l == "REBOOT") {
            Serial.println("[SYSTEM] Redemarrage...");
            delay(100);
            ESP.restart();
        }
    }
}

void loop() {
    checkSerialProvisioning();
    if (isApMode) {
        dnsServer.processNextRequest();
    }
    server.handleClient();

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

}
