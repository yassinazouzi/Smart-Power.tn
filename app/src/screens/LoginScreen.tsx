import React, { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { api, ApiError, saveTokens } from '../api';
import { useApp } from '../store';
import { colors } from '../theme';

export function LoginScreen() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setSignedIn = useApp((s) => s.setSignedIn);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = mode === 'login' ? await api.login(email.trim(), password) : await api.register(name.trim(), email.trim(), password);
      await saveTokens(res.accessToken, res.refreshToken);
      await useApp.getState().loadHomes();
      setSignedIn(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Cannot reach SmartPower. Check your connection.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.brand}>SmartPower</Text>
      <Text style={styles.subtitle}>Control your home and see what it uses.</Text>

      {mode === 'register' && (
        <TextInput style={styles.input} placeholder="Name" placeholderTextColor={colors.muted} value={name} onChangeText={setName} />
      )}
      <TextInput style={styles.input} placeholder="Email" placeholderTextColor={colors.muted} autoCapitalize="none" keyboardType="email-address" value={email} onChangeText={setEmail} />
      <TextInput style={styles.input} placeholder="Password" placeholderTextColor={colors.muted} secureTextEntry value={password} onChangeText={setPassword} />

      {error && <Text style={styles.error}>{error}</Text>}

      <Pressable style={[styles.button, busy && styles.disabled]} onPress={submit} disabled={busy}>
        {busy ? <ActivityIndicator color={colors.bg} /> : <Text style={styles.buttonText}>{mode === 'login' ? 'Sign in' : 'Create account'}</Text>}
      </Pressable>

      <Pressable onPress={() => setMode(mode === 'login' ? 'register' : 'login')}>
        <Text style={styles.link}>{mode === 'login' ? 'New here? Create an account' : 'Have an account? Sign in'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, padding: 24, justifyContent: 'center', gap: 12 },
  brand: { color: colors.accent, fontSize: 36, fontWeight: '800' },
  subtitle: { color: colors.muted, marginBottom: 16 },
  input: { backgroundColor: colors.card, color: colors.text, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: colors.border },
  error: { color: colors.danger },
  button: { backgroundColor: colors.accent, borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 4 },
  buttonText: { color: colors.bg, fontWeight: '700', fontSize: 16 },
  disabled: { opacity: 0.6 },
  link: { color: colors.accent, textAlign: 'center', marginTop: 8 },
});
