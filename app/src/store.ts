import { create } from 'zustand';
import { api, Device, Home } from './api';

interface AppState {
  signedIn: boolean;
  homes: Home[];
  homeId: string | null;
  devices: Device[];
  setSignedIn: (v: boolean) => void;
  loadHomes: () => Promise<void>;
  selectHome: (id: string) => void;
  loadDevices: () => Promise<void>;
  /** Optimistic update: the UI reflects the change now; the device's own report confirms it later. */
  patchDevice: (id: string, state: Record<string, any>) => void;
}

export const useApp = create<AppState>((set, get) => ({
  signedIn: false,
  homes: [],
  homeId: null,
  devices: [],
  setSignedIn: (signedIn) => set({ signedIn }),
  loadHomes: async () => {
    const { homes } = await api.homes();
    set({ homes, homeId: get().homeId ?? homes[0]?.id ?? null });
  },
  selectHome: (homeId) => set({ homeId, devices: [] }),
  loadDevices: async () => {
    const homeId = get().homeId;
    if (!homeId) return;
    const { devices } = await api.devices(homeId);
    set({ devices });
  },
  patchDevice: (id, state) =>
    set((s) => ({ devices: s.devices.map((d) => (d.id === id ? { ...d, state: { ...d.state, ...state } } : d)) })),
}));
