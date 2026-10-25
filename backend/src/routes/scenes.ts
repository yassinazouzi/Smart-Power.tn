import { Router } from 'express';
import { z } from 'zod';
import { assertHomeRole } from '../auth/middleware.js';
import { db } from '../lib/db.js';
import { HttpError, ah, notFound } from '../lib/errors.js';
import { runScene } from '../scenes/engine.js';
import { sceneInputSchema, type Action, type Condition } from '../scenes/schema.js';

export const scenesRouter = Router();

/** Every device and scene a scene references must belong to the same home. */
async function assertReferencesInHome(homeId: string, conditions: Condition[], actions: Action[], selfId?: string) {
  const deviceIds = new Set<string>();
  const sceneIds = new Set<string>();
  for (const c of conditions) if (c.type === 'device') deviceIds.add(c.deviceId);
  for (const a of actions) {
    if (a.type === 'device') deviceIds.add(a.deviceId);
    if (a.type === 'scene') sceneIds.add(a.sceneId);
  }
  if (selfId && sceneIds.has(selfId)) throw new HttpError(400, 'A scene cannot trigger itself', 'self_reference');
  const [devices, scenes] = await Promise.all([
    db.device.count({ where: { id: { in: [...deviceIds] }, homeId } }),
    db.scene.count({ where: { id: { in: [...sceneIds] }, homeId } }),
  ]);
  if (devices !== deviceIds.size || scenes !== sceneIds.size) throw new HttpError(400, 'Scene references devices or scenes outside this home', 'invalid_reference');
}

scenesRouter.get(
  '/',
  ah(async (req, res) => {
    const { homeId } = z.object({ homeId: z.string() }).parse(req.query);
    await assertHomeRole(req.userId, homeId);
    res.json({ scenes: await db.scene.findMany({ where: { homeId }, orderBy: { createdAt: 'asc' } }) });
  }),
);

scenesRouter.post(
  '/',
  ah(async (req, res) => {
    const { homeId } = z.object({ homeId: z.string() }).parse(req.body);
    await assertHomeRole(req.userId, homeId, 'ADMIN');
    const body = sceneInputSchema.parse(req.body);
    await assertReferencesInHome(homeId, body.conditions, body.actions);
    const scene = await db.scene.create({ data: { ...body, homeId, conditions: body.conditions as object[], actions: body.actions as object[] } });
    res.status(201).json({ scene });
  }),
);

async function loadScene(userId: string, sceneId: string, min: 'MEMBER' | 'ADMIN' = 'MEMBER') {
  const scene = await db.scene.findUnique({ where: { id: sceneId } });
  if (!scene) throw notFound('Scene');
  await assertHomeRole(userId, scene.homeId, min);
  return scene;
}

scenesRouter.put(
  '/:id',
  ah(async (req, res) => {
    const scene = await loadScene(req.userId, req.params.id, 'ADMIN');
    const body = sceneInputSchema.parse(req.body);
    await assertReferencesInHome(scene.homeId, body.conditions, body.actions, scene.id);
    const updated = await db.scene.update({
      where: { id: scene.id },
      data: { ...body, conditions: body.conditions as object[], actions: body.actions as object[] },
    });
    res.json({ scene: updated });
  }),
);

scenesRouter.patch(
  '/:id',
  ah(async (req, res) => {
    const scene = await loadScene(req.userId, req.params.id, 'ADMIN');
    const body = z.object({ enabled: z.boolean().optional(), name: z.string().min(1).max(60).optional(), icon: z.string().max(32).optional() }).parse(req.body);
    res.json({ scene: await db.scene.update({ where: { id: scene.id }, data: body }) });
  }),
);

scenesRouter.delete(
  '/:id',
  ah(async (req, res) => {
    const scene = await loadScene(req.userId, req.params.id, 'ADMIN');
    await db.scene.delete({ where: { id: scene.id } });
    res.status(204).end();
  }),
);

scenesRouter.post(
  '/:id/run',
  ah(async (req, res) => {
    const scene = await loadScene(req.userId, req.params.id);
    res.json(await runScene(scene.id, `user:${req.userId}`));
  }),
);

scenesRouter.get(
  '/:id/runs',
  ah(async (req, res) => {
    const scene = await loadScene(req.userId, req.params.id);
    res.json({ runs: await db.sceneRun.findMany({ where: { sceneId: scene.id }, orderBy: { ts: 'desc' }, take: 50 }) });
  }),
);
