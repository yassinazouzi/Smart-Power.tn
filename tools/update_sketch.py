import os

sketch_path = r"C:\Users\yassin\Desktop\SmartPower\firmware\esp32_smartpower_dashboard\esp32_smartpower_dashboard.ino"

with open(sketch_path, "r", encoding="utf-8") as f:
    code = f.read()

# Fallback default values
code = code.replace(
    'wifiSsid = prefs.getString("ssid", "");',
    'wifiSsid = prefs.getString("ssid", wifiSsid);\n    prefs.putString("ssid", wifiSsid);'
)
code = code.replace(
    'wifiPass = prefs.getString("pass", "");',
    'wifiPass = prefs.getString("pass", wifiPass);\n    prefs.putString("pass", wifiPass);'
)

# Add serial command provisioning
serial_handler = """
void checkSerialProvisioning() {
    if (Serial.available()) {
        String l = Serial.readStringUntil('\\n');
        l.trim();
        if (l.startsWith("WIFI ")) {
            int sp1 = l.indexOf(' ');
            int sp2 = l.indexOf(' ', sp1 + 1);
            if (sp2 > sp1) {
                wifiSsid = l.substring(sp1 + 1, sp2);
                wifiPass = l.substring(sp2 + 1);
                prefs.putString("ssid", wifiSsid);
                prefs.putString("pass", wifiPass);
                Serial.printf("[WIFI] Reconfiguration vers '%s'\\n", wifiSsid.c_str());
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
                    Serial.printf("\\nWi-Fi connecte ! IP : %s\\n", WiFi.localIP().toString().c_str());
                    setRgbColor(0, 50, 0);
                    isApMode = false;
                } else {
                    Serial.println("\\nEchec connexion Wi-Fi");
                }
            }
        } else if (l == "STATUS") {
            if (WiFi.status() == WL_CONNECTED) {
                Serial.printf("Wi-Fi connecte ! SSID: %s, IP: %s\\n", WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
            } else {
                Serial.printf("Mode AP : IP %s\\n", WiFi.softAPIP().toString().c_str());
            }
        } else if (l == "REBOOT") {
            Serial.println("[SYSTEM] Redemarrage...");
            delay(100);
            ESP.restart();
        }
    }
}
"""

if "checkSerialProvisioning()" not in code:
    code = code.replace("void loop() {", serial_handler + "\nvoid loop() {\n    checkSerialProvisioning();")

with open(sketch_path, "w", encoding="utf-8") as f:
    f.write(code)

print("SKETCH UPDATED SUCCESSFULLY!")
