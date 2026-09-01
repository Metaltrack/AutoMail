const test = require('node:test');
const assert = require('node:assert/strict');
const { createApp } = require('../src/app');

const config = {
  apiKey: 'test-shared-secret',
  mailFrom: 'Alerts <alerts@example.com>',
  adminEmail: 'admin@example.com'
};

function request(server, { method, path, headers = {}, body }) {
  return new Promise((resolve, reject) => {
    const http = require('http');
    const data = body === undefined ? undefined : JSON.stringify(body);
    const req = http.request({ port: server.address().port, method, path, headers: { ...headers, ...(data ? { 'content-type': 'application/json', 'content-length': Buffer.byteLength(data) } : {}) } }, (res) => {
      let responseBody = '';
      res.on('data', (chunk) => { responseBody += chunk; });
      res.on('end', () => resolve({ status: res.statusCode, body: JSON.parse(responseBody) }));
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

test('accepts an authenticated login-success notification and emails both recipients', async () => {
  const sent = [];
  const app = createApp({ config, mailer: { sendMail: async (mail) => { sent.push(mail); return { messageId: `${sent.length}` }; } }, logger: { info() {}, error() {} } });
  const server = app.listen(0);
  try {
    const result = await request(server, { method: 'POST', path: '/notifications/login-success', headers: { authorization: 'Bearer test-shared-secret' }, body: { userName: 'Rahul', userEmail: 'rahul@example.com', loginTime: '2026-09-01 17:30', device: 'Chrome on Windows' } });
    assert.equal(result.status, 202);
    assert.equal(sent.length, 2);
    assert.equal(sent[0].to, 'rahul@example.com');
    assert.equal(sent[1].to, 'admin@example.com');
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('rejects requests without the service API key', async () => {
  const app = createApp({ config, mailer: {}, logger: { info() {}, error() {} } });
  const server = app.listen(0);
  try {
    const result = await request(server, { method: 'POST', path: '/notifications/login-success', body: {} });
    assert.equal(result.status, 401);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
