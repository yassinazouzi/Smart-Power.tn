import { PrismaMariaDb } from '@prisma/adapter-mariadb';
import { config } from '../config.js';
import { PrismaClient } from '../generated/prisma/client.js';

// DATABASE_URL: mysql://user:password@host:3306/database
const url = new URL(config.DATABASE_URL);
const adapter = new PrismaMariaDb({
  host: url.hostname,
  port: Number(url.port || 3306),
  user: decodeURIComponent(url.username),
  password: decodeURIComponent(url.password),
  database: url.pathname.slice(1),
  connectionLimit: 10,
});

export const db = new PrismaClient({ adapter });
