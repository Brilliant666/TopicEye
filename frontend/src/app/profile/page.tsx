'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Copy,
  ExternalLink,
  KeyRound,
  Loader2,
  PlugZap,
  RefreshCw,
  ShieldCheck,
  TerminalSquare,
  Trash2,
  UserRound,
} from 'lucide-react';
import { useAppContext } from '@/components/ClientLayout';
import { Badge, Button, Panel, cx } from '@/components/ui';
import { integrationsApi } from '@/lib/api';
import type { IntegrationStatus, WeReadSyncResult } from '@/types';

const DEFAULT_INSTALL_COMMAND = 'npx skills add Tencent/WeChatReading -g';
const INSTALL_SCRIPT_COMMAND = 'npm run skills:install-weread';

function formatTime(value?: string | null) {
  if (!value) return '尚未同步';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function CopyCommandButton({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-gray-200 bg-white text-gray-500 transition hover:border-primary-border hover:text-primary"
      title={copied ? '已复制' : '复制命令'}
    >
      {copied ? <CheckCircle2 size={15} /> : <Copy size={15} />}
    </button>
  );
}

function CommandRow({ label, command }: { label: string; command: string }) {
  return (
    <div className="grid gap-2 rounded-sm border border-gray-200 bg-gray-50 p-3 sm:grid-cols-[116px_1fr_auto] sm:items-center">
      <div className="text-xs font-black text-gray-500">{label}</div>
      <code className="min-w-0 overflow-x-auto whitespace-nowrap rounded-xs bg-white px-2.5 py-2 font-mono text-xs font-bold text-gray-800">
        {command}
      </code>
      <CopyCommandButton command={command} />
    </div>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const { currentUser, authLoading, refreshCounts } = useAppContext();
  const [status, setStatus] = useState<IntegrationStatus | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<WeReadSyncResult | null>(null);

  const installCommand = status?.install_command || DEFAULT_INSTALL_COMMAND;
  const docsUrl = status?.docs_url || 'https://weread.qq.com/r/weread-skills';
  const canSave = apiKey.trim().length >= 8 && !saving;
  const canSync = Boolean(status?.configured && status.sync_endpoint_configured) && !syncing;

  const readiness = useMemo(() => {
    if (!status?.configured) {
      return { label: '未配置', tone: 'amber' as const, text: '先保存微信读书 API Key。' };
    }
    if (!status.sync_endpoint_configured) {
      return { label: '待接入', tone: 'amber' as const, text: 'API Key 已保存，后端还未配置 WEREAD_SKILL_API_URL。' };
    }
    return { label: '可同步', tone: 'teal' as const, text: 'Key 与同步 endpoint 均已配置。' };
  }, [status]);

  const loadStatus = async () => {
    if (!currentUser) {
      setLoadingStatus(false);
      return;
    }
    setLoadingStatus(true);
    setError(null);
    try {
      setStatus(await integrationsApi.getWeRead());
    } catch (err) {
      setError(err instanceof Error ? err.message : '读取微信读书配置失败');
    } finally {
      setLoadingStatus(false);
    }
  };

  useEffect(() => {
    void loadStatus();
  }, [currentUser?.id]);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError(null);
    setNotice(null);
    setSyncResult(null);
    try {
      const next = await integrationsApi.updateWeRead({ api_key: apiKey.trim() });
      setStatus(next);
      setApiKey('');
      setNotice('微信读书 API Key 已保存。');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (clearing) return;
    setClearing(true);
    setError(null);
    setNotice(null);
    setSyncResult(null);
    try {
      setStatus(await integrationsApi.clearWeRead());
      setApiKey('');
      setNotice('微信读书 API Key 已清除。');
    } catch (err) {
      setError(err instanceof Error ? err.message : '清除失败');
    } finally {
      setClearing(false);
    }
  };

  const handleSync = async () => {
    if (!canSync) return;
    setSyncing(true);
    setError(null);
    setNotice(null);
    setSyncResult(null);
    try {
      const result = await integrationsApi.syncWeRead(50);
      setSyncResult(result);
      setNotice(result.message);
      refreshCounts();
      await loadStatus();
    } catch (err) {
      const message = err instanceof Error ? err.message : '同步失败';
      setError(message);
      await loadStatus();
    } finally {
      setSyncing(false);
    }
  };

  if (authLoading) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center bg-page">
        <div className="inline-flex items-center gap-2 text-sm font-bold text-gray-500">
          <Loader2 size={16} className="animate-spin" />
          正在检查登录状态
        </div>
      </div>
    );
  }

  if (!currentUser) {
    return (
      <div className="flex h-full min-h-0 overflow-y-auto bg-page px-6 py-8 lg:px-10">
        <Panel className="mx-auto flex w-full max-w-[620px] flex-col items-start justify-center p-7">
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-sm bg-primary-light text-primary">
            <UserRound size={22} />
          </div>
          <h1 className="mb-2 text-2xl font-black text-gray-900">需要登录后配置个人集成</h1>
          <p className="mb-5 text-sm leading-7 text-gray-500">
            微信读书 API Key 属于个人凭据，只会绑定到你的账号，不会显示给其他用户。
          </p>
          <Button type="button" variant="primary" onClick={() => router.push('/login')}>
            去登录
            <ArrowRight size={14} />
          </Button>
        </Panel>
      </div>
    );
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto bg-page px-4 py-5 sm:px-6 lg:px-10">
      <div className="mx-auto w-full max-w-[1120px] space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Badge tone={currentUser.plan === 'free' ? 'neutral' : 'primary'}>
                {currentUser.plan === 'free' ? '免费版' : '付费版'}
              </Badge>
              <Badge tone={readiness.tone}>{readiness.label}</Badge>
            </div>
            <h1 className="text-[26px] font-black leading-tight text-gray-900">个人中心</h1>
            <p className="mt-2 max-w-[720px] text-sm leading-7 text-gray-500">
              管理账号、外部素材接入和同步状态。微信读书素材会进入内容流，后续可参与选题、收藏和创作方案生成。
            </p>
          </div>
          <Button type="button" onClick={loadStatus} disabled={loadingStatus} className="shrink-0">
            {loadingStatus ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            刷新状态
          </Button>
        </div>

        <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
          <Panel className="p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <div className="text-xs font-black text-gray-500">当前账号</div>
                <div className="mt-1 truncate text-base font-black text-gray-900">
                  {currentUser.display_name || currentUser.email}
                </div>
              </div>
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-sm bg-teal-light text-teal">
                <ShieldCheck size={20} />
              </div>
            </div>
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="text-gray-500">邮箱</span>
                <span className="min-w-0 truncate font-bold text-gray-800">{currentUser.email}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-gray-500">套餐</span>
                <span className="font-bold text-gray-800">{currentUser.plan === 'free' ? '免费版' : currentUser.plan}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span className="text-gray-500">创建时间</span>
                <span className="font-bold text-gray-800">{formatTime(currentUser.created_at)}</span>
              </div>
            </div>
          </Panel>

          <Panel className="p-5">
            <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <BookOpen size={18} className="text-primary" />
                  <h2 className="text-lg font-black text-gray-900">微信读书素材</h2>
                </div>
                <p className="text-sm leading-6 text-gray-500">{readiness.text}</p>
              </div>
              <Badge tone={status?.configured ? 'teal' : 'neutral'}>
                {status?.api_key_hint ? `Key ${status.api_key_hint}` : '未保存 Key'}
              </Badge>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-sm border border-gray-200 bg-gray-50 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-black text-gray-500">
                  <KeyRound size={14} />
                  API Key
                </div>
                <div className={cx('text-sm font-black', status?.configured ? 'text-teal' : 'text-gray-700')}>
                  {status?.configured ? '已保存' : '未配置'}
                </div>
              </div>
              <div className="rounded-sm border border-gray-200 bg-gray-50 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-black text-gray-500">
                  <PlugZap size={14} />
                  同步 Endpoint
                </div>
                <div className={cx('text-sm font-black', status?.sync_endpoint_configured ? 'text-teal' : 'text-amber')}>
                  {status?.sync_endpoint_configured ? '已配置' : '未配置'}
                </div>
              </div>
              <div className="rounded-sm border border-gray-200 bg-gray-50 p-3">
                <div className="mb-2 flex items-center gap-2 text-xs font-black text-gray-500">
                  <RefreshCw size={14} />
                  最近同步
                </div>
                <div className="truncate text-sm font-black text-gray-800">{formatTime(status?.last_sync_at)}</div>
              </div>
            </div>

            <form onSubmit={handleSave} className="mt-5 grid gap-3 md:grid-cols-[1fr_auto_auto]">
              <label className="block">
                <span className="mb-1.5 block text-xs font-black text-gray-500">微信读书 API Key</span>
                <input
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  className="h-10 w-full rounded-sm border border-gray-200 bg-white px-3 text-sm outline-none transition focus:border-primary-border focus:ring-2 focus:ring-primary-light"
                  placeholder={status?.configured ? '输入新 Key 后可覆盖当前配置' : '粘贴微信读书 API Key'}
                  type="password"
                  autoComplete="off"
                />
              </label>
              <div className="flex items-end">
                <Button type="submit" variant="primary" disabled={!canSave} className="w-full md:w-auto">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
                  保存 Key
                </Button>
              </div>
              <div className="flex items-end">
                <Button
                  type="button"
                  variant="danger"
                  onClick={handleClear}
                  disabled={clearing || !status?.configured}
                  className="w-full md:w-auto"
                >
                  {clearing ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                  清除
                </Button>
              </div>
            </form>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button type="button" variant="success" onClick={handleSync} disabled={!canSync}>
                {syncing ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
                {status?.configured && !status.sync_endpoint_configured ? '等待同步服务' : '同步 50 条素材'}
              </Button>
              {docsUrl && (
                <a
                  href={docsUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex min-h-9 items-center justify-center gap-1.5 rounded-sm border border-gray-200 bg-white px-3 py-2 text-xs font-bold text-gray-700 transition hover:border-primary-border hover:text-primary"
                >
                  官方文档
                  <ExternalLink size={14} />
                </a>
              )}
            </div>

            {(notice || error || syncResult || status?.last_sync_error) && (
              <div className="mt-4 space-y-2">
                {notice && (
                  <div className="rounded-sm border border-teal-border bg-teal-light px-3 py-2 text-xs font-bold text-teal">
                    {notice}
                  </div>
                )}
                {error && (
                  <div className="rounded-sm border border-amber-border bg-amber-light px-3 py-2 text-xs font-bold text-amber">
                    {error}
                  </div>
                )}
                {syncResult && (
                  <div className="grid gap-2 text-xs sm:grid-cols-3">
                    <div className="rounded-sm bg-gray-50 px-3 py-2 font-bold text-gray-600">拉取 {syncResult.fetched}</div>
                    <div className="rounded-sm bg-gray-50 px-3 py-2 font-bold text-gray-600">新增 {syncResult.new}</div>
                    <div className="rounded-sm bg-gray-50 px-3 py-2 font-bold text-gray-600">重复 {syncResult.duplicates}</div>
                  </div>
                )}
                {!error && status?.last_sync_error && (
                  <div className="rounded-sm border border-red-light bg-red-light px-3 py-2 text-xs font-bold text-red">
                    上次同步错误：{status.last_sync_error}
                  </div>
                )}
              </div>
            )}
          </Panel>
        </div>

        <Panel className="p-5">
          <div className="mb-4 flex items-center gap-2">
            <TerminalSquare size={18} className="text-primary" />
            <h2 className="text-lg font-black text-gray-900">Skill 安装</h2>
          </div>
          <p className="mb-4 max-w-[820px] text-sm leading-7 text-gray-500">
            官方 Skill 需要用户在本机安装并获取 API Key。服务启动阶段不会自动执行全局安装，避免网络依赖和全局写入影响后端稳定性。
          </p>
          <div className="space-y-3">
            <CommandRow label="官方命令" command={installCommand} />
            <CommandRow label="前端脚本" command={INSTALL_SCRIPT_COMMAND} />
          </div>
          <div className="mt-4 rounded-sm border border-gray-200 bg-gray-50 px-3 py-2 text-xs leading-6 text-gray-500">
            后端同步入口通过环境变量 <span className="font-mono font-bold text-gray-700">WEREAD_SKILL_API_URL</span> 配置；
            未配置时可以保存 Key，但同步按钮会返回明确错误。
          </div>
        </Panel>
      </div>
    </div>
  );
}
