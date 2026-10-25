import { describe, it, expect } from 'vitest';
import { calculateStegBill, STEG_TIERS } from '../steg.js';

describe('STEG Tariff Engine (Tunisie)', () => {
  it('calculates Tier 1 correctly (below 200 kWh)', () => {
    const calc = calculateStegBill(100);
    expect(calc.totalKwh).toBe(100);
    expect(calc.energyCostDT).toBe(18.1); // 100 * 0.181
    expect(calc.currentTierName).toBe(STEG_TIERS[0].name);
    expect(calc.remainingToNextTierKwh).toBe(100); // 200 - 100
    expect(calc.totalBillDT).toBeGreaterThan(18.1); // with TVA and redevance
  });

  it('calculates Tier 2 correctly (e.g. 250 kWh)', () => {
    const calc = calculateStegBill(250);
    expect(calc.totalKwh).toBe(250);
    // Tier 1: 200 * 0.181 = 36.2 DT
    // Tier 2: 50 * 0.223 = 11.15 DT
    // Energy total = 47.35 DT
    expect(calc.energyCostDT).toBe(47.35);
    expect(calc.currentTierName).toBe(STEG_TIERS[1].name);
    expect(calc.remainingToNextTierKwh).toBe(50); // 300 - 250
  });

  it('calculates Tier 4 correctly (e.g. 600 kWh)', () => {
    const calc = calculateStegBill(600);
    expect(calc.totalKwh).toBe(600);
    // Tier 1: 200 * 0.181 = 36.2 DT
    // Tier 2: 100 * 0.223 = 22.3 DT
    // Tier 3: 200 * 0.338 = 67.6 DT
    // Tier 4: 100 * 0.419 = 41.9 DT
    // Energy total = 168.0 DT
    expect(calc.energyCostDT).toBe(168.0);
    expect(calc.currentTierName).toBe(STEG_TIERS[3].name);
    expect(calc.remainingToNextTierKwh).toBeNull();
  });

  it('triggers tierCrossAlert when projection crosses threshold', () => {
    // 150 kWh on day 15 = 10 kWh/day -> 300 kWh projected (reaches Tier 3!)
    const calc = calculateStegBill(150, 15);
    expect(calc.predictedMonthEndKwh).toBe(300);
    expect(calc.tierCrossAlert).toBe(true);
  });
});
