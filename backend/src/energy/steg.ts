/**
 * Moteur de calcul de facturation et de prévision STEG (Société Tunisienne de l'Électricité et du Gaz)
 * Tarifs Basse Tension Résidentiel (en Dinars Tunisiens - TND / DT)
 */

export interface StegTier {
  name: string;
  minKwh: number;
  maxKwh: number;
  pricePerKwh: number; // en DT
}

// Grille tarifaire officielle STEG (Basse tension résidentiel)
export const STEG_TIERS: StegTier[] = [
  { name: 'Palier 1 (Économique)', minKwh: 0, maxKwh: 200, pricePerKwh: 0.181 },
  { name: 'Palier 2 (Moyen)', minKwh: 200, maxKwh: 300, pricePerKwh: 0.223 },
  { name: 'Palier 3 (Confort)', minKwh: 300, maxKwh: 500, pricePerKwh: 0.338 },
  { name: 'Palier 4 (Fort)', minKwh: 500, maxKwh: Infinity, pricePerKwh: 0.419 },
];

export const FIXED_REDEVANCE_DT = 2.5; // Redevance fixe mensuelle en DT
export const TVA_RATE = 0.07; // 7% TVA sur l'électricité résidentielle
export const RTT_TAX_PER_KWH = 0.005; // Taxe radio-télévision en DT / kWh

export interface StegBillCalculation {
  totalKwh: number;
  energyCostDT: number;
  tiersBreakdown: {
    tierName: string;
    kwhInTier: number;
    rateDT: number;
    subtotalDT: number;
  }[];
  currentTierIndex: number;
  currentTierName: string;
  nextTierThresholdKwh: number | null;
  remainingToNextTierKwh: number | null;
  tvaDT: number;
  fixedFeeDT: number;
  rttTaxDT: number;
  totalBillDT: number;
  predictedMonthEndKwh?: number;
  predictedMonthEndBillDT?: number;
  tierCrossAlert?: boolean;
}

/**
 * Calcule la facture STEG détaillée à partir d'une consommation en kWh
 * @param totalKwh Consommation totale en kWh sur la période de facturation
 * @param dayOfMonth Jour actuel du mois (1-31) pour le calcul prédictif (optionnel)
 */
export function calculateStegBill(totalKwh: number, dayOfMonth?: number): StegBillCalculation {
  let remainingKwh = Math.max(0, totalKwh);
  let energyCost = 0;
  let currentTierIndex = 0;
  const tiersBreakdown: StegBillCalculation['tiersBreakdown'] = [];

  for (let i = 0; i < STEG_TIERS.length; i++) {
    const tier = STEG_TIERS[i];
    const tierCapacity = tier.maxKwh - tier.minKwh;

    if (remainingKwh > 0) {
      currentTierIndex = i;
      const kwhInThisTier = Math.min(remainingKwh, tierCapacity);
      const subtotal = kwhInThisTier * tier.pricePerKwh;

      energyCost += subtotal;
      remainingKwh -= kwhInThisTier;

      tiersBreakdown.push({
        tierName: tier.name,
        kwhInTier: Number(kwhInThisTier.toFixed(2)),
        rateDT: tier.pricePerKwh,
        subtotalDT: Number(subtotal.toFixed(3)),
      });
    } else {
      tiersBreakdown.push({
        tierName: tier.name,
        kwhInTier: 0,
        rateDT: tier.pricePerKwh,
        subtotalDT: 0,
      });
    }
  }

  const currentTier = STEG_TIERS[currentTierIndex];
  const nextTierThresholdKwh = isFinite(currentTier.maxKwh) ? currentTier.maxKwh : null;
  const remainingToNextTierKwh = nextTierThresholdKwh !== null ? Math.max(0, nextTierThresholdKwh - totalKwh) : null;

  // Taxes et redevances
  const fixedFeeDT = FIXED_REDEVANCE_DT;
  const rttTaxDT = totalKwh * RTT_TAX_PER_KWH;
  const taxableAmount = energyCost + fixedFeeDT;
  const tvaDT = taxableAmount * TVA_RATE;
  const totalBillDT = energyCost + fixedFeeDT + rttTaxDT + tvaDT;

  const result: StegBillCalculation = {
    totalKwh: Number(totalKwh.toFixed(2)),
    energyCostDT: Number(energyCost.toFixed(3)),
    tiersBreakdown,
    currentTierIndex,
    currentTierName: currentTier.name,
    nextTierThresholdKwh,
    remainingToNextTierKwh: remainingToNextTierKwh !== null ? Number(remainingToNextTierKwh.toFixed(2)) : null,
    tvaDT: Number(tvaDT.toFixed(3)),
    fixedFeeDT,
    rttTaxDT: Number(rttTaxDT.toFixed(3)),
    totalBillDT: Number(totalBillDT.toFixed(3)),
  };

  // Prédiction de fin de mois si le jour actuel est renseigné
  if (dayOfMonth && dayOfMonth >= 1 && dayOfMonth <= 31) {
    const dailyAvg = totalKwh / dayOfMonth;
    const predictedKwh = dailyAvg * 30;
    const predictedCalc = calculateStegBill(predictedKwh);

    result.predictedMonthEndKwh = Number(predictedKwh.toFixed(2));
    result.predictedMonthEndBillDT = predictedCalc.totalBillDT;

    // Alerte si la projection change de palier
    result.tierCrossAlert = predictedCalc.currentTierIndex > currentTierIndex;
  }

  return result;
}
