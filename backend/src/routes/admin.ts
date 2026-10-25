import bcrypt from 'bcryptjs';
import { Router } from 'express';
import { z } from 'zod';
import { requireAdmin } from '../auth/middleware.js';
import { db } from '../lib/db.js';
import { createCustomer } from '../lib/customers.js';
import { HttpError, ah, notFound } from '../lib/errors.js';
import { provisionDevices } from '../lib/provision.js';
import { presentDevice } from '../devices/service.js';

/** Everything here is for SmartPower staff. Mounted behind requireAuth + requireAdmin. */
export const adminRouter = Router();
adminRouter.use(requireAdmin);

const email = z.string().email().transform((s) => s.toLowerCase());

// --- Customers ---

adminRouter.get(
  '/customers',
  ah(async (_req, res) => {
    const users = await db.user.findMany({
      where: { role: 'CUSTOMER' },
      orderBy: { createdAt: 'desc' },
      include: { memberships: { where: { role: 'OWNER' }, include: { home: { include: { _count: { select: { devices: true } } } } } } },
    });
    res.json({
      customers: users.map((u) => ({
        id: u.id,
        email: u.email,
        name: u.name,
        disabled: u.disabled,
        createdAt: u.createdAt,
        homes: u.memberships.map((m) => ({ id: m.home.id, name: m.home.name, deviceCount: m.home._count.devices })),
      })),
    });
  }),
);

adminRouter.post(
  '/customers',
  ah(async (req, res) => {
    const body = z
      .object({ email, name: z.string().min(1).max(80), password: z.string().min(8).max(128), homeName: z.string().min(1).max(60).optional() })
      .parse(req.body);
    if (await db.user.findUnique({ where: { email: body.email } })) {
      throw new HttpError(409, 'An account with this email already exists', 'email_taken');
    }
    const user = await createCustomer(body);
    res.status(201).json({ customer: { id: user.id, email: user.email, name: user.name } });
  }),
);

adminRouter.patch(
  '/customers/:id',
  ah(async (req, res) => {
    const body = z
      .object({ name: z.string().min(1).max(80).optional(), disabled: z.boolean().optional(), password: z.string().min(8).max(128).optional() })
      .parse(req.body);
    const customer = await db.user.findFirst({ where: { id: req.params.id, role: 'CUSTOMER' } });
    if (!customer) throw notFound('Customer');

    const data: { name?: string; disabled?: boolean; passwordHash?: string } = {};
    if (body.name) data.name = body.name;
    if (body.disabled !== undefined) data.disabled = body.disabled;
    if (body.password) data.passwordHash = await bcrypt.hash(body.password, 12);

    const ops = [db.user.update({ where: { id: customer.id }, data })] as any[];
    // Disabling signs the customer out everywhere: refresh tokens are removed.
    if (body.disabled || body.password) ops.push(db.refreshToken.deleteMany({ where: { userId: customer.id } }));
    await db.$transaction(ops);
    res.json({ ok: true });
  }),
);

// --- Devices ---

adminRouter.get(
  '/devices',
  ah(async (_req, res) => {
    const devices = await db.device.findMany({
      orderBy: { createdAt: 'desc' },
      include: { home: { include: { members: { where: { role: 'OWNER' }, include: { user: { select: { email: true } } } } } } },
    });
    res.json({
      devices: devices.map((d) => ({
        ...presentDevice(d),
        claimed: !!d.homeId,
        claimedAt: d.claimedAt,
        owner: d.home?.members[0]?.user.email ?? null,
      })),
    });
  }),
);

/** Creates one or more unclaimed devices. Secrets and claim codes are returned once: store them now. */
adminRouter.post(
  '/devices',
  ah(async (req, res) => {
    const body = z
      .object({
        type: z.enum(['PLUG', 'SWITCH', 'SWITCH_MULTI', 'DIMMER', 'RGB_LIGHT', 'CURTAIN', 'SENSOR_TH', 'ENERGY_METER']),
        model: z.string().min(1).max(64).optional(),
        channels: z.number().int().min(2).max(4).optional(),
        count: z.number().int().min(1).max(50).default(1),
        customerId: z.string().optional(),
      })
      .parse(req.body);

    const home = body.customerId ? await ownerHomeOf(body.customerId) : null;
    const devices = await provisionDevices(body);
    if (home) {
      await db.device.updateMany({ where: { id: { in: devices.map((d) => d.id) } }, data: { homeId: home, claimedAt: new Date() } });
    }
    res.status(201).json({ devices, assignedHomeId: home });
  }),
);

adminRouter.post(
  '/devices/:id/assign',
  ah(async (req, res) => {
    const { customerId } = z.object({ customerId: z.string() }).parse(req.body);
    const device = await db.device.findUnique({ where: { id: req.params.id } });
    if (!device) throw notFound('Device');
    if (device.homeId) throw new HttpError(409, 'Device is already assigned. Unassign it first.', 'already_assigned');
    const homeId = await ownerHomeOf(customerId);
    await db.device.update({ where: { id: device.id }, data: { homeId, roomId: null, claimedAt: new Date() } });
    res.json({ ok: true, homeId });
  }),
);

adminRouter.post(
  '/devices/:id/unassign',
  ah(async (req, res) => {
    const device = await db.device.findUnique({ where: { id: req.params.id } });
    if (!device) throw notFound('Device');
    await db.$transaction([
      db.timer.deleteMany({ where: { deviceId: device.id } }),
      db.device.update({ where: { id: device.id }, data: { homeId: null, roomId: null, name: null, claimedAt: null, online: false } }),
    ]);
    res.json({ ok: true });
  }),
);

/** Returns the home a customer owns. Devices are assigned to homes, and each customer has one home by default. */
async function ownerHomeOf(customerId: string): Promise<string> {
  const membership = await db.homeMember.findFirst({
    where: { userId: customerId, role: 'OWNER', user: { role: 'CUSTOMER' } },
    orderBy: { home: { createdAt: 'asc' } },
  });
  if (!membership) throw notFound('Customer home');
  return membership.homeId;
}
