import 'dotenv/config';
import { z } from 'zod';

const schema = z.object({
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  PORT: z.coerce.number().default(4000),
  PUBLIC_API_URL: z.string().default('https://api.smartpower.tn'),
  CORS_ORIGINS: z.string().default('https://smartpower.tn'),
  DATABASE_URL: z.string().startsWith('mysql://', 'DATABASE_URL must be a mysql:// URL'),
  JWT_SECRET: z.string().min(16, 'JWT_SECRET must be at least 16 characters'),
  ACCESS_TOKEN_TTL: z.string().default('15m'),
  REFRESH_TOKEN_TTL_DAYS: z.coerce.number().default(30),
  MQTT_PORT: z.coerce.number().default(1883),
  MQTT_WS_PORT: z.coerce.number().default(8083),
  PUBLIC_MQTT_HOST: z.string().default('mqtt.smartpower.tn'),
  PUBLIC_MQTT_PORT: z.coerce.number().default(8883),
  ENERGY_SAMPLE_INTERVAL: z.coerce.number().default(60),
  // Off by default: admins create customer accounts. Turn on only for an open signup.
  ALLOW_SELF_REGISTRATION: z
    .enum(['true', 'false'])
    .default('false')
    .transform((v) => v === 'true'),
});

const parsed = schema.safeParse(process.env);
if (!parsed.success) {
  console.error('Invalid environment:', parsed.error.flatten().fieldErrors);
  process.exit(1);
}

export const config = {
  ...parsed.data,
  corsOrigins: parsed.data.CORS_ORIGINS.split(',').map((s) => s.trim()),
};
