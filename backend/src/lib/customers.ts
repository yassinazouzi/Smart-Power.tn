import bcrypt from 'bcryptjs';
import { db } from './db.js';

export const DEFAULT_ROOMS = [
  { name: 'Living room', icon: 'sofa' },
  { name: 'Bedroom', icon: 'bed' },
  { name: 'Kitchen', icon: 'stove' },
];

/** Creates a customer account with its own home and default rooms. Used by admins and optional self-signup. */
export async function createCustomer(input: { email: string; name: string; password: string; homeName?: string }) {
  return db.user.create({
    data: {
      email: input.email,
      name: input.name,
      passwordHash: await bcrypt.hash(input.password, 12),
      role: 'CUSTOMER',
      memberships: {
        create: {
          role: 'OWNER',
          home: { create: { name: input.homeName ?? 'My Home', rooms: { create: DEFAULT_ROOMS } } },
        },
      },
    },
  });
}
