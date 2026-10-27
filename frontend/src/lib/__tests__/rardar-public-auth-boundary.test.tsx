import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ClientLayout from '@/components/ClientLayout';
import RardarTrendingPage from '@/components/RardarTrendingPage';
import RardarProjectDetailPage from '@/components/RardarProjectDetailPage';
import RardarFindProjectPage from '@/components/RardarFindProjectPage';
import RardarFoundationPage from '@/components/RardarFoundationPage';
import LoginPage from '@/app/login/page';
import type { AuthUser } from '@/types';
import type { TrendingBoard, TrendingDetail } from '@/lib/rardar-trending';

const state = vi.hoisted(() => ({ pathname: '/' }));
vi.mock('next/navigation', () => ({
  usePathname: () => state.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  notFound: () => { throw new Error('not found'); },
}));
vi.mock('@/lib/product-profile', async (original) => ({
  ...await original<typeof import('@/lib/product-profile')>(),
  activeProductProfile: { rardarEnabled: true },
  isRardarProduct: () => true,
}));
afterEach(() => vi.unstubAllGlobals());

const detail: TrendingDetail = {
  projectId: 'public-saved-project', repository: 'fixture/public-project',
  repositoryUrl: 'https://github.com/fixture/public-project', githubRepositoryId: null,
  description: '已保存的公开项目介绍', totalStars: 1200, dualListed: false,
  appearances: [], materialState: 'partial', profile: null, generationId: 'boards-saved',
};
const board: TrendingBoard = { schemaVersion: 1, generationId: 'boards-saved', publishedAt: null, checkedAt: null, sources: [], projects: [detail] };

function renderPage(pathname: string, page: React.ReactNode, user: AuthUser | null = null) {
  state.pathname = pathname;
  return renderToStaticMarkup(<ClientLayout initialData={{ user, featureFlags: {}, counts: null }}>{page}</ClientLayout>);
}

describe('Rardar public reading uses the real lightweight authentication tree', () => {
  it.each([
    ['/', <RardarTrendingPage key="today" board={board} />, '双榜项目清单'],
    ['/historical-hot', <RardarTrendingPage key="history" historical board={board} />, '历史回顾'],
    ['/project/stable/public-saved-project', <RardarProjectDetailPage key="stable" detail={detail} />, '生成 AI 深度解读'],
    ['/project/github/42', <RardarProjectDetailPage key="legacy" detail={detail} historical />, '生成 AI 深度解读'],
    ['/find', <RardarFindProjectPage key="find" initialRunId="another-users-private-run" />, '开始找项目'],
  ])('renders %s anonymously with auth context and without fetching private/operator state', (pathname, page, content) => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    const html = renderPage(pathname as string, page, null);
    expect(html).toContain('data-rardar-shell="true"');
    expect(html).toContain(content);
    expect(html).not.toContain('管理员榜单更新');
    expect(html).not.toContain('管理员登录');
    const adminLink = html.match(/<a\b[^>]*aria-label="打开 TopicEye 管理后台"[^>]*>/u)?.[0] || '';
    expect(adminLink).toContain('href="/admin"');
    expect(html).not.toContain('href="/login');
    expect(html).not.toContain('退出登录');
    expect(html).not.toContain('登录后生成');
    expect(html).not.toContain('登录后开始');
    expect(html).not.toContain('最近需求结果');
    expect(html).not.toContain('保存与运行状态');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it('keeps the Activity placeholder public without introducing a new content source', async () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    const page = await RardarFoundationPage({ pageKey: 'activity' });
    const html = renderPage('/activity', page);
    expect(html).toContain('动态尚未接入');
    expect(html).toContain('目前不采集、不分析、不推送动态');
    expect(fetcher).not.toHaveBeenCalled();
  });

  it.each(['user', 'admin'])('retains the original gear entry and signed-in actions for %s', (role) => {
    const user = { id: 7, role } as AuthUser;
    const html = renderPage('/project/stable/public-saved-project', <RardarProjectDetailPage detail={detail} />, user);
    expect(html).toContain('生成 AI 深度解读');
    expect(html).not.toContain('登录后生成 AI 深度解读');
    expect(html).toContain('打开 TopicEye 管理后台');
    expect(html).not.toContain('退出登录');
  });

  it.each([null, { id: 7, role: 'admin' } as AuthUser])('keeps the public Find form but disables anonymous submission for %j', (user) => {
    const html = renderPage('/find', <RardarFindProjectPage />, user);
    const submit = html.match(/<button\b[^>]*type="submit"[^>]*>[\s\S]*?<\/button>/u)?.[0] || '';
    expect(submit).toContain('开始找项目');
    expect(submit.includes('disabled=""')).toBe(!user);
    expect(html).toContain('你想完成什么？');
    expect(html).not.toContain('href="/login');
  });

  it('reuses only authentication on the Rardar login page and does not open registration', () => {
    const fetcher = vi.fn(); vi.stubGlobal('fetch', fetcher);
    const html = renderPage('/login', <LoginPage />);
    expect(html).toContain('登录后，按需使用 AI 分析');
    expect(html).toContain('返回原页面后不会自动生成');
    expect(html).not.toContain('创建账号');
    expect(html).not.toContain('>注册<');
    expect(html).not.toContain('data-rardar-shell');
    expect(fetcher).not.toHaveBeenCalled();
  });
});
