import type { DeviceType } from '../generated/prisma/client.js';
import { z } from 'zod';

/**
 * SmartPower MQTT protocol (devices authenticate with username = device id, password = device secret)
 *
 *   sp/{id}/status     device -> cloud  "online" | "offline" (retained; "offline" is the Last Will)
 *   sp/{id}/info       device -> cloud  { type, model, firmware, channels } (retained)
 *   sp/{id}/state      device -> cloud  full reported state, see DeviceState (retained)
 *   sp/{id}/telemetry  device -> cloud  { power, voltage, current, energyWh, temperature, humidity }
 *   sp/{id}/cmd        cloud -> device  partial desired state, see commandSchema()
 */
export const TOPIC_PREFIX = 'sp';
export const topic = (deviceId: string, leaf: 'status' | 'info' | 'state' | 'telemetry' | 'cmd') => `${TOPIC_PREFIX}/${deviceId}/${leaf}`;

export function parseTopic(t: string): { deviceId: string; leaf: string } | null {
  const parts = t.split('/');
  if (parts.length !== 3 || parts[0] !== TOPIC_PREFIX) return null;
  return { deviceId: parts[1], leaf: parts[2] };
}

const onOff = z.enum(['on', 'off']);
const percent = z.number().int().min(0).max(100);

export const telemetrySchema = z.object({
  power: z.number().min(0).optional(),
  voltage: z.number().min(0).optional(),
  current: z.number().min(0).optional(),
  energyWh: z.number().min(0).optional(), // monotonically increasing counter since boot / factory
  temperature: z.number().optional(),
  humidity: z.number().min(0).max(100).optional(),
  battery: percent.optional(),
});
export type Telemetry = z.infer<typeof telemetrySchema>;

export const infoSchema = z.object({
  model: z.string().max(64).optional(),
  firmware: z.string().max(32).optional(),
});

/** Commands accepted per device type. Every field is optional: a command is a partial desired state. */
export function commandSchema(type: DeviceType, channels: number) {
  switch (type) {
    case 'PLUG':
    case 'SWITCH':
    case 'ENERGY_METER':
      return z.object({ switch: onOff }).strict();
    case 'SWITCH_MULTI':
      return z
        .object({
          switch: onOff.optional(), // all channels
          switches: z.array(z.object({ ch: z.number().int().min(0).max(channels - 1), switch: onOff })).min(1).optional(),
        })
        .strict()
        .refine((c) => c.switch || c.switches, 'switch or switches is required');
    case 'DIMMER':
      return z.object({ switch: onOff.optional(), brightness: z.number().int().min(1).max(100).optional() }).strict();
    case 'RGB_LIGHT':
      return z
        .object({
          switch: onOff.optional(),
          brightness: z.number().int().min(1).max(100).optional(),
          mode: z.enum(['color', 'white']).optional(),
          color: z.object({ h: z.number().min(0).max(360), s: percent }).optional(),
          colorTemp: percent.optional(), // 0 = warm, 100 = cold
        })
        .strict();
    case 'CURTAIN':
      return z.object({ position: percent.optional(), motion: z.enum(['open', 'close', 'stop']).optional() }).strict();
    case 'SENSOR_TH':
      return z.never();
  }
}

/** Device types whose telemetry carries power and should be rolled into energy statistics. */
export const METERED_TYPES: DeviceType[] = ['PLUG', 'ENERGY_METER'];
