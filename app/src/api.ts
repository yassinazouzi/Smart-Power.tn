import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_URL } from './config';

export type DeviceType = 'PLUG' | 'SWITCH' | 'SWITCH_MULTI' | 'DIMMER' | 'RGB_LIGHT' | 'CURTAIN' | 'SENSOR_TH' | 'ENERGY_METER';

export interface Device {
  id: string;
  name: string;
  type: DeviceType;
  model: string;
  channels: number;
  roomId: string | null;
  online: boolean;
  state: Record<string, any>;
}
export interface Room { id: string; name: string; icon: string }
export interface Home { id: string; name: string; rooms: Room[]; role: string; tariffPerKwh: number; currency: string; deviceCount: number }
export interface Scene { id: string; name: string; type: 'MANUAL' | 'AUTO'; enabled: boolean; actions: any[]; conditions: any[] }
export interface EnergySummary {
  totalKwh: number; cost: number; currency: string; livePowerW: number; peakW: number;
  series: { start: string; energyKwh: number }[];
  breakdown: { deviceId: string; name: string; energyKwh: number; cost: number; share: number }[];
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

const KEYS = { access: 'sp.access', refresh: 'sp.refresh' };
let accessToken: string | null = null;
let onSessionLost: (() => void) | null = null;

export const setSessionLostHandler = (fn: () => void) => (onSessionLost = fn);
export async function saveTokens(access: string, refresh: string) {
  accessToken = access;
  await AsyncStorage.setItem(KEYS.access, access);
  await AsyncStorage.setItem(KEYS.refresh, refresh);
}
export async function clearTokens() {
  accessToken = null;
  await AsyncStorage.removeItem(KEYS.access);
  await AsyncStorage.removeItem(KEYS.refresh);
}
export const loadRefreshToken = () => AsyncStorage.getItem(KEYS.refresh);

async function request<T>(method: string, path: string, body?: unknown, retried = false): Promise<T> {
  const res = await fetch(API_URL + path, {
    method,
    headers: { 'content-type': 'application/json', ...(accessToken ? { authorization: `Bearer ${accessToken}` } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401 && !retried && path !== '/auth/login' && path !== '/auth/refresh') {
    // Access token expired: rotate the refresh token once, then retry the request.
    const refresh = await loadRefreshToken();
    if (refresh) {
      try {
        const next = await request<{ accessToken: string; refreshToken: string }>('POST', '/auth/refresh', { refreshToken: refresh });
        await saveTokens(next.accessToken, next.refreshToken);
        return request<T>(method, path, body, true);
      } catch {
        /* fall through */
      }
    }
    await clearTokens();
    onSessionLost?.();
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.error ?? 'error', data?.message ?? `Request failed (${res.status})`);
  return data as T;
}

export const api = {
  login: (email: string, password: string) =>
    request<{ user: { id: string; name: string; email: string }; accessToken: string; refreshToken: string }>('POST', '/auth/login', { email, password }),
  register: (name: string, email: string, password: string) =>
    request<{ user: { id: string; name: string; email: string }; accessToken: string; refreshToken: string }>('POST', '/auth/register', { name, email, password }),
  logout: async () => {
    const refresh = await loadRefreshToken();
    if (refresh) await request('POST', '/auth/logout', { refreshToken: refresh }).catch(() => null);
    await clearTokens();
  },
  refresh: (refreshToken: string) =>
    request<{ accessToken: string; refreshToken: string }>('POST', '/auth/refresh', { refreshToken }),
  homes: () => request<{ homes: Home[] }>('GET', '/homes'),
  devices: (homeId: string) => request<{ devices: Device[] }>('GET', `/devices?homeId=${homeId}`),
  command: (deviceId: string, command: Record<string, unknown>) => request<{ accepted: unknown }>('POST', `/devices/${deviceId}/command`, command),
  energy: (homeId: string, period: 'day' | 'week' | 'month' | 'year') =>
    request<EnergySummary>('GET', `/energy/summary?homeId=${homeId}&period=${period}`),
  scenes: (homeId: string) => request<{ scenes: Scene[] }>('GET', `/scenes?homeId=${homeId}`),
  setSceneEnabled: (sceneId: string, enabled: boolean) => request('PATCH', `/scenes/${sceneId}`, { enabled }),
  runScene: (sceneId: string) => request<{ ok: boolean; errors: string[] }>('POST', `/scenes/${sceneId}/run`),
};
