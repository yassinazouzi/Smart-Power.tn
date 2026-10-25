import { Router } from 'express';
import { z } from 'zod';
import { assertHomeRole } from '../auth/middleware.js';
import { db } from '../lib/db.js';
import { ah } from '../lib/errors.js';
import { METERED_TYPES } from '../devices/protocol.js';
import { energySeries, round, type Period } from '../energy/service.js';
import { calculateStegBill } from '../energy/steg.js';

export const energyRouter = Router();

/** Home-wide consumption: totals, cost, time series and a per-device breakdown. */
energyRouter.get(
  '/summary',
  ah(async (req, res) => {
    const { homeId, period } = z.object({ homeId: z.string(), period: z.enum(['day', 'week', 'month', 'year']).default('day') }).parse(req.query);
    await assertHomeRole(req.userId, homeId);
    const home = await db.home.findUniqueOrThrow({ where: { id: homeId } });
    const devices = await db.device.findMany({ where: { homeId, type: { in: METERED_TYPES } }, select: { id: true, name: true, model: true, state: true, online: true } });

    const result = await energySeries(devices.map((d) => d.id), period as Period, home.timezone);
    const livePowerW = devices.reduce((sum, d) => {
      const p = (d.state as Record<string, unknown>)?.power;
      return sum + (d.online && typeof p === 'number' ? p : 0);
    }, 0);

    const breakdown = devices
      .map((d) => {
        const kwh = round((result.perDevice.get(d.id) ?? 0) / 1000);
        return { deviceId: d.id, name: d.name ?? d.model, energyKwh: kwh, cost: round(kwh * home.tariffPerKwh), share: result.totalKwh ? round(kwh / result.totalKwh, 4) : 0 };
      })
      .sort((a, b) => b.energyKwh - a.energyKwh);

    const { perDevice: _omit, ...series } = result;
    res.json({
      ...series,
      livePowerW: round(livePowerW, 1),
      cost: round(result.totalKwh * home.tariffPerKwh),
      currency: home.currency,
      tariffPerKwh: home.tariffPerKwh,
      breakdown,
    });
  }),
);

/** Calculateur officiel STEG Tunisie (paliers de consommation et prévision de facture) */
energyRouter.get(
  '/steg-bill',
  ah(async (req, res) => {
    const { homeId } = z.object({ homeId: z.string() }).parse(req.query);
    await assertHomeRole(req.userId, homeId);
    const home = await db.home.findUniqueOrThrow({ where: { id: homeId } });
    const devices = await db.device.findMany({ where: { homeId, type: { in: METERED_TYPES } }, select: { id: true } });

    // Calcul de la consommation du mois en cours
    const result = await energySeries(devices.map((d) => d.id), 'month', home.timezone);
    const now = new Date();
    const currentDay = now.getDate();

    const stegAnalysis = calculateStegBill(result.totalKwh, currentDay);

    res.json({
      homeId,
      homeName: home.name,
      period: 'Mois en cours',
      currency: 'TND',
      stegAnalysis,
    });
  }),
);
