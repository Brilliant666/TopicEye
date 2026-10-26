// Synthetic HTTP auth fixture only. No database, GitHub or Provider access.
import { createServer } from 'node:http';
import { periodSelection } from './selection-period-fixture.mjs';
import { refocusBoard, refocusHistory } from './refocus-fixture.mjs';
import { savedSharedInsight, syntheticReader } from './public-reading-fixture.mjs';

let adminReads = 0;
let readerReads = 0;
const postPaths = [];
const insightReads = [];
const privateFindReads = [];
const server = createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  const url = new URL(request.url, 'http://127.0.0.1');
  const isAdmin = request.headers.cookie?.includes('topiceye_auth=synthetic-admin');
  const isReader = request.headers.cookie?.includes('topiceye_auth=synthetic-reader');
  if (request.method === 'POST') postPaths.push(url.pathname);
  if (request.method === 'POST' && url.pathname === '/api/v1/auth/login') {
    // Deliberately accepts any input: this is a UI session fixture, not an
    // authentication implementation. It never consults accounts or secrets.
    response.setHeader('Set-Cookie', 'topiceye_auth=synthetic-reader; Path=/; HttpOnly; SameSite=Lax');
    response.end(JSON.stringify({ access_token: 'synthetic-presence-only', token_type: 'bearer', expires_at: '2099-01-01T00:00:00Z', user: syntheticReader }));
    return;
  }
  if (request.method === 'GET' && ['/api/v1/rardar/trending-today', '/api/v1/rardar/historical-hot'].includes(url.pathname)) {
    response.end(JSON.stringify(url.pathname.endsWith('/historical-hot') ? refocusHistory : refocusBoard));
    return;
  }
  if (request.method === 'GET' && /\/rardar\/(trending-projects|historical-projects)\//.test(url.pathname)) {
    const project = refocusBoard.projects.find(item => item.projectId === url.pathname.split('/').at(-1));
    if (!project) { response.writeHead(404).end('{}'); return; }
    response.end(JSON.stringify({ ...project, generationId: refocusBoard.generationId, publishedAt: refocusBoard.publishedAt, sources: refocusBoard.sources }));
    return;
  }
  if (request.method === 'GET' && url.pathname.startsWith('/api/v1/rardar/project-insights/')) {
    insightReads.push({ projectId: url.pathname.split('/').at(-1), generationId: url.searchParams.get('generationId'), context: url.searchParams.get('context') });
    const savedProject = refocusBoard.projects[1];
    response.end(JSON.stringify(url.pathname.endsWith(`/${savedProject.projectId}`)
      && url.searchParams.get('generationId') === refocusBoard.generationId
      && ['trending', 'historical_hot'].includes(url.searchParams.get('context'))
      ? savedSharedInsight(savedProject, refocusBoard.generationId)
      : { state: 'unprocessed', result: null, errorCode: null, cacheHit: false }));
    return;
  }
  if (request.method === 'GET' && url.pathname.startsWith('/api/v1/rardar/find-runs')) {
    privateFindReads.push(url.pathname);
    if (!isAdmin && !isReader) { response.writeHead(401).end('{}'); return; }
    if (url.pathname !== '/api/v1/rardar/find-runs') { response.writeHead(404).end('{}'); return; }
    response.end(JSON.stringify({ runs: [] }));
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
    if (!isAdmin && !isReader) {
      response.writeHead(401).end('{}');
      return;
    }
    if (isAdmin) adminReads += 1;
    if (isReader) readerReads += 1;
    response.end(JSON.stringify(isAdmin ? { ...syntheticReader, id: 1, username: 'synthetic-admin', role: 'admin' } : syntheticReader));
    return;
  }
  if (url.pathname === '/api/v1/auth/oauth/providers') {
    response.end(JSON.stringify({ providers: [] }));
    return;
  }
  if (url.pathname === '/fixture-stats') {
    response.end(JSON.stringify({ adminReads, readerReads, postPaths, insightReads, privateFindReads, providerCalls: 0, fixture: true }));
    return;
  }
  response.end(JSON.stringify({ flags: {}, total: 0, items: [], today_picks: 0 }));
});
server.listen(3411, '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
