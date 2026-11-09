/** Integration checks against the demo database: every page renders, CSRF and approval stay enforced. */
import assert from 'node:assert/strict';
import test from 'node:test';

process.env.NAV_UNLOCKED = 'true';

const { createApp } = await import('../app.js');
const { initDb, closeDb } = await import('../db.js');

initDb();
const app = createApp();
const server = await new Promise((resolve) => {
  const listener = app.listen(0, '127.0.0.1', () => resolve(listener));
});
const base = `http://127.0.0.1:${server.address().port}`;

const jar = new Map();
const cookies = () => [...jar.entries()].map(([name, value]) => `${name}=${value}`).join('; ');

function absorb(response) {
  for (const line of response.headers.getSetCookie ? response.headers.getSetCookie() : []) {
    const [pair] = line.split(';');
    const [name, ...rest] = pair.split('=');
    jar.set(name.trim(), rest.join('='));
  }
}

async function get(path) {
  const response = await fetch(base + path, { headers: { cookie: cookies() }, redirect: 'manual' });
  absorb(response);
  return response;
}

async function post(path, data = {}) {
  const response = await fetch(base + path, {
    method: 'POST',
    headers: { cookie: cookies(), 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(data),
    redirect: 'manual',
  });
  absorb(response);
  return response;
}

async function csrfFrom(path) {
  const html = await (await get(path)).text();
  return /name="_csrf" value="([^"]+)"/.exec(html)?.[1];
}

test.after(() => {
  server.close();
  return closeDb();
});

test('health reports the database', async () => {
  const response = await get('/health');
  assert.equal(response.status, 200);
  assert.match(await response.text(), /"database":"ok"/);
});

test('the public shop renders', async () => {
  const response = await get('/');
  assert.equal(response.status, 200);
  assert.match(await response.text(), /The Fad/);
});

test('sign-in lands on attendance', async () => {
  const token = await csrfFrom('/login');
  const response = await post('/login', { _csrf: token, username: 'dev_admin', password: 'Admin@1234' });
  assert.equal(response.status, 302);
  assert.equal(response.headers.get('location'), '/attendance/');
});

test('every staff page renders', async () => {
  const routes = [
    '/dashboard', '/pos/', '/orders/', '/orders/65', '/inventory/', '/inventory/history',
    '/inventory/30', '/attendance/', '/attendance/everyone', '/attendance/overtime',
    '/attendance/schedule', '/attendance/shift', '/admin/products/', '/admin/products/?variants=1',
    '/admin/products/30/edit', '/admin/products/30/photos', '/admin/products/categories',
    '/admin/products/new', '/admin/promos/', '/admin/promos/24', '/admin/promos/24/view',
    '/admin/promos/new', '/admin/staff/', '/admin/staff/10/edit', '/admin/staff/new',
    '/admin/refunds/', '/admin/refunds/sale/19', '/admin/audit/', '/promos/', '/product/30', '/account',
  ];
  for (const route of routes) {
    const response = await get(route);
    assert.equal(response.status, 200, `${route} returned ${response.status}`);
  }
});

test('a POST without the CSRF token is rejected', async () => {
  const response = await post('/admin/staff/10/active', { active: '0' });
  assert.equal(response.status, 400);
});

test('a management POST without an approval PIN is rejected', async () => {
  const token = await csrfFrom('/admin/staff/');
  const response = await post('/admin/staff/10/active', { _csrf: token, active: '0' });
  assert.equal(response.status, 403);
});

test('signing out clears the session', async () => {
  const token = await csrfFrom('/attendance/');
  const response = await post('/logout', { _csrf: token });
  assert.equal(response.status, 302);
  assert.equal((await get('/dashboard')).status, 302);
});
