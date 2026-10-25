import { Router } from 'express';
import { z } from 'zod';
import { assertHomeRole } from '../auth/middleware.js';
import { db } from '../lib/db.js';
import { HttpError, ah, notFound } from '../lib/errors.js';

export const homesRouter = Router();

const homeInput = z.object({
  name: z.string().min(1).max(60),
  timezone: z.string().max(64).optional(),
  currency: z.string().length(3).optional(),
  tariffPerKwh: z.number().min(0).max(100).optional(),
});

homesRouter.get(
  '/',
  ah(async (req, res) => {
    const memberships = await db.homeMember.findMany({
      where: { userId: req.userId },
      include: { home: { include: { rooms: { orderBy: [{ sort: 'asc' }, { name: 'asc' }] }, _count: { select: { devices: true } } } } },
    });
    res.json({
      homes: memberships.map(({ home, role }) => ({
        id: home.id,
        name: home.name,
        timezone: home.timezone,
        currency: home.currency,
        tariffPerKwh: home.tariffPerKwh,
        role,
        rooms: home.rooms,
        deviceCount: home._count.devices,
      })),
    });
  }),
);

homesRouter.post(
  '/',
  ah(async (req, res) => {
    const body = homeInput.parse(req.body);
    const home = await db.home.create({ data: { ...body, members: { create: { userId: req.userId, role: 'OWNER' } } } });
    res.status(201).json({ home });
  }),
);

homesRouter.patch(
  '/:homeId',
  ah(async (req, res) => {
    await assertHomeRole(req.userId, req.params.homeId, 'ADMIN');
    const home = await db.home.update({ where: { id: req.params.homeId }, data: homeInput.partial().parse(req.body) });
    res.json({ home });
  }),
);

homesRouter.delete(
  '/:homeId',
  ah(async (req, res) => {
    await assertHomeRole(req.userId, req.params.homeId, 'OWNER');
    await db.$transaction([
      // Release devices so they can be claimed again.
      db.device.updateMany({ where: { homeId: req.params.homeId }, data: { homeId: null, roomId: null, name: null, claimedAt: null } }),
      db.home.delete({ where: { id: req.params.homeId } }),
    ]);
    res.status(204).end();
  }),
);

// --- Rooms ---

const roomInput = z.object({ name: z.string().min(1).max(40), icon: z.string().max(32).optional(), sort: z.number().int().optional() });

homesRouter.post(
  '/:homeId/rooms',
  ah(async (req, res) => {
    await assertHomeRole(req.userId, req.params.homeId, 'ADMIN');
    const room = await db.room.create({ data: { ...roomInput.parse(req.body), homeId: req.params.homeId } });
    res.status(201).json({ room });
  }),
);

homesRouter.patch(
  '/:homeId/rooms/:roomId',
  ah(async (req, res) => {
    await assertHomeRole(req.userId, req.params.homeId, 'ADMIN');
    const { count } = await db.room.updateMany({ where: { id: req.params.roomId, homeId: req.params.homeId }, data: roomInput.partial().parse(req.body) });
    if (!count) throw notFound('Room');
    res.json({ room: await db.room.findUnique({ where: { id: req.params.roomId } }) });
  }),
);

homesRouter.delete(
  '/:homeId/rooms/:roomId',
  ah(async (req, res) => {
    await assertHomeRole(req.userId, req.params.homeId, 'ADMIN');
    await db.room.deleteMany({ where: { id: req.params.roomId, homeId: req.params.homeId } });
    res.status(204).end();
  }),
);

// --- Members (sharing a home) ---

homesRouter.get(
  '/:homeId/members',
  ah(async (req, res) => {
    await assertHomeRole(req.userId, req.params.homeId);
    const members = await db.homeMember.findMany({ where: { homeId: req.params.homeId }, include: { user: { select: { id: true, name: true, email: true } } } });
    res.json({ members: members.map((m) => ({ ...m.user, role: m.role })) });
  }),
);

homesRouter.post(
  '/:homeId/members',
  ah(async (req, res) => {
    await assertHomeRole(req.userId, req.params.homeId, 'ADMIN');
    const body = z.object({ email: z.string().email().transform((s) => s.toLowerCase()), role: z.enum(['ADMIN', 'MEMBER']).default('MEMBER') }).parse(req.body);
    const user = await db.user.findUnique({ where: { email: body.email } });
    if (!user) throw new HttpError(404, 'No SmartPower account uses this email', 'user_not_found');
    await db.homeMember.upsert({
      where: { homeId_userId: { homeId: req.params.homeId, userId: user.id } },
      create: { homeId: req.params.homeId, userId: user.id, role: body.role },
      update: { role: body.role },
    });
    res.status(201).json({ member: { id: user.id, name: user.name, email: user.email, role: body.role } });
  }),
);

homesRouter.delete(
  '/:homeId/members/:userId',
  ah(async (req, res) => {
    // Members may leave; admins may remove others. The owner cannot be removed.
    if (req.params.userId !== req.userId) await assertHomeRole(req.userId, req.params.homeId, 'ADMIN');
    const target = await db.homeMember.findUnique({ where: { homeId_userId: { homeId: req.params.homeId, userId: req.params.userId } } });
    if (!target) throw notFound('Member');
    if (target.role === 'OWNER') throw new HttpError(400, 'The owner cannot leave the home; delete it instead', 'owner_cannot_leave');
    await db.homeMember.delete({ where: { homeId_userId: { homeId: req.params.homeId, userId: req.params.userId } } });
    res.status(204).end();
  }),
);
