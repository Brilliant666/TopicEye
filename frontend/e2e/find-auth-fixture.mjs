// Synthetic HTTP auth fixture only. No database, GitHub or Provider access.
import { createServer } from 'node:http';
import { periodSelection } from './selection-period-fixture.mjs';
import { refocusBoard } from './refocus-fixture.mjs';

let adminReads = 0;
const server = createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  const url = new URL(request.url, 'http://127.0.0.1');
  if (request.method === 'GET' && ['/api/v1/rardar/trending-today', '/api/v1/rardar/historical-hot'].includes(url.pathname)) {
    response.end(JSON.stringify(refocusBoard));
    return;
  }
  if (request.method === 'GET' && /\/rardar\/(trending-projects|historical-projects)\//.test(url.pathname)) {
    const project = refocusBoard.projects.find(item => item.projectId === url.pathname.split('/').at(-1));
    if (!project) { response.writeHead(404).end('{}'); return; }
    response.end(JSON.stringify({ ...project, generationId: refocusBoard.generationId, publishedAt: refocusBoard.publishedAt, sources: refocusBoard.sources }));
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/v1/rardar/discover/selection') {
    response.end(JSON.stringify(periodSelection));
    return;
  }
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
