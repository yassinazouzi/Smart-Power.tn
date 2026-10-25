import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { colors } from './theme';
import { DeviceScreen } from './screens/DeviceScreen';
import { EnergyScreen } from './screens/EnergyScreen';
import { HomeScreen } from './screens/HomeScreen';
import { ScenesScreen } from './screens/ScenesScreen';

export type RootParams = { Main: undefined; Device: { id: string } };

const Stack = createNativeStackNavigator<RootParams>();
const Tabs = createBottomTabNavigator();

const theme = {
  dark: true,
  colors: { primary: colors.accent, background: colors.bg, card: colors.card, text: colors.text, border: colors.border, notification: colors.danger },
  fonts: {} as any,
};

function MainTabs() {
  return (
    <Tabs.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.border },
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.muted,
      }}
    >
      <Tabs.Screen name="Home" component={HomeScreen} />
      <Tabs.Screen name="Energy" component={EnergyScreen} />
      <Tabs.Screen name="Scenes" component={ScenesScreen} />
    </Tabs.Navigator>
  );
}

/** Signed-in navigation: tabs plus a pushed device detail screen. */
export function AppNavigator() {
  return (
    <NavigationContainer theme={theme}>
      <Stack.Navigator>
        <Stack.Screen name="Main" component={MainTabs} options={{ headerShown: false }} />
        <Stack.Screen name="Device" component={DeviceScreen} options={{ headerStyle: { backgroundColor: colors.bg }, headerTintColor: colors.text, title: '' }} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
