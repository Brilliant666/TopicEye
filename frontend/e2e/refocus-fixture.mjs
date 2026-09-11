// Explicit synthetic browser fixtures; never presented as live source evidence.
const generationId = 'boards-' + 'a'.repeat(64);
export const refocusBoard = {
  schemaVersion: 1, generationId, publishedAt: '2026-09-10T00:00:00Z', checkedAt: '2026-09-10T00:00:00Z',
  sources: ['github', 'trendshift'].map(source => ({ source, label: source === 'github' ? 'GitHub Trending' : 'Trendshift', status: 'healthy', sourceDate: null, fetchedAt: '2026-09-10T00:00:00Z', count: 22, errorCode: null })),
  projects: Array.from({ length: 23 }, (_, i) => ({
    projectId: `fixture-project-${i}--` + 'b'.repeat(20), repository: `fixture/project-${i}`, repositoryUrl: `https://github.com/fixture/project-${i}`, githubRepositoryId: null,
    description: i === 0 ? 'A real-material shape, synthetic fixture content.' : null, totalStars: null, dualListed: i === 0,
    appearances: (i === 0 ? ['github', 'trendshift'] : [i % 2 ? 'github' : 'trendshift']).map(source => ({ source, rank: i + 1, sourceDate: null, fetchedAt: '2026-09-10T00:00:00Z', period: 'daily', reportedDelta: null })),
    materialState: 'unavailable', profile: null, historyAppearances: 1, firstSeenAt: null, lastSeenAt: null,
  })),
};
