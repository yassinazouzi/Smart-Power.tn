import { createServer as createNetServer } from 'node:net';
import { createServer as createHttpServer } from 'node:http';
import { Aedes, type AuthenticateError, type Client } from 'aedes';
import bcrypt from 'bcryptjs';
import { WebSocketServer, createWebSocketStream } from 'ws';
import { config } from '../config.js';
import { db } from '../lib/db.js';
import { logger } from '../lib/logger.js';
import { recordTelemetry } from '../energy/service.js';
import { METERED_TYPES, infoSchema, parseTopic, telemetrySchema, topic } from '../devices/protocol.js';
import { applyReportedState, setCommandPublisher, setOnline } from '../devices/service.js';
import { bus } from '../lib/events.js';

const log = logger.child({ mod: 'mqtt' });

const authError = (message: string): AuthenticateError => Object.assign(new Error(message), { returnCode: 4 as const });

/** Own topics only: a device may publish its reports and subscribe to its command topic. */
const ownTopic = (client: Client | null, t: string) => {
  const p = parseTopic(t);
  return !!client && !!p && p.deviceId === client.id;
};

export async function startBroker() {
  const broker = await Aedes.createBroker({
    authenticate: (client, username, password, done) => {
      if (!username || !password || username !== client.id) {
        done(authError('client id and username must equal the device id'), false);
        return;
      }
      db.device
        .findUnique({ where: { id: username }, select: { secretHash: true } })
        .then(async (d) => {
          const ok = !!d && (await bcrypt.compare(password.toString(), d.secretHash));
          done(ok ? null : authError('bad credentials'), ok);
        })
        .catch((err) => {
          log.error({ err }, 'auth lookup failed');
          done(authError('server error'), false);
        });
    },
    authorizePublish: (client, packet, cb) => {
      const p = parseTopic(packet.topic);
      if (ownTopic(client, packet.topic) && p && ['status', 'info', 'state', 'telemetry'].includes(p.leaf)) cb(null);
      else cb(new Error('publish not allowed'));
    },
    authorizeSubscribe: (client, sub, cb) => {
      if (sub.topic === topic(client.id, 'cmd')) cb(null, sub);
      else cb(new Error('subscribe not allowed'));
    },
  });

  broker.on('clientReady', (client) => {
    setOnline(client.id, true).catch((err) => log.warn({ err, id: client.id }, 'setOnline failed'));
  });
  broker.on('clientDisconnect', (client) => {
    setOnline(client.id, false).catch((err) => log.warn({ err, id: client.id }, 'setOnline failed'));
  });

  broker.on('publish', (packet, client) => {
    if (!client) return; // our own command publishes
    const p = parseTopic(packet.topic);
    if (!p) return;
    handleDeviceMessage(p.deviceId, p.leaf, packet.payload.toString()).catch((err) =>
      log.warn({ err, topic: packet.topic }, 'failed to handle device message'),
    );
  });

  setCommandPublisher(
    (deviceId, command) =>
      new Promise((resolve, reject) => {
        broker.publish(
          { cmd: 'publish', topic: topic(deviceId, 'cmd'), payload: Buffer.from(JSON.stringify(command)), qos: 1, retain: false, dup: false },
          (err) => (err ? reject(err) : resolve()),
        );
      }),
  );

  // Plain MQTT (terminate TLS on 8883 at the reverse proxy / load balancer).
  const tcp = createNetServer(broker.handle);
  tcp.listen(config.MQTT_PORT, () => log.info(`MQTT listening on :${config.MQTT_PORT}`));

  // MQTT over WebSocket for browser dashboards.
  const http = createHttpServer();
  const wss = new WebSocketServer({ server: http });
  wss.on('connection', (ws, req) => broker.handle(createWebSocketStream(ws), req));
  http.listen(config.MQTT_WS_PORT, () => log.info(`MQTT/WS listening on :${config.MQTT_WS_PORT}`));

  // Devices that were connected when the server last stopped are offline until they reconnect.
  await db.device.updateMany({ where: { online: true }, data: { online: false } });

  return {
    close: () =>
      new Promise<void>((resolve) => {
        tcp.close();
        http.close();
        broker.close(() => resolve());
      }),
  };
}

async function handleDeviceMessage(deviceId: string, leaf: string, raw: string) {
  switch (leaf) {
    case 'status':
      await setOnline(deviceId, raw === 'online');
      return;
    case 'info': {
      const info = infoSchema.parse(JSON.parse(raw));
      await db.device.update({ where: { id: deviceId }, data: { firmware: info.firmware, model: info.model ?? undefined } });
      return;
    }
    case 'state': {
      const state = JSON.parse(raw);
      if (state && typeof state === 'object' && !Array.isArray(state)) await applyReportedState(deviceId, state);
      return;
    }
    case 'telemetry': {
      const t = telemetrySchema.parse(JSON.parse(raw));
      const device = await db.device.findUnique({ where: { id: deviceId }, select: { type: true, homeId: true } });
      if (!device) return;
      if (METERED_TYPES.includes(device.type)) await recordTelemetry(deviceId, t);
      // Live readings are part of the state so the app and scene conditions can use them.
      const live: Record<string, number> = {};
      if (t.power !== undefined) live.power = t.power;
      if (t.voltage !== undefined) live.voltage = t.voltage;
      if (t.current !== undefined) live.current = t.current;
      if (t.temperature !== undefined) live.temperature = t.temperature;
      if (t.humidity !== undefined) live.humidity = t.humidity;
      if (t.battery !== undefined) live.battery = t.battery;
      if (Object.keys(live).length) await applyReportedState(deviceId, live);
      bus.emit('device:telemetry', {
        deviceId,
        homeId: device.homeId,
        powerW: t.power ?? 0,
        voltageV: t.voltage,
        currentA: t.current,
        temperature: t.temperature,
        humidity: t.humidity,
      });
      return;
    }
  }
}
