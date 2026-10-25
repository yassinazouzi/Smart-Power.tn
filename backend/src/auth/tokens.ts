import crypto from 'node:crypto';
import jwt from 'jsonwebtoken';
import { config } from '../config.js';
import { db } from '../lib/db.js';

export interface AccessPayload {
  sub: string;
  email: string;
}

export function signAccessToken(user: { id: string; email: string }): string {
  return jwt.sign({ sub: user.id, email: user.email } satisfies AccessPayload, config.JWT_SECRET, {
    expiresIn: config.ACCESS_TOKEN_TTL as jwt.SignOptions['expiresIn'],
  });
}

export function verifyAccessToken(token: string): AccessPayload {
  return jwt.verify(token, config.JWT_SECRET) as AccessPayload;
}

export const sha256 = (value: string) => crypto.createHash('sha256').update(value).digest('hex');

export async function issueRefreshToken(userId: string): Promise<string> {
  const token = crypto.randomBytes(48).toString('base64url');
  await db.refreshToken.create({
    data: {
      userId,
      tokenHash: sha256(token),
      expiresAt: new Date(Date.now() + config.REFRESH_TOKEN_TTL_DAYS * 86_400_000),
    },
  });
  return token;
}

/** Single-use rotation: the presented token is deleted and a new pair is issued. */
export async function rotateRefreshToken(token: string) {
  const record = await db.refreshToken.findUnique({ where: { tokenHash: sha256(token) }, include: { user: true } });
  if (!record) return null;
  await db.refreshToken.delete({ where: { id: record.id } });
  if (record.expiresAt < new Date()) return null;
  return {
    user: record.user,
    accessToken: signAccessToken(record.user),
    refreshToken: await issueRefreshToken(record.userId),
  };
}
