import type { Server as HttpServer } from 'node:http';
import { Server } from 'socket.io';
import { verifyAccessToken } from '../auth/tokens.js';
import { config } from '../config.js';
import { db } from '../lib/db.js';
import { bus } from '../lib/events.js';

/**
 * Realtime channel for the app. Clients authenticate with their access token and are joined to a
 * room per home they belong to. Events: device:state, device:online, scene:run, notification.
 */
export function startRealtime(server: HttpServer) {
  const io = new Server(server, { cors: { origin: config.corsOrigins }, path: '/realtime' });

  io.use((socket, next) => {
    try {
      const token = socket.handshake.auth?.token as string | undefined;
      if (!token) throw new Error('missing token');
      socket.data.userId = verifyAccessToken(token).sub;
      next();
    } catch {
      next(new Error('unauthorized'));
    }
  });

  io.on('connection', async (socket) => {
    const memberships = await db.homeMember.findMany({ where: { userId: socket.data.userId }, select: { homeId: true } });
    for (const m of memberships) socket.join(`home:${m.homeId}`);
  });

  const toHome = (homeId: string | null) => (homeId ? io.to(`home:${homeId}`) : null);

  bus.on('device:state', (e) => toHome(e.homeId)?.emit('device:state', { deviceId: e.deviceId, state: e.state }));
  bus.on('device:online', (e) => toHome(e.homeId)?.emit('device:online', { deviceId: e.deviceId, online: e.online }));
  bus.on('scene:run', (e) => toHome(e.homeId)?.emit('scene:run', e));
  bus.on('notification', (e) => toHome(e.homeId)?.emit('notification', e));

  return io;
}
