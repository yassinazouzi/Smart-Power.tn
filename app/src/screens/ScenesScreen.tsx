import React, { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { api, Scene } from '../api';
import { useApp } from '../store';
import { colors } from '../theme';

export function ScenesScreen() {
  const homeId = useApp((s) => s.homeId);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (homeId) api.scenes(homeId).then((r) => setScenes(r.scenes)).catch((e) => setMessage(e.message));
  }, [homeId]);

  const run = async (scene: Scene) => {
    try {
      const res = await api.runScene(scene.id);
      setMessage(res.ok ? `"${scene.name}" ran` : `"${scene.name}": ${res.errors.join('; ')}`);
    } catch (e: any) {
      setMessage(e.message);
    }
  };

  const toggle = async (scene: Scene, enabled: boolean) => {
    setScenes((list) => list.map((s) => (s.id === scene.id ? { ...s, enabled } : s)));
    try {
      await api.setSceneEnabled(scene.id, enabled);
    } catch (e: any) {
      setMessage(e.message);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ padding: 20, gap: 12 }}>
      <Text style={styles.title}>Scenes</Text>
      {message && <Text style={styles.message}>{message}</Text>}
      {scenes.length === 0 && <Text style={styles.muted}>No scenes yet.</Text>}
      {scenes.map((s) => (
        <View key={s.id} style={styles.card}>
          <Pressable style={styles.cardBody} onPress={() => run(s)} disabled={s.type === 'AUTO'}>
            <Text style={styles.name}>{s.name}</Text>
            <Text style={styles.muted}>{s.type === 'MANUAL' ? 'Tap to run' : 'Automatic'} · {s.actions.length} actions</Text>
          </Pressable>
          {s.type === 'AUTO' && <Switch value={s.enabled} onValueChange={(v) => toggle(s, v)} trackColor={{ true: colors.accent }} />}
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  title: { color: colors.text, fontSize: 26, fontWeight: '700', paddingTop: 36 },
  muted: { color: colors.muted },
  message: { color: colors.text, backgroundColor: colors.card, padding: 12, borderRadius: 12 },
  card: { backgroundColor: colors.card, borderRadius: 16, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 12 },
  cardBody: { flex: 1 },
  name: { color: colors.text, fontSize: 16, fontWeight: '600' },
});
