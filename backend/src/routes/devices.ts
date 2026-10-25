import { Router } from 'express';
import { z } from 'zod';
import { assertHomeRole, loadDeviceForUser } from '../auth/middleware.js';
import { db } from '../lib/db.js';
import { HttpError, ah, notFound } from '../lib/errors.js';
import { energySeries, type Period } from '../energy/service.js';
import { presentDevice, sendCommand } from '../devices/service.js';
import { commandSchema } from '../devices/protocol.js';
import { timerInputSchema } from '../scenes/schema.js';

export const devicesRouter = Router();

devicesRouter.get(
  '/',
  ah(async (req, res) => {
    const { homeId } = z.object({ homeId: z.string() }).parse(req.query);
    await assertHomeRole(req.userId, homeId);
    const devices = await db.device.findMany({ where: { homeId }, orderBy: { claimedAt: 'asc' } });
    res.json({ devices: devices.map(presentDevice) });
  }),
);

/**
 * Claims a factory-registered device into a home. The QR label holds "SP1:{deviceId}:{claimCode}";
 * during SoftAP pairing the device returns the same pair from http://192.168.4.1/info.
 */
devicesRouter.post(
  '/claim',
  ah(async (req, res) => {
    const body = z
      .object({ deviceId: z.string().min(4), claimCode: z.string().min(4), homeId: z.string(), roomId: z.string().optional(), name: z.string().min(1).max(60).optional() })
      .parse(req.body);
    await assertHomeRole(req.userId, body.homeId, 'ADMIN');

    const device = await db.device.findUnique({ where: { id: body.deviceId } });
    if (!device || device.claimCode !== body.claimCode) throw new HttpError(404, 'Device not found or claim code is wrong', 'invalid_claim');
    if (device.homeId && device.homeId !== body.homeId) {
      throw new HttpError(409, 'This device belongs to another home. Remove it there first or factory-reset it.', 'already_claimed');
    }
    if (body.roomId && !(await db.room.findFirst({ where: { id: body.roomId, homeId: body.homeId } }))) throw notFound('Room');

    const claimed = await db.device.update({
      where: { id: device.id },
      data: { homeId: body.homeId, roomId: body.roomId ?? null, name: body.name ?? device.name, claimedAt: new Date() },
    });
    res.status(201).json({ device: presentDevice(claimed) });
  }),
);

devicesRouter.get(
  '/:id',
  ah(async (req, res) => {
    res.json({ device: presentDevice(await loadDeviceForUser(req.userId, req.params.id)) });
  }),
);

devicesRouter.patch(
  '/:id',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id, 'ADMIN');
    const body = z.object({ name: z.string().min(1).max(60).optional(), roomId: z.string().nullable().optional() }).parse(req.body);
    if (body.roomId && !(await db.room.findFirst({ where: { id: body.roomId, homeId: device.homeId! } }))) throw notFound('Room');
    res.json({ device: presentDevice(await db.device.update({ where: { id: device.id }, data: body })) });
  }),
);

devicesRouter.delete(
  '/:id',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id, 'ADMIN');
    await db.$transaction([
      db.timer.deleteMany({ where: { deviceId: device.id } }),
      db.device.update({ where: { id: device.id }, data: { homeId: null, roomId: null, name: null, claimedAt: null } }),
    ]);
    res.status(204).end();
  }),
);

devicesRouter.post(
  '/:id/command',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id);
    const command = await sendCommand(device, req.body);
    // The app updates optimistically; the authoritative state arrives over the socket when the device reports it.
    res.status(202).json({ accepted: command });
  }),
);

// --- Timers ---

devicesRouter.get(
  '/:id/timers',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id);
    res.json({ timers: await db.timer.findMany({ where: { deviceId: device.id }, orderBy: { at: 'asc' } }) });
  }),
);

devicesRouter.post(
  '/:id/timers',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id, 'ADMIN');
    const body = timerInputSchema.parse(req.body);
    commandSchema(device.type, device.channels).parse(body.command);
    if ((await db.timer.count({ where: { deviceId: device.id } })) >= 16) throw new HttpError(400, 'A device can have at most 16 timers', 'too_many_timers');
    res.status(201).json({ timer: await db.timer.create({ data: { ...body, command: body.command as object, deviceId: device.id } }) });
  }),
);

devicesRouter.patch(
  '/:id/timers/:timerId',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id, 'ADMIN');
    const body = timerInputSchema.partial().parse(req.body);
    if (body.command) commandSchema(device.type, device.channels).parse(body.command);
    const { count } = await db.timer.updateMany({
      where: { id: req.params.timerId, deviceId: device.id },
      data: { ...body, command: body.command as object | undefined },
    });
    if (!count) throw notFound('Timer');
    res.json({ timer: await db.timer.findUnique({ where: { id: req.params.timerId } }) });
  }),
);

devicesRouter.delete(
  '/:id/timers/:timerId',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id, 'ADMIN');
    await db.timer.deleteMany({ where: { id: req.params.timerId, deviceId: device.id } });
    res.status(204).end();
  }),
);

// --- Energy for one device ---

const periodSchema = z.object({ period: z.enum(['day', 'week', 'month', 'year']).default('day') });

devicesRouter.get(
  '/:id/energy',
  ah(async (req, res) => {
    const device = await loadDeviceForUser(req.userId, req.params.id);
    const { period } = periodSchema.parse(req.query);
    const home = await db.home.findUniqueOrThrow({ where: { id: device.homeId! } });
    const { perDevice: _omit, ...result } = await energySeries([device.id], period as Period, home.timezone);
    res.json({ ...result, cost: Math.round(result.totalKwh * home.tariffPerKwh * 1000) / 1000, currency: home.currency });
  }),
);
