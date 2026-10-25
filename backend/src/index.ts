import { createServer } from 'node:http';
import cors from 'cors';
import express from 'express';
import helmet from 'helmet';
import { pinoHttp } from 'pino-http';
import { config } from './config.js';
import { requireAuth } from './auth/middleware.js';
import { db } from './lib/db.js';
import { errorHandler } from './lib/errors.js';
import { logger } from './lib/logger.js';
import { startBroker } from './mqtt/broker.js';
import { startRealtime } from './realtime/socket.js';
import { adminRouter } from './routes/admin.js';
import { authRouter } from './routes/auth.js';
import { devicesRouter } from './routes/devices.js';
import { energyRouter } from './routes/energy.js';
import { homesRouter } from './routes/homes.js';
import { scenesRouter } from './routes/scenes.js';
import { startSceneEngine } from './scenes/engine.js';

const app = express();
app.set('trust proxy', 1);
app.use(helmet());
app.use(cors({ origin: config.corsOrigins }));
app.use(express.json({ limit: '100kb' }));
app.use(pinoHttp({ logger, autoLogging: { ignore: (req) => req.url === '/health' } }));

app.get('/health', (_req, res) => {
  res.json({ ok: true });
});

/** Public endpoints the app and devices need before login (pairing uses the MQTT address). */
app.get('/v1/config', (_req, res) => {
  res.json({ apiUrl: config.PUBLIC_API_URL, mqtt: { host: config.PUBLIC_MQTT_HOST, port: config.PUBLIC_MQTT_PORT, tls: true } });
});

app.use('/v1/auth', authRouter);
app.use('/v1/homes', requireAuth, homesRouter);
app.use('/v1/devices', requireAuth, devicesRouter);
app.use('/v1/energy', requireAuth, energyRouter);
app.use('/v1/scenes', requireAuth, scenesRouter);
app.use('/v1/admin', requireAuth, adminRouter);
app.use((_req, res) => {
  res.status(404).json({ error: 'not_found', message: 'Route not found' });
});
app.use(errorHandler);

async function main() {
  const server = createServer(app);
  startRealtime(server);
  const broker = await startBroker();
  const stopEngine = startSceneEngine();
  server.listen(config.PORT, () => logger.info(`SmartPower API listening on :${config.PORT}`));

  const shutdown = async () => {
    logger.info('shutting down');
    stopEngine();
    server.close();
    await broker.close();
    await db.$disconnect();
    process.exit(0);
  };
  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((err) => {
  logger.fatal({ err }, 'failed to start');
  process.exit(1);
});
