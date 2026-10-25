import type { Scene } from '../generated/prisma/client.js';
import { db } from '../lib/db.js';
import { bus } from '../lib/events.js';
import { logger } from '../lib/logger.js';
import { asState, sendCommand } from '../devices/service.js';
import { actionSchema, conditionSchema, type Action, type Condition } from './schema.js';

const log = logger.child({ mod: 'scenes' });
const MAX_CHAIN_DEPTH = 3;

const parseConditions = (s: Scene) => conditionSchema.array().safeParse(s.conditions).data ?? [];
const parseActions = (s: Scene) => actionSchema.array().safeParse(s.actions).data ?? [];

function compare(actual: unknown, op: string, expected: unknown) {
  if (actual === undefined) return false;
  switch (op) {
    case 'eq':
      return actual === expected;
    case 'neq':
      return actual !== expected;
    case 'gt':
      return typeof actual === 'number' && typeof expected === 'number' && actual > expected;
    case 'lt':
      return typeof actual === 'number' && typeof expected === 'number' && actual < expected;
  }
  return false;
}

const deviceConditionTrue = (c: Extract<Condition, { type: 'device' }>, state: Record<string, unknown>) => compare(state[c.key], c.op, c.value);

/** Local "HH:mm" and ISO weekday (1 = Monday) in a timezone. */
export function localClock(timezone: string, now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: timezone, hour: '2-digit', minute: '2-digit', weekday: 'short', hour12: false }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  const weekday = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(get('weekday')) + 1;
  return { hhmm: `${get('hour').replace('24', '00')}:${get('minute')}`, weekday };
}

const timeMatches = (c: Extract<Condition, { type: 'time' }>, clock: { hhmm: string; weekday: number }) =>
  c.at === clock.hhmm && (c.days.length === 0 || c.days.includes(clock.weekday));

async function currentStates(conditions: Condition[]) {
  const ids = [...new Set(conditions.filter((c) => c.type === 'device').map((c) => (c as { deviceId: string }).deviceId))];
  const devices = await db.device.findMany({ where: { id: { in: ids } }, select: { id: true, state: true } });
  return new Map(devices.map((d) => [d.id, asState(d.state)]));
}

/** Runs a scene's actions in order. Failures of one action are logged and do not stop the rest. */
export async function runScene(sceneId: string, trigger: string, depth = 0): Promise<{ ok: boolean; errors: string[] }> {
  const scene = await db.scene.findUnique({ where: { id: sceneId } });
  if (!scene) return { ok: false, errors: ['scene not found'] };
  const errors: string[] = [];

  for (const action of parseActions(scene)) {
    try {
      await runAction(scene, action, depth);
    } catch (err) {
      errors.push(`${action.type}: ${(err as Error).message}`);
    }
  }

  const ok = errors.length === 0;
  await db.$transaction([
    db.scene.update({ where: { id: scene.id }, data: { lastRunAt: new Date() } }),
    db.sceneRun.create({ data: { sceneId: scene.id, trigger, ok, detail: errors.join('; ') || null } }),
  ]);
  bus.emit('scene:run', { sceneId: scene.id, homeId: scene.homeId, ok, trigger });
  log.info({ sceneId, trigger, ok, errors }, 'scene ran');
  return { ok, errors };
}

async function runAction(scene: Scene, action: Action, depth: number) {
  switch (action.type) {
    case 'device': {
      const device = await db.device.findFirst({ where: { id: action.deviceId, homeId: scene.homeId } });
      if (!device) throw new Error('device not in this home');
      await sendCommand(device, action.command);
      return;
    }
    case 'delay':
      await new Promise((r) => setTimeout(r, action.seconds * 1000));
      return;
    case 'scene': {
      const target = await db.scene.findFirst({ where: { id: action.sceneId, homeId: scene.homeId } });
      if (!target) throw new Error('scene not in this home');
      if (action.action === 'run') {
        if (depth >= MAX_CHAIN_DEPTH) throw new Error('scene chain too deep');
        await runScene(target.id, `scene:${scene.id}`, depth + 1);
      } else {
        await db.scene.update({ where: { id: target.id }, data: { enabled: action.action === 'enable' } });
      }
      return;
    }
    case 'notify':
      // Delivered to connected apps over the realtime socket (see realtime/socket.ts).
      bus.emit('notification', { homeId: scene.homeId, title: scene.name, message: action.message });
      return;
  }
}

/**
 * Fires automations whose device condition just became true (edge-triggered, so a sensor reading
 * 30 °C every few seconds triggers once, not continuously).
 */
async function onDeviceState(deviceId: string, homeId: string, state: Record<string, unknown>, previous: Record<string, unknown>) {
  const scenes = await db.scene.findMany({ where: { homeId, type: 'AUTO', enabled: true } });
  for (const scene of scenes) {
    const conditions = parseConditions(scene);
    const mine = conditions.filter((c): c is Extract<Condition, { type: 'device' }> => c.type === 'device' && c.deviceId === deviceId);
    const rising = mine.some((c) => deviceConditionTrue(c, state) && !deviceConditionTrue(c, previous));
    if (!rising) continue;

    if (scene.matchAll) {
      if (conditions.some((c) => c.type === 'time')) continue; // time-gated: only fires on its tick
      const states = await currentStates(conditions);
      states.set(deviceId, state);
      const all = conditions.every((c) => c.type === 'device' && deviceConditionTrue(c, states.get(c.deviceId) ?? {}));
      if (!all) continue;
    }
    runScene(scene.id, `device:${deviceId}`).catch((err) => log.error({ err }, 'scene failed'));
  }
}

async function onMinute() {
  const scenes = await db.scene.findMany({ where: { type: 'AUTO', enabled: true }, include: { home: { select: { timezone: true } } } });
  for (const scene of scenes) {
    const conditions = parseConditions(scene);
    const clock = localClock(scene.home.timezone);
    const timeHit = conditions.some((c) => c.type === 'time' && timeMatches(c, clock));
    if (!timeHit) continue;
    if (scene.matchAll) {
      const states = await currentStates(conditions);
      const rest = conditions.every((c) => (c.type === 'time' ? timeMatches(c, clock) : deviceConditionTrue(c, states.get(c.deviceId) ?? {})));
      if (!rest) continue;
    }
    runScene(scene.id, 'time').catch((err) => log.error({ err }, 'scene failed'));
  }

  const timers = await db.timer.findMany({ where: { enabled: true }, include: { device: { include: { home: { select: { timezone: true } } } } } });
  for (const timer of timers) {
    if (!timer.device.home) continue;
    const clock = localClock(timer.device.home.timezone);
    const days = Array.isArray(timer.days) ? (timer.days as number[]) : [];
    if (timer.at !== clock.hhmm || (days.length > 0 && !days.includes(clock.weekday))) continue;
    sendCommand(timer.device, timer.command).catch((err) => log.warn({ err, timerId: timer.id }, 'timer command failed'));
  }
}

export function startSceneEngine() {
  bus.on('device:state', (e) => {
    if (!e.homeId) return;
    onDeviceState(e.deviceId, e.homeId, e.state, e.previous).catch((err) => log.error({ err }, 'device trigger evaluation failed'));
  });

  // Tick at the start of every minute.
  let interval: NodeJS.Timeout | undefined;
  const tick = () => onMinute().catch((err) => log.error({ err }, 'minute tick failed'));
  const first = setTimeout(() => {
    tick();
    interval = setInterval(tick, 60_000);
  }, 60_000 - (Date.now() % 60_000) + 50);

  return () => {
    clearTimeout(first);
    if (interval) clearInterval(interval);
  };
}
