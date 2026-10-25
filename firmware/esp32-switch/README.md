# SmartPower ESP32 NodeMCU switch

One relay, one device. This firmware talks the new SmartPower MQTT protocol, with a unique id and secret per device.

## 1. Create the device on the server (admin)

```
curl -X POST https://api.smartpower.tn/v1/admin/devices \
  -H "Authorization: Bearer <admin access token>" \
  -H "Content-Type: application/json" \
  -d '{"type":"SWITCH","count":1}'
```

The response contains `id`, `secret` and `claimCode`. **The secret is shown only once.** Write it on the device label or in your records before closing the response.

## 2. Install the Arduino IDE and libraries

1. Install Arduino IDE 2.x.
2. Add the ESP32 board package: File > Preferences > Additional boards manager URLs, add
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`, then Tools > Board > Boards Manager > install **esp32 by Espressif**.
3. Library Manager: install **PubSubClient** (Nick O'Leary) and **ArduinoJson** (version 7).
4. Board: **ESP32 Dev Module**. Upload speed 921600 is fine.

## 3. Configure and flash

Open `esp32-switch.ino` and set:
- `MQTT_HOST`: the broker address. On your LAN, use the PC or server IP. In production, use `mqtt.smartpower.tn` on port 8883 with TLS (see below).
- `RELAY_PIN` and `RELAY_ACTIVE_HIGH`: match your relay module.

Upload to the board.

## 4. Provision (once per device)

Open the Serial Monitor at **115200 baud**, with "Newline" line endings, and type:

```
WIFI <your-wifi-name> <your-wifi-password>
DEVICE <id from step 1> <secret from step 1>
STATUS
```

`STATUS` should show `MQTT up`. In the app or on the server, the device should show as online.

To reset: `RESET` in the Serial Monitor, or hold the BOOT button for 5 seconds.

## 5. Claim it for a customer

The admin can assign the device to a customer:

```
POST /v1/admin/devices/<id>/assign   {"customerId": "<customer id>"}
```

Or the customer can claim it in the app with the **id** and **claim code** from the label.

## Production notes

- The sketch uses plain MQTT (port 1883) for LAN testing. Before going live, the broker must be reachable at `mqtt.smartpower.tn:8883` with TLS. Then set `MQTT_PORT = 8883` and use `WiFiClientSecure` with the server's CA certificate. Plain MQTT sends the secret unencrypted.
- The device only reports and obeys `switch` on/off. Energy metering needs a meter chip (for example a BL0937/HLW8012) and the `PLUG` device type; that's a separate firmware.
- Store secrets safely: the NodeMCU keeps them in flash (`Preferences`), which is not encrypted. Enable flash encryption on production batches.
