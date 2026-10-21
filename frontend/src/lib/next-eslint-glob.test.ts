import { afterAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { mkdtempSync, mkdirSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { ESLint } from 'eslint';

const require = createRequire(import.meta.url);
const { getRootDirs } = require('@next/eslint-plugin-next/dist/utils/get-root-dirs');
const plugin = require('@next/eslint-plugin-next');
const root = realpathSync.native(mkdtempSync(join(tmpdir(), 'next-eslint-glob-')));
for (const name of ['alpha', 'beta']) {
  mkdirSync(join(root, 'apps', name, 'pages'), { recursive: true });
  writeFileSync(join(root, 'apps', name, 'pages', 'index.jsx'), 'export default function Page() {}');
}
writeFileSync(join(root, 'apps', 'not-a-directory'), '');
afterAll(() => rmSync(root, { recursive: true, force: true }));
const normalized = (paths: string[]) => paths.map(p => p.replaceAll('\\', '/')).sort();
const resolveRoots = (rootDir?: string | string[]) => normalized(getRootDirs({
  cwd: root, settings: { next: rootDir === undefined ? {} : { rootDir } },
}));

describe('Next ESLint directory glob replacement', () => {
  it('retains cwd defaults, literal roots, directory-only globs and missing roots', () => {
    expect(resolveRoots()).toEqual(normalized([root]));
    expect(resolveRoots(join(root, 'apps', 'alpha'))).toEqual(normalized([join(root, 'apps', 'alpha')]));
    expect(resolveRoots(join(root, 'apps', '*'))).toEqual(normalized(['alpha', 'beta'].map(n => join(root, 'apps', n))));
    expect(resolveRoots(join(root, 'missing', '*'))).toEqual([]);
  });
  it('retains brace patterns, array settings and Windows path normalization', () => {
    expect(resolveRoots(join(root, 'apps', '{alpha,beta}'))).toEqual(normalized(['alpha', 'beta'].map(n => join(root, 'apps', n))));
    expect(resolveRoots([join(root, 'apps', 'alpha'), join(root, 'apps', 'beta')])).toEqual(normalized(['alpha', 'beta'].map(n => join(root, 'apps', n))));
    expect(resolveRoots(join(root, 'apps', '*').replaceAll('/', '\\'))).toEqual(resolveRoots(join(root, 'apps', '*')));
  });
  it('does not expand a literal root or include it in descendant-only matches', () => {
    expect(resolveRoots(join(root, 'apps', 'alpha', '**'))).toEqual(normalized([join(root, 'apps', 'alpha', 'pages')]));
    expect(resolveRoots(join(root, 'apps', 'alpha', '**', '*'))).toEqual(normalized([join(root, 'apps', 'alpha', 'pages')]));
  });
  it('keeps the actual Next link rule active rather than suppressing its diagnostics', async () => {
    const eslint = new ESLint({
      cwd: root, overrideConfigFile: true,
      overrideConfig: [{
        files: ['**/*.jsx'],
        languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
        plugins: { '@next/next': plugin },
        settings: { next: { rootDir: join(root, 'apps', '*') } },
        rules: { '@next/next/no-html-link-for-pages': 'error' },
      }],
    });
    const [bad] = await eslint.lintText('export default () => <a href="/">Home</a>', { filePath: join(root, 'test.jsx') });
    expect(bad.messages.map(m => m.ruleId)).toContain('@next/next/no-html-link-for-pages');
    const [good] = await eslint.lintText('export default () => <a href="https://example.com">External</a>', { filePath: join(root, 'test.jsx') });
    expect(good.messages).toEqual([]);
  });
});
