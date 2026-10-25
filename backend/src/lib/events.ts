import { EventEmitter } from 'node:events';

export interface DeviceStateEvent {
  deviceId: string;
  homeId: string | null;
  state: Record<string, unknown>;
  previous: Record<string, unknown>;
}

export interface DeviceOnlineEvent {
  deviceId: string;
  homeId: string | null;
  online: boolean;
}

export interface TelemetryEvent {
  deviceId: string;
  homeId: string | null;
  powerW: number;
  voltageV?: number;
  currentA?: number;
  temperature?: number;
  humidity?: number;
}

export interface SceneRunEvent {
  sceneId: string;
  homeId: string;
  ok: boolean;
  trigger: string;
}

interface EventMap {
  'device:state': [DeviceStateEvent];
  'device:online': [DeviceOnlineEvent];
  'device:telemetry': [TelemetryEvent];
  'scene:run': [SceneRunEvent];
  notification: [{ homeId: string; title: string; message: string }];
}

/** In-process bus connecting the MQTT gateway, realtime sockets and the automation engine. */
export const bus = new EventEmitter<EventMap>();
bus.setMaxListeners(50);
