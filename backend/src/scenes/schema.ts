import { z } from 'zod';

const hhmm = z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, 'expected HH:mm');
const days = z.array(z.number().int().min(1).max(7)).max(7).default([]);

export const conditionSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('device'),
    deviceId: z.string(),
    key: z.string().min(1).max(32), // e.g. switch, power, temperature, humidity, position
    op: z.enum(['eq', 'neq', 'gt', 'lt']),
    value: z.union([z.string(), z.number(), z.boolean()]),
  }),
  z.object({ type: z.literal('time'), at: hhmm, days }),
]);

export const actionSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('device'), deviceId: z.string(), command: z.record(z.string(), z.unknown()) }),
  z.object({ type: z.literal('delay'), seconds: z.number().int().min(1).max(3600) }),
  z.object({ type: z.literal('scene'), sceneId: z.string(), action: z.enum(['run', 'enable', 'disable']) }),
  z.object({ type: z.literal('notify'), message: z.string().min(1).max(200) }),
]);

export const sceneInputSchema = z
  .object({
    name: z.string().min(1).max(60),
    icon: z.string().max(32).optional(),
    type: z.enum(['MANUAL', 'AUTO']),
    enabled: z.boolean().optional(),
    matchAll: z.boolean().optional(),
    conditions: z.array(conditionSchema).max(10).default([]),
    actions: z.array(actionSchema).min(1).max(30),
  })
  .refine((s) => s.type === 'MANUAL' || s.conditions.length > 0, { message: 'Automations need at least one condition', path: ['conditions'] });

export type Condition = z.infer<typeof conditionSchema>;
export type Action = z.infer<typeof actionSchema>;

export const timerInputSchema = z.object({
  at: hhmm,
  days,
  command: z.record(z.string(), z.unknown()),
  enabled: z.boolean().optional(),
});
