'use client';

import React, { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, LockKeyhole, Mail, Radar, UserRound } from 'lucide-react';
import { useAppContext } from '@/components/ClientLayout';
import { authApi } from '@/lib/api';
import { Badge, Button, Panel, cx } from '@/components/ui';

type AuthMode = 'login' | 'register';

export default function LoginPage() {
  const router = useRouter();
  const { applyAuthSession, currentUser } = useAppContext();
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    if (!email.trim() || !password) return false;
    if (mode === 'register' && password.length < 8) return false;
    return true;
  }, [email, password, mode]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSubmit || submitting) return;

    setSubmitting(true);
    setError(null);
    try {
      const session = mode === 'login'
        ? await authApi.login({ email: email.trim(), password })
        : await authApi.register({
            email: email.trim(),
            password,
            display_name: displayName.trim() || null,
          });
      applyAuthSession(session);
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : mode === 'login' ? '登录失败' : '注册失败');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 overflow-y-auto bg-page px-6 py-8 lg:px-10">
      <div className="mx-auto grid w-full max-w-[980px] items-center gap-6 lg:grid-cols-[1fr_420px]">
        <div className="min-w-0">
          <div className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-sm bg-primary text-white shadow-sm">
            <Radar size={22} strokeWidth={2.4} />
          </div>
          <h1 className="mb-3 max-w-[560px] text-[30px] font-black leading-tight text-gray-900">
            把选题、收藏和创作流绑定到你的账号
          </h1>
          <p className="max-w-[560px] text-[14px] leading-7 text-gray-500">
            登录后可以稳定保存收藏、信源偏好和后续付费区权限。复盘、创作和个人工作台需要登录，管理入口仅管理员可见。
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            <Badge tone="primary">邮箱登录</Badge>
            <Badge tone="teal">免费版默认开通</Badge>
            <Badge tone="neutral">付费区预留</Badge>
          </div>
        </div>

        <Panel className="p-6 shadow-sm">
          <div className="mb-5 flex rounded-sm border border-gray-200 bg-gray-100 p-0.5">
            {[
              { key: 'login' as const, label: '登录' },
              { key: 'register' as const, label: '注册' },
            ].map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => {
                  setMode(item.key);
                  setError(null);
                }}
                className={cx(
                  'flex-1 rounded-xs px-3 py-2 text-sm font-black transition',
                  mode === item.key ? 'bg-white text-primary shadow-sm' : 'text-gray-500 hover:text-gray-800',
                )}
              >
                {item.label}
              </button>
            ))}
          </div>

          {currentUser && (
            <div className="mb-4 rounded-sm border border-teal-border bg-teal-light px-3 py-2 text-xs font-bold text-teal">
              当前已登录：{currentUser.display_name || currentUser.email}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3.5">
            {mode === 'register' && (
              <label className="block">
                <span className="mb-1.5 block text-xs font-black text-gray-500">昵称</span>
                <div className="flex items-center rounded-sm border border-gray-200 bg-white px-3 focus-within:border-primary-border focus-within:ring-2 focus-within:ring-primary-light">
                  <UserRound size={15} className="shrink-0 text-gray-400" />
                  <input
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    className="h-10 min-w-0 flex-1 bg-transparent px-2 text-sm outline-none"
                    placeholder="创作者昵称"
                    maxLength={100}
                  />
                </div>
              </label>
            )}

            <label className="block">
              <span className="mb-1.5 block text-xs font-black text-gray-500">邮箱</span>
              <div className="flex items-center rounded-sm border border-gray-200 bg-white px-3 focus-within:border-primary-border focus-within:ring-2 focus-within:ring-primary-light">
                <Mail size={15} className="shrink-0 text-gray-400" />
                <input
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="h-10 min-w-0 flex-1 bg-transparent px-2 text-sm outline-none"
                  placeholder="you@example.com"
                  type="email"
                  autoComplete="email"
                  required
                />
              </div>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-black text-gray-500">密码</span>
              <div className="flex items-center rounded-sm border border-gray-200 bg-white px-3 focus-within:border-primary-border focus-within:ring-2 focus-within:ring-primary-light">
                <LockKeyhole size={15} className="shrink-0 text-gray-400" />
                <input
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="h-10 min-w-0 flex-1 bg-transparent px-2 text-sm outline-none"
                  placeholder={mode === 'register' ? '至少 8 位' : '输入密码'}
                  type="password"
                  autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                  required
                />
              </div>
            </label>

            {error && (
              <div className="rounded-sm border border-red-light bg-red-light px-3 py-2 text-xs font-bold text-red">
                {error}
              </div>
            )}

            <Button type="submit" variant="primary" disabled={!canSubmit || submitting} className="w-full">
              {submitting ? '处理中...' : mode === 'login' ? '登录' : '创建账号'}
              <ArrowRight size={14} />
            </Button>
          </form>
        </Panel>
      </div>
    </div>
  );
}
