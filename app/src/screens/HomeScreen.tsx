import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { api, Device } from '../api';
import { useApp } from '../store';
import { colors } from '../theme';

export const isOn = (d: Device) => {
  if (d.type === 'SWITCH_MULTI') return (d.state.switches ?? []).some((s: any) => s.switch === 'on');
  return d.state.switch === 'on';
};

/** The state patch and command that switch every channel of a device on or off. */
const power = (d: Device, on: boolean) => {
  const value = on ? 'on' : 'off';
  if (d.type === 'SWITCH_MULTI') {
    return { patch: { switches: (d.state.switches ?? []).map((s: any) => ({ ...s, switch: value })) }, command: { switch: value } };
  }
  return { patch: { switch: value }, command: { switch: value } };
};

export function summary(d: Device) {
  const s = d.state;
  if (!d.online) return 'Offline';
  if (d.type === 'SENSOR_TH') return `${s.temperature ?? '--'} °C · ${s.humidity ?? '--'} %`;
  if (d.type === 'PLUG' || d.type === 'ENERGY_METER') return `${Math.round(s.power ?? 0)} W`;
  if (d.type === 'SWITCH_MULTI') return `${(s.switches ?? []).filter((x: any) => x.switch === 'on').length} of ${d.channels} on`;
  return d.model;
}

export function HomeScreen({ navigation }: { navigation: any }) {
  const { homes, homeId, devices, loadDevices, patchDevice, selectHome } = useApp();
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const home = homes.find((h) => h.id === homeId);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await loadDevices();
      setError(null);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRefreshing(false);
    }
  }, [loadDevices]);

  useEffect(() => {
    refresh();
    // Polls as a fallback; live state arrives from the device's own reports.
    const timer = setInterval(() => loadDevices().catch(() => null), 15_000);
    return () => clearInterval(timer);
  }, [refresh, loadDevices]);

  const byRoom = useMemo(() => {
    const groups = new Map<string, Device[]>();
    for (const d of devices) {
      const key = d.roomId ?? 'none';
      groups.set(key, [...(groups.get(key) ?? []), d]);
    }
    return groups;
  }, [devices]);

  const toggle = async (d: Device) => {
    const on = !isOn(d);
    const { patch, command } = power(d, on);
    patchDevice(d.id, patch);
    try {
      await api.command(d.id, command);
    } catch (e: any) {
      setError(`${d.name}: ${e.message}`);
      loadDevices().catch(() => null);
    }
  };

  return (
    <ScrollView style={styles.container} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={colors.accent} />}>
      <View style={styles.header}>
        <Text style={styles.title}>{home?.name ?? 'SmartPower'}</Text>
        {homes.length > 1 && (
          <Pressable onPress={() => home && selectHome(homes[(homes.indexOf(home) + 1) % homes.length].id)}>
            <Text style={styles.link}>Switch home</Text>
          </Pressable>
        )}
      </View>

      {error && <Text style={styles.error}>{error}</Text>}

      {devices.length === 0 && !refreshing && (
        <View style={styles.empty}>
          <Text style={styles.muted}>No devices yet.</Text>
        </View>
      )}

      {[...byRoom.entries()].map(([roomId, list]) => (
        <View key={roomId} style={styles.section}>
          <Text style={styles.sectionTitle}>{home?.rooms.find((r) => r.id === roomId)?.name ?? 'Unassigned'}</Text>
          {list.map((d) => (
            <Pressable key={d.id} style={styles.card} onPress={() => navigation.navigate('Device', { id: d.id })}>
              <View style={styles.cardBody}>
                <Text style={styles.cardTitle}>{d.name}</Text>
                <Text style={styles.muted}>{summary(d)}</Text>
              </View>
              {d.type !== 'SENSOR_TH' && (
                <Pressable
                  style={[styles.pill, isOn(d) && styles.pillOn, !d.online && styles.disabled]}
                  onPress={() => toggle(d)}
                  disabled={!d.online}
                >
                  <Text style={[styles.pillText, isOn(d) && styles.pillTextOn]}>{!d.online ? 'Offline' : isOn(d) ? 'On' : 'Off'}</Text>
                </Pressable>
              )}
            </Pressable>
          ))}
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { padding: 20, paddingTop: 56, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { color: colors.text, fontSize: 26, fontWeight: '700' },
  section: { paddingHorizontal: 16, marginBottom: 12 },
  sectionTitle: { color: colors.muted, textTransform: 'uppercase', fontSize: 12, letterSpacing: 1, marginBottom: 8 },
  card: { backgroundColor: colors.card, borderRadius: 16, padding: 16, marginBottom: 10, flexDirection: 'row', alignItems: 'center', gap: 12 },
  cardBody: { flex: 1 },
  cardTitle: { color: colors.text, fontSize: 16, fontWeight: '600' },
  muted: { color: colors.muted },
  error: { color: colors.danger, paddingHorizontal: 20, marginBottom: 8 },
  link: { color: colors.accent },
  empty: { padding: 40, alignItems: 'center' },
  pill: { borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 8 },
  pillOn: { backgroundColor: colors.on, borderColor: colors.on },
  pillText: { color: colors.muted, fontWeight: '600' },
  pillTextOn: { color: colors.bg },
  disabled: { opacity: 0.4 },
});
