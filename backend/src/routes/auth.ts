import bcrypt from 'bcryptjs';
import { Router } from 'express';
import rateLimit from 'express-rate-limit';
import { z } from 'zod';
import { requireAuth } from '../auth/middleware.js';
import { issueRefreshToken, rotateRefreshToken, sha256, signAccessToken } from '../auth/tokens.js';
import { config } from '../config.js';
import { db } from '../lib/db.js';
import { createCustomer } from '../lib/customers.js';
import { HttpError, ah } from '../lib/errors.js';

export const authRouter = Router();

const limiter = rateLimit({ windowMs: 15 * 60_000, limit: 30, standardHeaders: true, legacyHeaders: false });

const publicUser = (u: { id: string; email: string; name: string }) => ({ id: u.id, email: u.email, name: u.name });

const registerSchema = z.object({
  email: z.string().email().transform((s) => s.toLowerCase()),
  password: z.string().min(8).max(128),
  name: z.string().min(1).max(80),
});

authRouter.post(
  '/register',
  limiter,
  ah(async (req, res) => {
    if (!config.ALLOW_SELF_REGISTRATION) throw new HttpError(403, 'Accounts are created by SmartPower support', 'self_registration_disabled');
    const body = registerSchema.parse(req.body);
    if (await db.user.findUnique({ where: { email: body.email } })) {
      throw new HttpError(409, 'An account with this email already exists', 'email_taken');
    }
    const user = await createCustomer(body);
    res.status(201).json({
      user: publicUser(user),
      accessToken: signAccessToken(user),
      refreshToken: await issueRefreshToken(user.id),
    });
  }),
);

const loginSchema = z.object({ email: z.string().email().transform((s) => s.toLowerCase()), password: z.string() });

authRouter.post(
  '/login',
  limiter,
  ah(async (req, res) => {
    const body = loginSchema.parse(req.body);
    const user = await db.user.findUnique({ where: { email: body.email } });
    if (!user || !(await bcrypt.compare(body.password, user.passwordHash))) {
      throw new HttpError(401, 'Incorrect email or password', 'invalid_credentials');
    }
    if (user.disabled) throw new HttpError(403, 'This account is disabled. Contact SmartPower support.', 'account_disabled');
    res.json({ user: publicUser(user), accessToken: signAccessToken(user), refreshToken: await issueRefreshToken(user.id) });
  }),
);

authRouter.post(
  '/refresh',
  limiter,
  ah(async (req, res) => {
    const { refreshToken } = z.object({ refreshToken: z.string() }).parse(req.body);
    const rotated = await rotateRefreshToken(refreshToken);
    if (!rotated) throw new HttpError(401, 'Session expired, please sign in again', 'invalid_refresh_token');
    res.json({ user: publicUser(rotated.user), accessToken: rotated.accessToken, refreshToken: rotated.refreshToken });
  }),
);

authRouter.post(
  '/logout',
  ah(async (req, res) => {
    const { refreshToken } = z.object({ refreshToken: z.string() }).parse(req.body);
    await db.refreshToken.deleteMany({ where: { tokenHash: sha256(refreshToken) } });
    res.status(204).end();
  }),
);

authRouter.get(
  '/me',
  requireAuth,
  ah(async (req, res) => {
    const user = await db.user.findUniqueOrThrow({ where: { id: req.userId } });
    res.json({ user: publicUser(user) });
  }),
);

authRouter.patch(
  '/me',
  requireAuth,
  ah(async (req, res) => {
    const body = z
      .object({ name: z.string().min(1).max(80).optional(), currentPassword: z.string().optional(), newPassword: z.string().min(8).max(128).optional() })
      .parse(req.body);
    const user = await db.user.findUniqueOrThrow({ where: { id: req.userId } });
    const data: { name?: string; passwordHash?: string } = {};
    if (body.name) data.name = body.name;
    if (body.newPassword) {
      if (!body.currentPassword || !(await bcrypt.compare(body.currentPassword, user.passwordHash))) {
        throw new HttpError(400, 'Current password is incorrect', 'invalid_password');
      }
      data.passwordHash = await bcrypt.hash(body.newPassword, 12);
    }
    const updated = await db.user.update({ where: { id: user.id }, data });
    res.json({ user: publicUser(updated) });
  }),
);

authRouter.delete(
  '/me',
  requireAuth,
  ah(async (req, res) => {
    // Homes the user solely owns are removed with the account; their devices are released for re-claiming.
    const owned = await db.homeMember.findMany({ where: { userId: req.userId, role: 'OWNER' } });
    await db.$transaction([
      db.device.updateMany({ where: { homeId: { in: owned.map((m) => m.homeId) } }, data: { homeId: null, roomId: null, name: null, claimedAt: null } }),
      db.home.deleteMany({ where: { id: { in: owned.map((m) => m.homeId) } } }),
      db.user.delete({ where: { id: req.userId } }),
    ]);
    res.status(204).end();
  }),
);
