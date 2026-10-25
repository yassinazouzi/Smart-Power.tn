/**
 * Factory provisioning: registers a device and prints the credentials to flash into it and the QR
 * payload to print on its label.
 *
 *   npm run device:create -- --type PLUG --model SP-PLUG-16A
 *   npm run device:create -- --type SWITCH_MULTI --channels 3 --count 10
 */
import crypto from 'node:crypto';
import { parseArgs } from 'node:util';
import bcrypt from 'bcryptjs';
import { db } from '../src/lib/db.js';
import { DeviceType } from '../src/generated/prisma/enums.js';

const { values } = parseArgs({
  options: {
    type: { type: 'string', default: 'PLUG' },
    model: { type: 'string' },
    channels: { type: 'string', default: '1' },
    count: { type: 'string', default: '1' },
    json: { type: 'boolean', default: false },
  },
});

const type = values.type as DeviceType;
if (!Object.values(DeviceType).includes(type)) {
  console.error(`Unknown --type. Use one of: ${Object.values(DeviceType).join(', ')}`);
  process.exit(1);
}

const defaultModel: Record<DeviceType, string> = {
  PLUG: 'SP-PLUG-16A',
  SWITCH: 'SP-SW1',
  SWITCH_MULTI: 'SP-SW4',
  DIMMER: 'SP-DIM',
  RGB_LIGHT: 'SP-BULB-RGBW',
  CURTAIN: 'SP-CURTAIN',
  SENSOR_TH: 'SP-TH',
  ENERGY_METER: 'SP-METER-63A',
};

// Unambiguous alphabet for codes a human may type in.
const code = (len: number) => {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  return Array.from(crypto.randomBytes(len), (b) => alphabet[b % alphabet.length]).join('');
};

const created = [];
for (let i = 0; i < Number(values.count); i++) {
  const id = `sp${crypto.randomBytes(5).toString('hex')}`;
  const secret = crypto.randomBytes(18).toString('base64url');
  const claimCode = code(8);
  await db.device.create({
    data: {
      id,
      secretHash: await bcrypt.hash(secret, 10),
      claimCode,
      type,
      model: values.model ?? defaultModel[type],
      channels: type === 'SWITCH_MULTI' ? Math.min(4, Math.max(2, Number(values.channels))) : 1,
    },
  });
  created.push({ id, secret, claimCode, type, qr: `SP1:${id}:${claimCode}` });
}

if (values.json) console.log(JSON.stringify(created, null, 2));
else
  for (const d of created) {
    console.log(`\n${d.type} ${d.id}\n  MQTT username/client id: ${d.id}\n  MQTT password (flash):   ${d.secret}\n  Claim code:              ${d.claimCode}\n  QR label payload:        ${d.qr}`);
  }

await db.$disconnect();
