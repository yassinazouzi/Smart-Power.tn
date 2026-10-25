import type { HomeRole } from '../generated/prisma/client.js';
import type { RequestHandler } from 'express';
import { db } from '../lib/db.js';
import { HttpError, forbidden } from '../lib/errors.js';
import { verifyAccessToken } from './tokens.js';

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      userId: string;
    }
  }
}

export const requireAuth: RequestHandler = (req, _res, next) => {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) return next(new HttpError(401, 'Missing access token', 'unauthorized'));
  try {
    req.userId = verifyAccessToken(header.slice(7)).sub;
    next();
  } catch {
    next(new HttpError(401, 'Invalid or expired access token', 'unauthorized'));
  }
};

/** Platform admins only (role ADMIN, account not disabled). Must follow requireAuth. */
export const requireAdmin: RequestHandler = async (req, _res, next) => {
  try {
    const user = await db.user.findUnique({ where: { id: req.userId }, select: { role: true, disabled: true } });
    if (!user || user.disabled || user.role !== 'ADMIN') return next(forbidden());
    next();
  } catch (err) {
    next(err);
  }
};

const rank: Record<HomeRole, number> = { MEMBER: 0, ADMIN: 1, OWNER: 2 };

/** Throws unless the user belongs to the home with at least the given role. */
export async function assertHomeRole(userId: string, homeId: string, min: HomeRole = 'MEMBER') {
  const member = await db.homeMember.findUnique({ where: { homeId_userId: { homeId, userId } } });
  if (!member || rank[member.role] < rank[min]) throw forbidden();
  return member;
}

/** Loads a claimed device the user can access. Non-members get 404 so device existence is not revealed. */
export async function loadDeviceForUser(userId: string, deviceId: string, min: HomeRole = 'MEMBER') {
  const device = await db.device.findUnique({ where: { id: deviceId } });
  if (!device?.homeId) throw new HttpError(404, 'Device not found', 'not_found');
  const member = await db.homeMember.findUnique({ where: { homeId_userId: { homeId: device.homeId, userId } } });
  if (!member) throw new HttpError(404, 'Device not found', 'not_found');
  if (rank[member.role] < rank[min]) throw forbidden();
  return device;
}
