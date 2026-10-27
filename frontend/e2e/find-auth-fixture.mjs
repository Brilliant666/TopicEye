// Synthetic HTTP auth fixture only. No database, GitHub or Provider access.
import { createServer } from 'node:http';
import { createHash, randomUUID } from 'node:crypto';
import { periodSelection } from './selection-period-fixture.mjs';
import { refocusBoard, refocusHistory } from './refocus-fixture.mjs';
import { savedSharedInsight, syntheticReader } from './public-reading-fixture.mjs';

let adminReads = 0;
let readerReads = 0;
const postPaths = [];
const insightReads = [];
const privateFindReads = [];
const publicSnapshotReads = [];
let publicPointerReads = 0;
let legacyBoardReads = 0;
let publicationVariant = 'baseline';
let pointerDelayMs = 0;
const fixturePublication = randomUUID();
const publishedSnapshots = new Map();

function publishedView(view) {
  const source = view === 'historical-hot' ? refocusHistory : refocusBoard;
  const board = structuredClone(source);
  // This marker makes separate fixture processes different immutable documents,
  // including when a previous production Next data cache remains on disk.
  board.fixturePublication = `${fixturePublication}:${publicationVariant}`;
  if (publicationVariant !== 'baseline') {
    board.projects[0].displayProfile.officialTaglineZh = `合成发布版本 ${publicationVariant}，只验证发布成品切换。`;
  }
  const revision = createHash('sha256').update(JSON.stringify(board)).digest('hex');
  publishedSnapshots.set(`${view}/${revision}`, { ...board, readingRevision: revision });
  return { revision, publishedAt: board.dailyReview?.publishedAt || board.publishedAt, generationId: board.generationId };
}

const server = createServer((request, response) => {
  response.setHeader('Content-Type', 'application/json');
  response.setHeader('Cache-Control', 'no-store');
  const url = new URL(request.url, 'http://127.0.0.1');
  const isAdmin = request.headers.cookie?.includes('topiceye_auth=synthetic-admin');
  const isReader = request.headers.cookie?.includes('topiceye_auth=synthetic-reader');
  if (request.method === 'POST' && url.pathname === '/fixture-public-reading') {
    publicationVariant = url.searchParams.get('variant') || 'baseline';
    pointerDelayMs = Math.min(3000, Math.max(0, Number(url.searchParams.get('delay')) || 0));
    response.end(JSON.stringify({ fixture: true }));
    return;
  }
  if (request.method === 'POST') postPaths.push(url.pathname);
  if (request.method === 'POST' && url.pathname === '/api/v1/auth/login') {
    // Deliberately accepts any input: this is a UI session fixture, not an
    // authentication implementation. It never consults accounts or secrets.
    response.setHeader('Set-Cookie', 'topiceye_auth=synthetic-reader; Path=/; HttpOnly; SameSite=Lax');
    response.end(JSON.stringify({ access_token: 'synthetic-presence-only', token_type: 'bearer', expires_at: '2099-01-01T00:00:00Z', user: syntheticReader }));
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/v1/rardar/public-reading') {
    publicPointerReads += 1;
    const body = JSON.stringify({ schemaVersion: 1, views: {
      'trending-today': publishedView('trending-today'),
      'historical-hot': publishedView('historical-hot'),
    } });
    if (pointerDelayMs) setTimeout(() => response.end(body), pointerDelayMs);
    else response.end(body);
    return;
  }
  if (request.method === 'GET' && url.pathname.startsWith('/api/v1/rardar/public-reading/')) {
    const key = url.pathname.slice('/api/v1/rardar/public-reading/'.length);
    const board = publishedSnapshots.get(key);
    if (!board) { response.writeHead(404).end('{}'); return; }
    const [view, revision] = key.split('/');
    publicSnapshotReads.push({ view, revision, hasCookie: Boolean(request.headers.cookie), hasAuthorization: Boolean(request.headers.authorization) });
    response.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
    response.end(JSON.stringify(board));
    return;
  }
  if (request.method === 'GET' && ['/api/v1/rardar/trending-today', '/api/v1/rardar/historical-hot'].includes(url.pathname)) {
    legacyBoardReads += 1;
    response.end(JSON.stringify(url.pathname.endsWith('/historical-hot') ? refocusHistory : refocusBoard));
    return;
  }
  if (request.method === 'GET' && /\/rardar\/(trending-projects|historical-projects)\//.test(url.pathname)) {
    const readingRevision = url.searchParams.get('readingRevision');
    const historical = url.pathname.includes('/historical-projects/');
    const source = readingRevision !== null
      ? publishedSnapshots.get(`${historical ? 'historical-hot' : 'trending-today'}/${readingRevision}`)
      : refocusBoard;
    if (!source || (!historical && readingRevision !== null && url.searchParams.get('generation') !== source.generationId)) {
      response.writeHead(404).end('{}'); return;
    }
    const project = source.projects.find(item => item.projectId === url.pathname.split('/').at(-1));
    if (!project) { response.writeHead(404).end('{}'); return; }
    response.end(JSON.stringify({ ...project, generationId: source.generationId, readingRevision: source.readingRevision, publishedAt: source.publishedAt, sources: source.sources }));
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
    response.end(JSON.stringify({ adminReads, readerReads, postPaths, insightReads, privateFindReads, publicPointerReads, publicSnapshotReads, legacyBoardReads, providerCalls: 0, fixture: true }));
    return;
  }
  response.end(JSON.stringify({ flags: {}, total: 0, items: [], today_picks: 0 }));
});
server.listen(3411, '127.0.0.1');
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close());
