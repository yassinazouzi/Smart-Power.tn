import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { api, EnergySummary } from '../api';
import { useApp } from '../store';
import { colors } from '../theme';

const PERIODS = ['day', 'week', 'month', 'year'] as const;

export function EnergyScreen() {
  const homeId = useApp((s) => s.homeId);
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>('day');
  const [data, setData] = useState<EnergySummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!homeId) return;
    api.energy(homeId, period).then(setData).catch((e) => setError(e.message));
  }, [homeId, period]);

  const max = Math.max(0.001, ...(data?.series.map((b) => b.energyKwh) ?? [0]));

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 20, gap: 16 }}>
      <Text style={styles.title}>Energy</Text>
      <View style={styles.periods}>
        {PERIODS.map((p) => (
          <Pressable key={p} style={[styles.period, p === period && styles.periodOn]} onPress={() => setPeriod(p)}>
            <Text style={[styles.periodText, p === period && styles.periodTextOn]}>{p}</Text>
          </Pressable>
        ))}
      </View>

      {error && <Text style={styles.error}>{error}</Text>}

      {data && (
        <>
          <View style={styles.stats}>
            <Stat label="Used" value={`${data.totalKwh.toFixed(2)} kWh`} />
            <Stat label="Cost" value={`${data.cost.toFixed(2)} ${data.currency}`} />
            <Stat label="Live" value={`${Math.round(data.livePowerW)} W`} />
          </View>

          <View style={styles.chart}>
            {data.series.map((b) => (
              <View key={b.start} style={styles.barWrap}>
                <View style={[styles.bar, { height: Math.max(2, (b.energyKwh / max) * 140) }]} />
              </View>
            ))}
          </View>

          <Text style={styles.section}>By device</Text>
          {data.breakdown.map((b) => (
            <View key={b.deviceId} style={styles.row}>
              <Text style={styles.rowName}>{b.name}</Text>
              <Text style={styles.muted}>{b.energyKwh.toFixed(2)} kWh · {Math.round(b.share * 100)}%</Text>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.muted}>{label}</Text>
      <Text style={styles.statValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  title: { color: colors.text, fontSize: 26, fontWeight: '700', paddingTop: 36 },
  periods: { flexDirection: 'row', backgroundColor: colors.card, borderRadius: 12, padding: 4 },
  period: { flex: 1, padding: 10, borderRadius: 9, alignItems: 'center' },
  periodOn: { backgroundColor: colors.accent },
  periodText: { color: colors.muted, textTransform: 'capitalize', fontWeight: '600' },
  periodTextOn: { color: colors.bg },
  error: { color: colors.danger },
  muted: { color: colors.muted },
  stats: { flexDirection: 'row', gap: 10 },
  stat: { flex: 1, backgroundColor: colors.card, borderRadius: 16, padding: 14 },
  statValue: { color: colors.text, fontSize: 17, fontWeight: '700', marginTop: 4 },
  chart: { flexDirection: 'row', alignItems: 'flex-end', height: 160, gap: 3, backgroundColor: colors.card, borderRadius: 16, padding: 12 },
  barWrap: { flex: 1, justifyContent: 'flex-end' },
  bar: { backgroundColor: colors.accent, borderRadius: 3 },
  section: { color: colors.muted, textTransform: 'uppercase', fontSize: 12, letterSpacing: 1 },
  row: { backgroundColor: colors.card, borderRadius: 14, padding: 14, flexDirection: 'row', justifyContent: 'space-between' },
  rowName: { color: colors.text, fontWeight: '600' },
});
