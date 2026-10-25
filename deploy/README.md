# Deploying the SmartPower API on OVH

## 1. DNS (OVH manager)
Zone DNS of smartpower.tn: add an **A** record `api` → public IP of the OVH server. Wait until `api.smartpower.tn` resolves.

## 2. Server
Install Docker and the Compose plugin on the server (Ubuntu/Debian: `apt install docker.io docker-compose-v2`). Open ports 80, 443 (HTTPS) and 1883 (devices, until TLS MQTT is set up).

## 3. Start
```
git clone <your repo> smartpower && cd smartpower/deploy
cp .env.prod.example .env.prod      # then edit the two secrets
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml exec api npx prisma migrate deploy
docker compose -f docker-compose.prod.yml exec api node dist/scripts/create-admin.js --email you@smartpower.tn --password "<12+ chars>"
```
Check: `https://api.smartpower.tn/health` returns `{"ok":true}`.

## 4. Before going live
- **MQTT over TLS (8883)** is not set up yet. Devices currently connect on plain 1883, so the device secret travels unencrypted. Add a TLS terminator (for example stunnel or nginx stream with a Let's Encrypt certificate for `mqtt.smartpower.tn`) before the ESP32s leave the LAN.
- Put `api.smartpower.tn` in the Next.js site's API calls and allow `https://smartpower.tn` in CORS (already set).
- Back up the `pgdata` volume.
