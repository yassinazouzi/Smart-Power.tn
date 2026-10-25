import React, { useEffect, useState } from 'react';
import { ActivityIndicator, StatusBar, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { api, clearTokens, loadRefreshToken, saveTokens, setSessionLostHandler } from './src/api';
import { AppNavigator } from './src/navigation';
import { LoginScreen } from './src/screens/LoginScreen';
import { useApp } from './src/store';
import { colors } from './src/theme';

function Root() {
  const { signedIn, setSignedIn, loadHomes } = useApp();
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    setSessionLostHandler(() => useApp.getState().setSignedIn(false));
    (async () => {
      // Try to restore a session from the stored refresh token.
      try {
        const refresh = await loadRefreshToken();
        if (refresh) {
          const next = await api.refresh(refresh);
          await saveTokens(next.accessToken, next.refreshToken);
          await loadHomes();
          setSignedIn(true);
        }
      } catch {
        await clearTokens();
      } finally {
        setBooting(false);
      }
    })();
  }, [loadHomes, setSignedIn]);

  if (booting) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.bg, justifyContent: 'center' }}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }
  if (!signedIn) return <LoginScreen />;
  return <AppNavigator />;
}

export default function App() {
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="light-content" />
      <Root />
    </SafeAreaProvider>
  );
}
