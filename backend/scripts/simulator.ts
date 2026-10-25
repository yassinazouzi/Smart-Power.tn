/**
 * Simulates a SmartPower device over MQTT so the app can be developed without hardware.
 *
 *   npm run simulate -- --id sp1a2b3c4d5e --secret <secret> --type PLUG [--url mqtt://localhost:1883]
 *
 * Plugs and meters report realistic power while on and accumulate an energy counter.
 */
import { parseArgs } from 'node:util';
import mqtt from 'mqtt';

const { values } = parseArgs({
  options: {
    id: { type: 'string' },
    secret: { type: 'string' },
    type: { type: 'string', default: 'PLUG' },
    channels: { type: 'string', default: '2' },
    url: { type: 'string', default: 'mqtt://localhost:1883' },
    interval: { type: 'string', default: '5' },
  },
});

if (!values.id || !values.secret) {
  console.error('Usage: npm run simulate -- --id <deviceId> --secret <secret> --type PLUG');
  process.exit(1);
}

const id = values.id;
const type = values.type!;
const t = (leaf: string) => `sp/${id}/${leaf}`;

let state: Record<string, unknown> = (() => {
  switch (type) {
    case 'SWITCH_MULTI':
      return { switches: Array.from({ length: Number(values.channels) }, (_, ch) => ({ ch, switch: 'off' })) };
    case 'DIMMER':
      return { switch: 'off', brightness: 80 };
    case 'RGB_LIGHT':
      return { switch: 'off', brightness: 80, mode: 'white', colorTemp: 50, color: { h: 30, s: 100 } };
    case 'CURTAIN':
      return { position: 0, motion: 'stop' };
    case 'SENSOR_TH':
      return {};
    default:
      return { switch: 'off' };
  }
})();

let energyWh = 0;
const baseLoad = 40 + Math.random() * 1400; // W drawn by whatever is plugged in

const client = mqtt.connect(values.url!, {
  clientId: id,
  username: id,
  password: values.secret,
  will: { topic: t('status'), payload: Buffer.from('offline'), retain: true, qos: 1 },
});

const publishState = () => client.publish(t('state'), JSON.stringify(state), { retain: true, qos: 1 });

client.on('connect', () => {
  console.log(`[${id}] connected as ${type}`);
  client.publish(t('status'), 'online', { retain: true, qos: 1 });
  client.publish(t('info'), JSON.stringify({ firmware: '1.0.0-sim' }), { retain: true });
  client.subscribe(t('cmd'), { qos: 1 });
  publishState();
});

client.on('message', (_topic, payload) => {
  const cmd = JSON.parse(payload.toString());
  console.log(`[${id}] command`, cmd);
  if (type === 'SWITCH_MULTI') {
    const switches = (state.switches as { ch: number; switch: string }[]).map((s) => ({ ...s }));
    if (cmd.switch) switches.forEach((s) => (s.switch = cmd.switch));
    for (const c of cmd.switches ?? []) {
      const s = switches.find((x) => x.ch === c.ch);
      if (s) s.switch = c.switch;
    }
    state = { ...state, switches };
  } else if (type === 'CURTAIN') {
    const target = cmd.position ?? (cmd.motion === 'open' ? 100 : cmd.motion === 'close' ? 0 : (state.position as number));
    state = { ...state, position: target, motion: 'stop' };
  } else {
    state = { ...state, ...cmd };
  }
  publishState();
});

client.on('error', (err) => console.error(`[${id}] error:`, err.message));

setInterval(() => {
  if (!client.connected) return;
  const seconds = Number(values.interval);
  if (type === 'SENSOR_TH') {
    const hour = new Date().getHours();
    client.publish(
      t('telemetry'),
      JSON.stringify({ temperature: +(22 + 4 * Math.sin((hour / 24) * 2 * Math.PI) + Math.random()).toFixed(1), humidity: Math.round(45 + Math.random() * 15), battery: 92 }),
    );
    return;
  }
  if (type === 'PLUG' || type === 'ENERGY_METER') {
    const on = state.switch === 'on' || type === 'ENERGY_METER';
    const power = on ? +(baseLoad * (0.9 + Math.random() * 0.2)).toFixed(1) : 0;
    const voltage = +(228 + Math.random() * 6).toFixed(1);
    energyWh += (power * seconds) / 3600;
    client.publish(t('telemetry'), JSON.stringify({ power, voltage, current: +(power / voltage).toFixed(3), energyWh: +energyWh.toFixed(3) }));
  }
}, Number(values.interval) * 1000);
