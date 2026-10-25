/*
 * SmartPower - single relay switch for ESP32 NodeMCU (ESP32-WROOM).
 *
 * Talks the SmartPower MQTT protocol (see backend/src/devices/protocol.ts):
 *   sp/{id}/status  "online" | "offline" (retained, offline is the Last Will)
 *   sp/{id}/info    {"model","firmware"}  (retained)
 *   sp/{id}/state   {"switch":"on"|"off"} (retained)
 *   sp/{id}/cmd     {"switch":"on"|"off"} (from the cloud)
 *
 * Each device has its own id and secret. The id is the MQTT username and client id,
 * the secret is the password. Both are provisioned once from the Serial Monitor
 * (115200 baud) and kept in flash:
 *
 *   WIFI <ssid> <password>
 *   DEVICE <id> <secret>
 *   STATUS
 *   RESET          clears Wi-Fi and device credentials
 *
 * Hold the BOOT button for 5 seconds to clear credentials as well.
 *
 * Libraries (Arduino IDE > Library Manager): PubSubClient (Nick O'Leary), ArduinoJson (v7).
 * Board: "ESP32 Dev Module" (NodeMCU-32S uses the same settings).
 */

#include <WiFi.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ---- Configure for your server ------------------------------------------------
const char* MQTT_HOST = "192.168.1.10";   // IP or hostname of the SmartPower broker
const uint16_t MQTT_PORT = 1883;          // plain MQTT on the LAN; use TLS (8883) in production
const char* MODEL = "SP-SW1";
const char* FIRMWARE = "1.0.0";

// ---- Hardware -------------------------------------------------------------------
const int RELAY_PIN = 26;
const bool RELAY_ACTIVE_HIGH = true;      // set false for active-low relay modules
const int BUTTON_PIN = 0;                 // BOOT button on NodeMCU-32S
const unsigned long FACTORY_RESET_MS = 5000;

// ---- State ----------------------------------------------------------------------
Preferences prefs;
WiFiClient net;
PubSubClient mqtt(net);
String wifiSsid, wifiPass, deviceId, deviceSecret;
bool relayOn = false;
unsigned long lastMqttAttempt = 0;
unsigned long buttonDownAt = 0;

String topic(const char* leaf) { return "sp/" + deviceId + "/" + leaf; }

void setRelay(bool on) {
  relayOn = on;
  digitalWrite(RELAY_PIN, (on == RELAY_ACTIVE_HIGH) ? HIGH : LOW);
}

void publishState() {
  JsonDocument doc;
  doc["switch"] = relayOn ? "on" : "off";
  char buf[64];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(topic("state").c_str(), (const uint8_t*)buf, n, true);
}

void onCommand(char* t, byte* payload, unsigned int length) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, length)) {
    Serial.println("cmd: invalid JSON");
    return;
  }
  const char* value = doc["switch"];
  if (!value) return;
  if (strcmp(value, "on") == 0) setRelay(true);
  else if (strcmp(value, "off") == 0) setRelay(false);
  publishState();
}

bool connectWifi() {
  if (wifiSsid.isEmpty()) return false;
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  Serial.print("Wi-Fi");
  for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
    delay(500);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected, IP ");
    Serial.println(WiFi.localIP());
    return true;
  }
  Serial.println("Wi-Fi failed");
  return false;
}

bool connectMqtt() {
  if (deviceId.isEmpty() || deviceSecret.isEmpty()) return false;
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onCommand);
  mqtt.setBufferSize(512);

  // Last Will: if the connection drops, the broker publishes "offline" for us.
  bool ok = mqtt.connect(deviceId.c_str(), deviceId.c_str(), deviceSecret.c_str(),
                         topic("status").c_str(), 1, true, "offline");
  if (!ok) {
    Serial.print("MQTT failed, state ");
    Serial.println(mqtt.state());
    return false;
  }

  mqtt.publish(topic("status").c_str(), "online", true);

  JsonDocument info;
  info["model"] = MODEL;
  info["firmware"] = FIRMWARE;
  char buf[96];
  size_t n = serializeJson(info, buf);
  mqtt.publish(topic("info").c_str(), (const uint8_t*)buf, n, true);

  mqtt.subscribe(topic("cmd").c_str(), 1);
  publishState();
  Serial.println("MQTT connected");
  return true;
}

void saveCredentials() {
  prefs.putString("ssid", wifiSsid);
  prefs.putString("pass", wifiPass);
  prefs.putString("id", deviceId);
  prefs.putString("secret", deviceSecret);
}

void clearCredentials() {
  prefs.clear();
  wifiSsid = wifiPass = deviceId = deviceSecret = "";
  Serial.println("Credentials cleared");
}

void printStatus() {
  Serial.printf("Device %s, Wi-Fi %s, MQTT %s, relay %s\n",
                deviceId.isEmpty() ? "(not set)" : deviceId.c_str(),
                WiFi.status() == WL_CONNECTED ? "up" : "down",
                mqtt.connected() ? "up" : "down",
                relayOn ? "on" : "off");
}

void handleSerial() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.startsWith("WIFI ")) {
    int sp = line.indexOf(' ', 5);
    if (sp < 0) { Serial.println("usage: WIFI <ssid> <password>"); return; }
    wifiSsid = line.substring(5, sp);
    wifiPass = line.substring(sp + 1);
    saveCredentials();
    Serial.println("Wi-Fi saved, reconnecting");
    WiFi.disconnect();
  } else if (line.startsWith("DEVICE ")) {
    int sp = line.indexOf(' ', 7);
    if (sp < 0) { Serial.println("usage: DEVICE <id> <secret>"); return; }
    deviceId = line.substring(7, sp);
    deviceSecret = line.substring(sp + 1);
    saveCredentials();
    Serial.println("Device saved, connecting");
    mqtt.disconnect();
  } else if (line == "STATUS") {
    printStatus();
  } else if (line == "RESET") {
    clearCredentials();
  } else if (!line.isEmpty()) {
    Serial.println("commands: WIFI, DEVICE, STATUS, RESET");
  }
}

void handleButton() {
  if (digitalRead(BUTTON_PIN) == LOW) {
    if (buttonDownAt == 0) buttonDownAt = millis();
    if (millis() - buttonDownAt > FACTORY_RESET_MS) {
      clearCredentials();
      buttonDownAt = 0;
    }
  } else {
    buttonDownAt = 0;
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  setRelay(false);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  prefs.begin("sp", false);
  wifiSsid = prefs.getString("ssid", "");
  wifiPass = prefs.getString("pass", "");
  deviceId = prefs.getString("id", "");
  deviceSecret = prefs.getString("secret", "");

  Serial.println("SmartPower switch starting. Type STATUS, or WIFI / DEVICE to provision.");
  if (!wifiSsid.isEmpty()) connectWifi();
}

void loop() {
  handleSerial();
  handleButton();

  if (WiFi.status() != WL_CONNECTED) {
    static unsigned long lastWifi = 0;
    if (!wifiSsid.isEmpty() && millis() - lastWifi > 15000) {
      lastWifi = millis();
      connectWifi();
    }
    return;
  }

  if (!mqtt.connected()) {
    if (millis() - lastMqttAttempt > 5000) {
      lastMqttAttempt = millis();
      connectMqtt();
    }
  } else {
    mqtt.loop();
  }
}
