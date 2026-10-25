import { config } from '../config.js';
import { db } from '../lib/db.js';

const lastCounter = new Map<string, number>(); // deviceId -> last energyWh counter seen
const lastPowerSample = new Map<string, { ts: number; powerW: number }>();
const lastSampleStored = new Map<string, number>();

const hourStart = (d: Date) => {
  const h = new Date(d);
  h.setUTCMinutes(0, 0, 0);
  return h;
};

/**
 * Accumulates consumption into EnergyHourly. Prefers the device's energy counter; falls back to
 * integrating power over time when a device only reports watts.
 */
export async function recordTelemetry(deviceId: string, t: { power?: number; voltage?: number; current?: number; energyWh?: number }) {
  const now = new Date();
  let deltaWh = 0;

  if (t.energyWh !== undefined) {
    const prev = lastCounter.get(deviceId);
    lastCounter.set(deviceId, t.energyWh);
    // A lower value than before means the device rebooted and its counter restarted.
    if (prev !== undefined) deltaWh = t.energyWh >= prev ? t.energyWh - prev : t.energyWh;
  } else if (t.power !== undefined) {
    const prev = lastPowerSample.get(deviceId);
    if (prev) {
      const hours = (now.getTime() - prev.ts) / 3_600_000;
      // Ignore gaps longer than 10 minutes rather than extrapolating across an outage.
      if (hours > 0 && hours < 1 / 6) deltaWh = ((prev.powerW + t.power) / 2) * hours;
    }
  }
  if (t.power !== undefined) lastPowerSample.set(deviceId, { ts: now.getTime(), powerW: t.power });

  const power = t.power ?? 0;
  if (deltaWh > 0 || power > 0) {
    const hour = hourStart(now);
    // MySQL upsert: the primary key (deviceId, hour) decides between insert and update.
    await db.$executeRaw`
      INSERT INTO sp_energy_hourly (deviceId, hour, energyWh, maxPowerW)
      VALUES (${deviceId}, ${hour}, ${deltaWh}, ${power})
      ON DUPLICATE KEY UPDATE
        energyWh = energyWh + VALUES(energyWh),
        maxPowerW = GREATEST(maxPowerW, VALUES(maxPowerW))`;
  }

  if (t.power !== undefined) {
    const last = lastSampleStored.get(deviceId) ?? 0;
    if (now.getTime() - last >= config.ENERGY_SAMPLE_INTERVAL * 1000) {
      lastSampleStored.set(deviceId, now.getTime());
      await db.energyReading.create({ data: { deviceId, ts: now, powerW: t.power, voltageV: t.voltage, currentA: t.current } });
    }
  }
}

export type Period = 'day' | 'week' | 'month' | 'year';

/** Returns [start, end) and the bucket size for a period ending now, in the home's timezone. */
export function periodRange(period: Period, timezone: string, now = new Date()) {
  // Compute the local midnight offset for the home timezone.
  const local = new Date(now.toLocaleString('en-US', { timeZone: timezone }));
  const offsetMs = local.getTime() - now.getTime();
  const localMidnight = new Date(local);
  localMidnight.setHours(0, 0, 0, 0);
  const todayStart = new Date(localMidnight.getTime() - offsetMs);

  switch (period) {
    case 'day':
      return { start: todayStart, end: new Date(todayStart.getTime() + 86_400_000), bucket: 'hour' as const, offsetMs };
    case 'week':
      return { start: new Date(todayStart.getTime() - 6 * 86_400_000), end: new Date(todayStart.getTime() + 86_400_000), bucket: 'day' as const, offsetMs };
    case 'month':
      return { start: new Date(todayStart.getTime() - 29 * 86_400_000), end: new Date(todayStart.getTime() + 86_400_000), bucket: 'day' as const, offsetMs };
    case 'year': {
      const first = new Date(localMidnight);
      first.setDate(1);
      first.setMonth(first.getMonth() - 11);
      const end = new Date(localMidnight);
      end.setDate(1);
      end.setMonth(end.getMonth() + 1);
      return { start: new Date(first.getTime() - offsetMs), end: new Date(end.getTime() - offsetMs), bucket: 'month' as const, offsetMs };
    }
  }
}

interface Bucket {
  start: string;
  energyKwh: number;
}

/** Builds a gap-free series of consumption buckets for the given devices. */
export async function energySeries(deviceIds: string[], period: Period, timezone: string) {
  const { start, end, bucket, offsetMs } = periodRange(period, timezone);
  const rows = deviceIds.length
    ? await db.energyHourly.findMany({ where: { deviceId: { in: deviceIds }, hour: { gte: start, lt: end } } })
    : [];

  const keyOf = (utc: Date) => {
    const local = new Date(utc.getTime() + offsetMs);
    if (bucket === 'hour') local.setUTCMinutes(0, 0, 0);
    else if (bucket === 'day') local.setUTCHours(0, 0, 0, 0);
    else {
      local.setUTCDate(1);
      local.setUTCHours(0, 0, 0, 0);
    }
    return new Date(local.getTime() - offsetMs).toISOString();
  };

  const buckets = new Map<string, number>();
  for (let t = new Date(start); t < end; ) {
    buckets.set(keyOf(t), 0);
    if (bucket === 'hour') t = new Date(t.getTime() + 3_600_000);
    else if (bucket === 'day') t = new Date(t.getTime() + 86_400_000);
    else {
      const local = new Date(t.getTime() + offsetMs);
      local.setUTCMonth(local.getUTCMonth() + 1);
      t = new Date(local.getTime() - offsetMs);
    }
  }

  const perDevice = new Map<string, number>();
  let peakW = 0;
  for (const r of rows) {
    const k = keyOf(r.hour);
    buckets.set(k, (buckets.get(k) ?? 0) + r.energyWh);
    perDevice.set(r.deviceId, (perDevice.get(r.deviceId) ?? 0) + r.energyWh);
    peakW = Math.max(peakW, r.maxPowerW);
  }

  const series: Bucket[] = [...buckets.entries()].map(([s, wh]) => ({ start: s, energyKwh: round(wh / 1000) }));
  const totalKwh = round(series.reduce((a, b) => a + b.energyKwh, 0));
  return { period, bucket, start: start.toISOString(), end: end.toISOString(), totalKwh, peakW: round(peakW), series, perDevice };
}

export const round = (n: number, digits = 3) => Math.round(n * 10 ** digits) / 10 ** digits;
