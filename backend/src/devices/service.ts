import type { Device } from '../generated/prisma/client.js';
import { db } from '../lib/db.js';
import { HttpError } from '../lib/errors.js';
import { bus } from '../lib/events.js';
import { commandSchema } from './protocol.js';

type Publisher = (deviceId: string, command: Record<string, unknown>) => Promise<void>;

let publisher: Publisher | null = null;

/** The MQTT gateway registers how commands reach devices. */
export function setCommandPublisher(fn: Publisher) {
  publisher = fn;
}

export const asState = (value: unknown) => (value && typeof value === 'object' ? (value as Record<string, unknown>) : {});

/** Validates a command against the device type and sends it to the device over MQTT. */
export async function sendCommand(device: Pick<Device, 'id' | 'type' | 'channels' | 'online'>, command: unknown) {
  const parsed = commandSchema(device.type, device.channels).safeParse(command);
  if (!parsed.success) throw new HttpError(400, `Invalid command for ${device.type}: ${parsed.error.issues[0]?.message}`, 'invalid_command');
  if (!device.online) throw new HttpError(409, 'Device is offline', 'device_offline');
  if (!publisher) throw new HttpError(503, 'MQTT broker unavailable', 'broker_unavailable');
  await publisher(device.id, parsed.data as Record<string, unknown>);
  return parsed.data;
}

/** Merges a reported state from the device and notifies listeners when something changed. */
export async function applyReportedState(deviceId: string, patch: Record<string, unknown>) {
  const device = await db.device.findUnique({ where: { id: deviceId } });
  if (!device) return;
  const previous = asState(device.state);
  const state = { ...previous, ...patch };
  if (JSON.stringify(state) === JSON.stringify(previous)) return;
  await db.device.update({ where: { id: deviceId }, data: { state: state as object, lastSeenAt: new Date() } });
  bus.emit('device:state', { deviceId, homeId: device.homeId, state, previous });
}

export async function setOnline(deviceId: string, online: boolean) {
  const device = await db.device.update({
    where: { id: deviceId },
    data: { online, lastSeenAt: new Date() },
    select: { homeId: true },
  });
  bus.emit('device:online', { deviceId, homeId: device.homeId, online });
}

/** Shape returned to the app. Secrets and claim codes never leave the server. */
export function presentDevice(d: Device) {
  return {
    id: d.id,
    name: d.name ?? d.model,
    type: d.type,
    model: d.model,
    channels: d.channels,
    firmware: d.firmware,
    homeId: d.homeId,
    roomId: d.roomId,
    online: d.online,
    lastSeenAt: d.lastSeenAt,
    state: asState(d.state),
  };
}
