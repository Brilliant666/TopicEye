import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { consumeFindDraft, saveFindDraft } from '@/lib/rardar-find-draft';

let values: Map<string, string>;
beforeEach(() => {
  values = new Map();
  vi.stubGlobal('sessionStorage', { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
});
afterEach(() => vi.unstubAllGlobals());

describe('tab-local unsent Find draft', () => {
  const path = '/find?repositoryUrl=https%3A%2F%2Fgithub.com%2Ffixture%2Foriginal';
  const draft = { requirement: '  我需要自己的未提交需求\n保留输入原样。 ', repositoryUrl: 'https://github.com/fixture/typed-repository' };

  it('restores exact typed inputs only at the original URL and consumes them once without POST', () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    saveFindDraft(draft, path);
    expect(consumeFindDraft('/find')).toBeNull();
    expect(values.size).toBe(1);
    expect(consumeFindDraft(path)).toEqual(draft);
    expect(consumeFindDraft(path)).toBeNull();
    expect(values.size).toBe(0);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('serializes only input fields and the return URL, never private run/results or execution intent', () => {
    saveFindDraft({ ...draft, runId: 'must-not-save', result: { private: true }, execute: true } as typeof draft, path);
    expect(JSON.parse([...values.values()][0])).toEqual({ returnPath: path, ...draft });
  });

  it.each(['not-json', JSON.stringify({ returnPath: path, requirement: 1, repositoryUrl: '' }), JSON.stringify({ returnPath: path, requirement: 'x'.repeat(1201), repositoryUrl: '' })])('discards malformed temporary drafts', (raw) => {
    saveFindDraft(draft, path);
    const key = [...values.keys()][0]; values.set(key, raw);
    expect(consumeFindDraft(path)).toBeNull();
    expect(values.size).toBe(0);
  });

  it('does not block normal login when browser storage is disabled', () => {
    vi.stubGlobal('sessionStorage', { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } });
    expect(() => saveFindDraft(draft, path)).not.toThrow();
    expect(consumeFindDraft(path)).toBeNull();
  });
});
