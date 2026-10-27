import { renderToStaticMarkup } from 'react-dom/server';
import type { ComponentProps } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RardarShell from '@/components/RardarShell';

const state = vi.hoisted(() => ({ pending: false }));
vi.mock('next/navigation', () => ({ usePathname: () => '/' }));
vi.mock('next/link', () => ({
  default: ({ children, prefetch, ...props }: ComponentProps<'a'> & { prefetch?: boolean }) => <a {...props} data-prefetch={String(prefetch)}>{children}</a>,
  useLinkStatus: () => ({ pending: state.pending }),
}));
afterEach(() => { state.pending = false; });

describe('Rardar navigation feedback', () => {
  it.each([false, true])('shows only the real Link pending state without changing route or prefetch policy (%s)', pending => {
    state.pending = pending;
    const html = renderToStaticMarkup(<RardarShell><p>Current published content</p></RardarShell>);
    expect((html.match(new RegExp(`data-pending="${pending}"`, 'g')) ?? [])).toHaveLength(8);
    expect((html.match(/aria-label="正在切换页面"/g) ?? [])).toHaveLength(pending ? 8 : 0);
    expect((html.match(/aria-label="今日热榜"/g) ?? [])).toHaveLength(2);
    expect((html.match(/aria-label="历史回顾"/g) ?? [])).toHaveLength(2);
    expect(html).not.toContain('data-prefetch="true"');
    expect(html).not.toContain('?revision=');
    expect(html).toContain('Current published content');
    expect(html).toContain('href="/find"');
    expect(html).toContain('href="/admin"');
  });
});
