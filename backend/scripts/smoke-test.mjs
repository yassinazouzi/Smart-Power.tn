// Usage: provision devices (npm run device:create -- --type PLUG --json > dev-plug.json, etc.),
// start simulators for them, then: DEVICES_DIR=<dir> node scripts/smoke-test.mjs
// End-to-end smoke test against a running SmartPower API with simulators connected.
import fs from 'node:fs';
const API = 'http://localhost:4000/v1';
const devs = Object.fromEntries(['plug', 'multi', 'th'].map((k) => [k, JSON.parse(fs.readFileSync(`${process.env.DEVICES_DIR ?? '.'}/dev-${k}.json`, 'utf8'))[0]]));
let token;
const call = async (method, path, body, expect) => {
  const r = await fetch(API + path, { method, headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) }, body: body ? JSON.stringify(body) : undefined });
  const text = await r.text();
  const data = text ? JSON.parse(text) : null;
  const ok = expect ? r.status === expect : r.ok;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${method} ${path} -> ${r.status}${ok ? '' : ' ' + text}`);
  if (!ok) process.exitCode = 1;
  return data;
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const email = `test${Date.now()}@smartpower.tn`;
const reg = await call('POST', '/auth/register', { email, password: 'password123', name: 'Test User' }, 201);
token = reg.accessToken;
await call('POST', '/auth/login', { email, password: 'wrong-pass' }, 401);
const refreshed = await call('POST', '/auth/refresh', { refreshToken: reg.refreshToken });
await call('POST', '/auth/refresh', { refreshToken: reg.refreshToken }, 401); // single-use
token = refreshed.accessToken;

const { homes } = await call('GET', '/homes');
const home = homes[0];
console.log('  home:', home.name, 'rooms:', home.rooms.map((r) => r.name).join(', '));

await call('POST', '/devices/claim', { deviceId: devs.plug.id, claimCode: 'WRONG123', homeId: home.id }, 404);
for (const [k, name] of [['plug', 'Heater plug'], ['multi', 'Kitchen lights'], ['th', 'Living sensor']]) {
  await call('POST', '/devices/claim', { deviceId: devs[k].id, claimCode: devs[k].claimCode, homeId: home.id, roomId: home.rooms[0].id, name }, 201);
}
await sleep(500);
let { devices } = await call('GET', `/devices?homeId=${home.id}`);
console.log('  devices:', devices.map((d) => `${d.name}[${d.type}] online=${d.online}`).join(' | '));

await call('POST', `/devices/${devs.plug.id}/command`, { switch: 'on' }, 202);
await call('POST', `/devices/${devs.plug.id}/command`, { brightness: 50 }, 400); // not valid for a plug
await call('POST', `/devices/${devs.multi.id}/command`, { switches: [{ ch: 1, switch: 'on' }] }, 202);
await call('POST', `/devices/${devs.multi.id}/command`, { switches: [{ ch: 7, switch: 'on' }] }, 400);
await sleep(5000);
({ devices } = await call('GET', `/devices?homeId=${home.id}`));
for (const d of devices) console.log(`  ${d.name}: ${JSON.stringify(d.state)}`);

await call('POST', `/devices/${devs.plug.id}/timers`, { at: '23:00', days: [1, 2, 3, 4, 5], command: { switch: 'off' } }, 201);
const { timers } = await call('GET', `/devices/${devs.plug.id}/timers`);
console.log('  timers:', timers.length);

const manual = await call('POST', '/scenes', { homeId: home.id, name: 'All off', type: 'MANUAL', actions: [{ type: 'device', deviceId: devs.plug.id, command: { switch: 'off' } }, { type: 'device', deviceId: devs.multi.id, command: { switch: 'off' } }] }, 201);
await call('POST', '/scenes', { homeId: home.id, name: 'Bad', type: 'AUTO', actions: [{ type: 'notify', message: 'x' }] }, 400); // auto needs a condition
await call('POST', '/scenes', { homeId: home.id, name: 'Too hot', type: 'AUTO', conditions: [{ type: 'device', deviceId: devs.th.id, key: 'temperature', op: 'gt', value: -50 }], actions: [{ type: 'device', deviceId: devs.multi.id, command: { switches: [{ ch: 0, switch: 'on' }] } }] }, 201);
const run = await call('POST', `/scenes/${manual.scene.id}/run`);
console.log('  manual run:', JSON.stringify(run));
await sleep(4000);
({ devices } = await call('GET', `/devices?homeId=${home.id}`));
for (const d of devices) console.log(`  ${d.name}: ${JSON.stringify(d.state)}`);

await call('POST', `/devices/${devs.plug.id}/command`, { switch: 'on' }, 202);
await sleep(7000);
const energy = await call('GET', `/energy/summary?homeId=${home.id}&period=day`);
console.log(`  energy today: ${energy.totalKwh} kWh, live ${energy.livePowerW} W, cost ${energy.cost} ${energy.currency}, buckets ${energy.series.length}, breakdown ${JSON.stringify(energy.breakdown)}`);
await call('GET', `/energy/summary?homeId=${home.id}&period=year`);
await call('GET', `/devices/${devs.plug.id}/energy?period=week`);

// Another user must not see this home's devices.
const other = await call('POST', '/auth/register', { email: `other${Date.now()}@smartpower.tn`, password: 'password123', name: 'Other' }, 201);
token = other.accessToken;
await call('GET', `/devices/${devs.plug.id}`, null, 404);
await call('POST', '/devices/claim', { deviceId: devs.plug.id, claimCode: devs.plug.claimCode, homeId: (await call('GET', '/homes')).homes[0].id }, 409);
console.log(process.exitCode ? '\nSOME CHECKS FAILED' : '\nALL CHECKS PASSED');
