import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { api, Device } from '../api';
import { useApp } from '../store';
import { colors } from '../theme';

export function DeviceScreen({ route }: { route: { params: { id: string } } }) {
  const device = useApp((s) => s.devices.find((d) => d.id === route.params.id));
  const patchDevice = useApp((s) => s.patchDevice);
  const [error, setError] = React.useState<string | null>(null);

  if (!device) return <Text style={styles.muted}>Device not found.</Text>;

  const send = async (command: Record<string, unknown>, patch: Record<string, unknown>) => {
    patchDevice(device.id, patch);
    try {
      await api.command(device.id, command);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 20, gap: 16 }}>
      <Text style={styles.title}>{device.name}</Text>
      <Text style={styles.muted}>{device.model} · {device.online ? 'Online' : 'Offline'}</Text>
      {error && <Text style={styles.error}>{error}</Text>}

      {(device.type === 'PLUG' || device.type === 'SWITCH' || device.type === 'ENERGY_METER' || device.type === 'DIMMER' || device.type === 'RGB_LIGHT') && (
        <Pressable
          style={[styles.bigButton, device.state.switch === 'on' && styles.bigOn, !device.online && styles.disabled]}
          disabled={!device.online}
          onPress={() => {
            const next = device.state.switch === 'on' ? 'off' : 'on';
            send({ switch: next }, { switch: next });
          }}
        >
          <Text style={styles.bigText}>{device.state.switch === 'on' ? 'Turn off' : 'Turn on'}</Text>
        </Pressable>
      )}

      {device.type === 'SWITCH_MULTI' &&
        Array.from({ length: device.channels }, (_, ch) => {
          const on = (device.state.switches ?? []).find((s: any) => s.ch === ch)?.switch === 'on';
          return (
            <Pressable
              key={ch}
              style={[styles.row, on && styles.bigOn]}
              disabled={!device.online}
              onPress={() => {
                const switches = (device.state.switches ?? []).map((s: any) => (s.ch === ch ? { ...s, switch: on ? 'off' : 'on' } : s));
                send({ switches: [{ ch, switch: on ? 'off' : 'on' }] }, { switches });
              }}
            >
              <Text style={styles.bigText}>Channel {ch + 1}: {on ? 'On' : 'Off'}</Text>
            </Pressable>
          );
        })}

      {device.type === 'CURTAIN' && (
        <View style={styles.row}>
          {(['open', 'stop', 'close'] as const).map((m) => (
            <Pressable key={m} style={styles.small} disabled={!device.online} onPress={() => send({ motion: m }, {})}>
              <Text style={styles.bigText}>{m}</Text>
            </Pressable>
          ))}
        </View>
      )}

      {device.type === 'SENSOR_TH' && (
        <View style={styles.stats}>
          <Stat label="Temperature" value={`${device.state.temperature ?? '--'} °C`} />
          <Stat label="Humidity" value={`${device.state.humidity ?? '--'} %`} />
          <Stat label="Battery" value={`${device.state.battery ?? '--'} %`} />
        </View>
      )}

      {(device.type === 'PLUG' || device.type === 'ENERGY_METER') && (
        <View style={styles.stats}>
          <Stat label="Power" value={`${Math.round(device.state.power ?? 0)} W`} />
          <Stat label="Voltage" value={`${Math.round(device.state.voltage ?? 0)} V`} />
          <Stat label="Current" value={`${(device.state.current ?? 0).toFixed(2)} A`} />
        </View>
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
  title: { color: colors.text, fontSize: 26, fontWeight: '700' },
  muted: { color: colors.muted },
  error: { color: colors.danger },
  bigButton: { backgroundColor: colors.card, borderRadius: 20, padding: 28, alignItems: 'center' },
  row: { flexDirection: 'row', gap: 10, backgroundColor: colors.card, borderRadius: 16, padding: 18, justifyContent: 'center' },
  small: { backgroundColor: colors.bg, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: colors.border },
  bigOn: { backgroundColor: colors.on },
  bigText: { color: colors.text, fontSize: 17, fontWeight: '600' },
  disabled: { opacity: 0.4 },
  stats: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  stat: { backgroundColor: colors.card, borderRadius: 16, padding: 16, minWidth: '45%', flexGrow: 1 },
  statValue: { color: colors.text, fontSize: 22, fontWeight: '700', marginTop: 4 },
});
