/**
 * Creates or promotes a SmartPower admin. Run on the server, never from the app.
 *
 *   npm run admin:create -- --email staff@smartpower.tn --name "Staff" --password "a-long-password"
 */
import { parseArgs } from 'node:util';
import bcrypt from 'bcryptjs';
import { db } from '../src/lib/db.js';

const { values } = parseArgs({
  options: {
    email: { type: 'string' },
    name: { type: 'string', default: 'SmartPower Admin' },
    password: { type: 'string' },
  },
});

if (!values.email || !values.password || values.password.length < 12) {
  console.error('Usage: npm run admin:create -- --email <email> --password <at least 12 characters> [--name <name>]');
  process.exit(1);
}

const email = values.email.toLowerCase();
const existing = await db.user.findUnique({ where: { email } });
if (existing) {
  await db.user.update({ where: { id: existing.id }, data: { role: 'ADMIN', disabled: false, passwordHash: await bcrypt.hash(values.password, 12) } });
  console.log(`Promoted ${email} to ADMIN and reset the password.`);
} else {
  await db.user.create({ data: { email, name: values.name!, passwordHash: await bcrypt.hash(values.password, 12), role: 'ADMIN' } });
  console.log(`Created admin ${email}.`);
}

await db.$disconnect();
