import { describe, expect, it } from 'vitest';

import { RARDAR_NAVIGATION } from '../../../product-profile.config.js';
import { RARDAR_FOUNDATION_PAGES, RARDAR_FOUNDATION_SLOTS } from '@/lib/rardar-foundation';

describe('Rardar foundation content contract', () => {
  it('defines exactly the six approved user-facing route shells', () => {
    const pages = Object.values(RARDAR_FOUNDATION_PAGES);

    expect(pages).toHaveLength(6);
    expect(pages.map((page) => page.href)).toEqual(
      RARDAR_NAVIGATION.map((item) => item.href),
    );
  });

  it('keeps every route honest about its unconnected capability', () => {
    for (const page of Object.values(RARDAR_FOUNDATION_PAGES).filter((item) => item.key !== 'today')) {
      expect(page.title).toContain('尚未接入');
      expect(page.slot.length).toBeGreaterThan(0);
      expect(page.nextStep).toContain('后续');
    }
    expect(RARDAR_FOUNDATION_PAGES.today.title).toBe('GitHub 24h 爆发事实');
  });

  it('reserves only the three approved future integration slots', () => {
    expect(RARDAR_FOUNDATION_SLOTS.map((slot) => slot.name)).toEqual([
      'Intelligence Adapter',
      'Find Project Control Plane',
      'AI Runtime',
    ]);
  });

  it('does not encode fixture results or fake ranking values', () => {
    const contract = JSON.stringify({ RARDAR_FOUNDATION_PAGES, RARDAR_FOUNDATION_SLOTS });

    expect(contract).not.toMatch(/fixtureRevision|observedStarDelta|quickCandidates|jobId/);
    expect(contract).not.toMatch(/Top\s*[0-9]+|\+[0-9]+\s*Star/i);
  });
});
