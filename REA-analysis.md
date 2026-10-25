# REA analysis — eWeLink 5.30.0 (reference for SmartPower)

Input: `ewelink-5-30-0.apk` — 182 MB, sha256 `13d58aa8b2c9ef6944ab2adb4a296168363b9323d739077af935e7a517929fee`
Tools: `rea inspect-artifact` (inventory: 5,982 artifacts / 8,038 entries), `rea identify-flutter-build`,
plus string extraction from the manifest and Hermes bundles. Raw outputs: `C:\Users\yassin\rea-work\ewelink\`.

Not run: `rea inspect-android-package` / class decompilation (requires JADX — `REA_JADX_MCP_JAR` not set).

## Architecture

| Layer | Finding |
|---|---|
| Package | `com.coolkit` (CoolKit), `MainActivity` / `MainApplication` |
| UI framework | **React Native** (new arch: Fabric, `libreact_render_*`), **Hermes** bytecode v84 — not Flutter |
| JS bundles | `index.android.bundle` (28.6 MB, main app) + 5 home-screen widget bundles (`widget`, `deviceWidget`, `sceneWidget`, `statusWidget`, `sceneShortcuts`) |
| State | MobX |
| Navigation | react-navigation (bottom tabs) |
| Key RN libs | reanimated, gesture-handler, screens, vision-camera (QR scan), calendars, color-picker, draggable-flatlist, async-storage, localize, datetimepicker, `react-native-matter`, watch connectivity |
| Native (Java/Kotlin) | 7 dex files (~66 MB): push (FCM, Xiaomi, Huawei, Oppo, Vivo, Meizu, Honor), Google Sign-In, ML Kit barcode, OkHttp |
| Native .so (arm64) | WebRTC (`libjingle_peerconnection_so`), Matter (`libCHIPController`), IJK/FFmpeg player, TUTK/PPCS P2P cameras, Gizwits & Broadlink Wi-Fi pairing (`libGizWifiDaemon`, `libBLEasyConfig`), barcode (`libbarhopper_v3`) |

## Permissions (notable)
Internet / network & Wi-Fi state / change Wi-Fi & multicast (LAN discovery, device pairing), fine/coarse location,
Bluetooth scan/connect/advertise (BLE pairing), camera (QR), record audio (camera intercom), NFC,
post notifications, foreground service (data sync, media playback), boot completed, vibrate, wake lock.

## Feature map (from screen names)

- **Account:** login, SMS login, register/reset with country selector, biometric login, anonymous login, close account, change password, bind email
- **Home / Family:** families, rooms, sorting, sharing devices/families, roles
- **Device pairing:** Wi-Fi AP/EZ pairing (`ChooseWifiScreen`, `PairingScreen`, `MulEspPairingScreen`), QR, mDNS (`ScanCodeMDnsParingScreen`), Matter, Zigbee sub-devices, BLE
- **Device control:** switches/multi-channel, inching, timers, schedules, dimmers & RGB lights (color picker, scenes, rhythm mode), curtains/rolling doors/motors, thermostats (weekly schedule), temp/humidity sensors, IR remotes, cameras (live, playback, events, gallery)
- **Energy:** `TotalPowerScreen`, power history, kWh per hour/day/100-day, overload protection
- **Scenes:** smart scenes (if/then), manual scenes, recommended scenes, scene history
- **Integrations:** Google Home, Alexa, HomeKit, Home Assistant, SmartThings, Matter bridge
- **Other:** firmware OTA, message center, push, VIP subscription (Google/Apple billing), FAQ/feedback, Android home-screen widgets, Wear OS

## APIs observed
- Cloud REST `/v2/...`: `user/login`, `user/register`, `family/...`, `device/thing/status`, `device/timer`, `device/ota`,
  `device/share/...`, `smartscene2/...`, `message/...`, `purchase/...`
- **LAN (DIY / zeroconf) on the device:** `/zeroconf/switch`, `/zeroconf/switches`, `/zeroconf/startups`, `/zeroconf/pulses`,
  `/zeroconf/timerV2`, `/zeroconf/brightness`, `/zeroconf/powerHistory`, `/zeroconf/getHoursKwh`, `/zeroconf/monitor`,
  `/zeroconf/wifi`, `/zeroconf/info`… (discovered via mDNS `_ewelink._tcp`)

## Notes for SmartPower
Build an **original** app using this as a feature/architecture reference — don't copy eWeLink code, assets, branding or
private cloud APIs. The public Sonoff **DIY-mode LAN API** and the **CoolKit Open API (eWeLink developer platform,
requires your own appid)** are the legitimate integration points.
