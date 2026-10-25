// Admin flow check against a running API. Usage:
//   ADMIN_EMAIL=... ADMIN_PASSWORD=... node scripts/admin-test.mjs
const API = process.env.API_URL ?? 'http://localhost:4000/v1';
const ADMIN_EMAIL = process.env.ADMIN_EMAIL;
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD;
if (!ADMIN_EMAIL || !ADMIN_PASSWORD) {
  console.error('Set ADMIN_EMAIL and ADMIN_PASSWORD');
  process.exit(1);
}

let failed = false;
const call = async (method, path, { token, body, expect } = {}) => {
  const r = await fetch(API + path, {
    method,
    headers: { 'content-type': 'application/json', ...(token ? { authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await r.text();
  const data = text ? JSON.parse(text) : null;
  const ok = r.status === expect;
  if (!ok) failed = true;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${method} ${path} -> ${r.status} (expected ${expect})${ok ? '' : ' ' + text}`);
  return data;
};

const admin = await call('POST', '/auth/login', { body: { email: ADMIN_EMAIL, password: ADMIN_PASSWORD }, expect: 200 });
const adminToken = admin.accessToken;

const customerEmail = `client${Date.now()}@example.test`;
const customerPassword = 'Client-password-1';
await call('POST', '/auth/register', { body: { email: customerEmail, password: customerPassword, name: 'Client' }, expect: 403 }); // self-signup off

const created = await call('POST', '/admin/customers', { token: adminToken, body: { email: customerEmail, name: 'Client', password: customerPassword }, expect: 201 });
const customerId = created.customer.id;

const provisioned = await call('POST', '/admin/devices', { token: adminToken, body: { type: 'PLUG', count: 1, customerId }, expect: 201 });
const device = provisioned.devices[0];
console.log(`  provisioned ${device.id} secret shown once: ${Boolean(device.secret)} assignedHome: ${provisioned.assignedHomeId}`);

const customer = await call('POST', '/auth/login', { body: { email: customerEmail, password: customerPassword }, expect: 200 });
const customerToken = customer.accessToken;
const homes = await call('GET', '/homes', { token: customerToken, expect: 200 });
const devices = await call('GET', `/devices?homeId=${homes.homes[0].id}`, { token: customerToken, expect: 200 });
const sees = devices.devices.some((d) => d.id === device.id);
console.log(`  customer sees the assigned device: ${sees}`);
if (!sees) failed = true;

await call('GET', '/admin/customers', { token: customerToken, expect: 403 }); // customers cannot use admin routes
await call('POST', '/admin/devices', { token: customerToken, body: { type: 'PLUG' }, expect: 403 });

await call('PATCH', `/admin/customers/${customerId}`, { token: adminToken, body: { disabled: true }, expect: 200 });
await call('POST', '/auth/login', { body: { email: customerEmail, password: customerPassword }, expect: 403 });
await call('PATCH', `/admin/customers/${customerId}`, { token: adminToken, body: { disabled: false }, expect: 200 });
await call('POST', '/auth/login', { body: { email: customerEmail, password: customerPassword }, expect: 200 });

const list = await call('GET', '/admin/devices', { token: adminToken, expect: 200 });
console.log(`  admin device list has ${list.devices.length} devices; owner of ${device.id}: ${list.devices.find((d) => d.id === device.id)?.owner}`);

console.log(failed ? '\nSOME CHECKS FAILED' : '\nALL ADMIN CHECKS PASSED');
process.exitCode = failed ? 1 : 0;
