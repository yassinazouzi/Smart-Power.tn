import crypto from 'node:crypto';
import bcrypt from 'bcryptjs';
import { DeviceType } from '../generated/prisma/enums.js';
import { db } from './db.js';

export const DEFAULT_MODEL: Record<DeviceType, string> = {
  PLUG: 'SP-PLUG-16A',
  SWITCH: 'SP-SW1',
  SWITCH_MULTI: 'SP-SW4',
  DIMMER: 'SP-DIM',
  RGB_LIGHT: 'SP-BULB-RGBW',
  CURTAIN: 'SP-CURTAIN',
  SENSOR_TH: 'SP-TH',
  ENERGY_METER: 'SP-METER-63A',
};

// Unambiguous alphabet for codes a person may type in.
const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const randomCode = (len: number) => Array.from(crypto.randomBytes(len), (b) => CODE_ALPHABET[b % CODE_ALPHABET.length]).join('');

export interface ProvisionedDevice {
  id: string;
  type: DeviceType;
  model: string;
  secret: string;   // shown once: flashed into the device, only the hash is stored
  claimCode: string;
  qr: string;       // payload printed on the label: SP1:{id}:{claimCode}
}

/** Creates unclaimed device records. Secrets are returned once and never retrievable afterwards. */
export async function provisionDevices(input: { type: DeviceType; model?: string; channels?: number; count: number }) {
  const created: ProvisionedDevice[] = [];
  for (let i = 0; i < input.count; i++) {
    const id = `sp${crypto.randomBytes(5).toString('hex')}`;
    const secret = crypto.randomBytes(18).toString('base64url');
    const claimCode = randomCode(8);
    const model = input.model ?? DEFAULT_MODEL[input.type];
    const channels = input.type === 'SWITCH_MULTI' ? Math.min(4, Math.max(2, input.channels ?? 3)) : 1;
    await db.device.create({
      data: { id, secretHash: await bcrypt.hash(secret, 10), claimCode, type: input.type, model, channels },
    });
    created.push({ id, type: input.type, model, secret, claimCode, qr: `SP1:${id}:${claimCode}` });
  }
  return created;
}
