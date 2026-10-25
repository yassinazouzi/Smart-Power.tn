# SmartPower

Smart-home app for controlling devices and tracking energy use. Original project. Its design was informed by an analysis of the eWeLink 5.30.0 APK, but no eWeLink code, assets or private APIs are used.

## Layout

- `app/`: React Native (TypeScript) app for Android and iOS. Login, home with rooms and devices, device control, energy charts, scenes.
- `backend/`: Node.js API (Express, Prisma with PostgreSQL), MQTT broker (Aedes) for devices, realtime socket, scene and timer engine.
- `docker-compose.yml`: local PostgreSQL.
- `REA-analysis.md`: notes from the REA inspection of the reference APK.

## Run the backend

```
cd backend
cp .env.example .env          # set JWT_SECRET
docker compose -f ../docker-compose.yml up -d db
npx prisma migrate deploy
npm run dev                   # API :4000, MQTT :1883, MQTT over WebSocket :8083
```

## Simulate devices

```
npm run device:create -- --type PLUG --json > dev-plug.json
npm run simulate -- --id <id> --secret <secret> --type PLUG
```

`device:create --json` prints the id, secret and claim code. To run the end-to-end check, provision one plug, one multi-channel switch and one sensor, start a simulator for each, then run:

```
DEVICES_DIR=<folder with dev-plug.json, dev-multi.json, dev-th.json> node scripts/smoke-test.mjs
```

## Run the app

```
cd app
npm start                     # one terminal
npm run android               # another terminal, with an emulator or device connected
```

The API address is set in `app/src/config.ts` (`10.0.2.2:4000` is the Android emulator's view of localhost).

## Status

- **Backend:** auth, homes and rooms, device claim and control, timers, scenes (manual and automatic), energy summaries. The end-to-end smoke test passes against simulated devices.
- **App:** TypeScript typecheck and Android bundle both pass. Not yet run on a device or emulator.
- **Not built yet:** add-device pairing (QR or Wi-Fi), iOS build, push notifications, production TLS for MQTT.
