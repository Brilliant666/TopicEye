// Synthetic HTTP auth fixture only. No database, GitHub or Provider access.
import { createServer } from 'node:http';

let adminReads = 0;
const server = createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  const url = new URL(request.url, 'http://127.0.0.1');
  if (request.method !== 'GET') {
    response.writeHead(405).end('{}');
    return;
  }
  if (url.pathname === '/api/v1/auth/me') {
    if (!request.headers.cookie?.includes('topiceye_auth=synthetic-admin')) {
      response.writeHead(401).end('{}');
      return;
    }
    adminReads += 1;
    response.end(JSON.stringify({ id: 1, username: 'synthetic-admin', role: 'admin', is_active: true }));
    return;
  }
  if (url.pathname === '/fixture-stats') {
    response.end(JSON.stringify({ adminReads, providerCalls: 0, fixture: true }));
    return;
  }
  response.end(JSON.stringify({ flags: {}, total: 0, items: [], today_picks: 0 }));
});
server.listen(3411, '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
