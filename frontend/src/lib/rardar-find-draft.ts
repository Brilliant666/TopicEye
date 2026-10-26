export type FindDraft = { requirement: string; repositoryUrl: string };

const draftKey = 'rardar-find-login-draft-v1';

/** Tab-local, unsent inputs only; never save a run, result, owner or action flag. */
export function saveFindDraft(draft: FindDraft, returnPath: string): void {
  try {
    sessionStorage.setItem(draftKey, JSON.stringify({
      returnPath,
      requirement: draft.requirement,
      repositoryUrl: draft.repositoryUrl,
    }));
  } catch { /* optional draft recovery; storage can be disabled */ }
}

/** Restore only at the original Find URL, then remove the temporary draft. */
export function consumeFindDraft(returnPath: string): FindDraft | null {
  try {
    const raw = sessionStorage.getItem(draftKey);
    if (!raw) return null;
    let value: unknown;
    try { value = JSON.parse(raw); } catch { sessionStorage.removeItem(draftKey); return null; }
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      sessionStorage.removeItem(draftKey); return null;
    }
    const draft = value as Record<string, unknown>;
    if (typeof draft.returnPath !== 'string' || typeof draft.requirement !== 'string' || draft.requirement.length > 1200 || typeof draft.repositoryUrl !== 'string' || draft.repositoryUrl.length > 4096) {
      sessionStorage.removeItem(draftKey); return null;
    }
    if (draft.returnPath !== returnPath) return null;
    sessionStorage.removeItem(draftKey);
    return { requirement: draft.requirement, repositoryUrl: draft.repositoryUrl };
  } catch {
    return null;
  }
}
