'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { T } from '@/lib/design-tokens';
import { sourcesApi, settingsApi } from '@/lib/api';
import type { RSSHubInstance } from '@/lib/api';

// ─── Backend Source (snake_case fields) ───

interface BackendSource {
  id: number;
  name: string;
  source_type: string;
  url: string;
  keyword?: string;
  platform?: string;
  category: string;
  weight: number;
  status: string;
  last_sync_at: string | null;
  sync_error: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

// ─── Helpers ───

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return '从未同步';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return '刚刚';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  const months = Math.floor(days / 30);
  return `${months} 个月前`;
}

const weightStars = (w: number) => '●'.repeat(Math.min(w, 5)) + '○'.repeat(Math.max(5 - w, 0));

const typeColors: Record<string, { bg: string; color: string }> = {
  'RSS': { bg: '#EEF2FF', color: '#4F46E5' },
  'RSSHub': { bg: '#F0FDF4', color: '#16A34A' },
  '公众号': { bg: '#FFF1F2', color: '#E11D48' },
  '网站': { bg: '#FEF3C7', color: '#92400E' },
};

// ─── Form State ───

interface FormState {
  name: string;
  source_type: string;
  url: string;
  category: string;
  enabled: boolean;
}

const emptyForm: FormState = {
  name: '',
  source_type: 'RSS',
  url: '',
  category: 'AI',
  enabled: true,
};

const CATEGORIES = ['AI', '商业', '科技', '教育', '自媒体', '生活', '职场', '产品'];
const SOURCE_TYPES = ['RSS', 'RSSHub', '公众号', '网站'];

// ─── Page Component ───

export default function SourcesPage() {
  const [sources, setSources] = useState<BackendSource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingSource, setEditingSource] = useState<BackendSource | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [syncingIds, setSyncingIds] = useState<Set<number>>(new Set());
  const [syncResults, setSyncResults] = useState<Record<number, string>>({});
  const [deletingIds, setDeletingIds] = useState<Set<number>>(new Set());
  const [rsshubInstances, setRsshubInstances] = useState<RSSHubInstance[]>([]);
  const [rsshubLoading, setRsshubLoading] = useState(true);
  const [rsshubSaving, setRsshubSaving] = useState(false);
  const [rsshubError, setRsshubError] = useState<string | null>(null);
  const [newInstanceUrl, setNewInstanceUrl] = useState('');
  const opmlInputRef = useRef<HTMLInputElement>(null);
  const [importingOPML, setImportingOPML] = useState(false);

  // ─── Fetch sources ───
  const fetchSources = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res: any = await sourcesApi.list();
      // Handle both ApiResponse wrapper and direct response
      const data = res?.data !== undefined ? res.data : res;
      const items = data?.items || (Array.isArray(data) ? data : []);
      setSources(items);
    } catch (err: any) {
      setError(err.message || '加载信源列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // ─── Fetch RSSHub instances ───
  const fetchRSSHubInstances = useCallback(async () => {
    try {
      setRsshubLoading(true);
      const data = await settingsApi.getRSSHubInstances();
      setRsshubInstances(data.instances || []);
    } catch (err: any) {
      setRsshubError(err.message || '加载RSSHub实例失败');
    } finally {
      setRsshubLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources();
    fetchRSSHubInstances();
  }, [fetchSources, fetchRSSHubInstances]);

  // ─── Toggle instance enabled ───
  const toggleInstance = async (url: string) => {
    const updated = rsshubInstances.map((i) =>
      i.url === url ? { ...i, enabled: !i.enabled } : i
    );
    setRsshubInstances(updated);
    try {
      setRsshubSaving(true);
      await settingsApi.updateRSSHubInstances(updated);
    } catch (err: any) {
      setRsshubError(err.message || '更新失败');
      setRsshubInstances((prev) => prev.map((i) => i.url === url ? { ...i, enabled: !i.enabled } : i));
    } finally {
      setRsshubSaving(false);
    }
  };

  // ─── Add instance ───
  const addInstance = async () => {
    const url = newInstanceUrl.trim();
    if (!url || !url.startsWith('http')) {
      setRsshubError('请输入以 http/https 开头的有效 URL');
      return;
    }
    if (rsshubInstances.find((i) => i.url === url)) {
      setRsshubError('该实例已存在');
      return;
    }
    const updated = [...rsshubInstances, { url, enabled: true, priority: rsshubInstances.length, note: '' }];
    setRsshubInstances(updated);
    setNewInstanceUrl('');
    try {
      setRsshubSaving(true);
      await settingsApi.updateRSSHubInstances(updated);
    } catch (err: any) {
      setRsshubError(err.message || '添加失败');
      setRsshubInstances((prev) => prev.filter((i) => i.url !== url));
    } finally {
      setRsshubSaving(false);
    }
  };

  // ─── Delete instance ───
  const deleteInstance = async (url: string) => {
    if (!confirm(`删除实例 ${url}？`)) return;
    const prev = rsshubInstances;
    setRsshubInstances((prev) => prev.filter((i) => i.url !== url));
    try {
      setRsshubSaving(true);
      await settingsApi.updateRSSHubInstances(rsshubInstances.filter((i) => i.url !== url));
    } catch (err: any) {
      setRsshubError(err.message || '删除失败');
      setRsshubInstances(prev);
    } finally {
      setRsshubSaving(false);
    }
  };

  // ─── Create source ───
  const handleCreate = async () => {
    if (!form.name.trim()) return;
    try {
      setSubmitting(true);
      await sourcesApi.create({
        name: form.name.trim(),
        source_type: form.source_type,
        url: form.url.trim(),
        category: form.category,
        enabled: form.enabled,
      } as any);
      setShowAddModal(false);
      setForm(emptyForm);
      await fetchSources();
    } catch (err: any) {
      setError(err.message || '添加信源失败');
    } finally {
      setSubmitting(false);
    }
  };

  // ─── Import OPML ───
  const handleOPMLImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImportingOPML(true);
    try {
      const result = await sourcesApi.importOPML(file);
      setRsshubSuccess(result.message);
      fetchSources();
    } catch (err: any) {
      setError(err.message || 'OPML 导入失败');
    } finally {
      setImportingOPML(false);
      if (opmlInputRef.current) opmlInputRef.current.value = '';
    }
  };

  // ─── Update source ───
  const handleUpdate = async () => {
    if (!editingSource || !form.name.trim()) return;
    try {
      setSubmitting(true);
      await sourcesApi.update(editingSource.id, {
        name: form.name.trim(),
        source_type: form.source_type,
        url: form.url.trim(),
        category: form.category,
        enabled: form.enabled,
      } as any);
      setEditingSource(null);
      setForm(emptyForm);
      await fetchSources();
    } catch (err: any) {
      setError(err.message || '更新信源失败');
    } finally {
      setSubmitting(false);
    }
  };

  // ─── Open edit modal ───
  const openEditModal = (src: BackendSource) => {
    setEditingSource(src);
    setForm({
      name: src.name,
      source_type: src.source_type,
      url: src.url,
      category: src.category,
      enabled: src.enabled,
    });
  };

  // ─── Sync source ───
  const handleSync = async (id: number) => {
    try {
      setSyncingIds((prev) => new Set(prev).add(id));
      setSyncResults((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      const res: any = await sourcesApi.sync(id);
      const data = res?.data !== undefined ? res.data : res;
      const fetched = data?.fetched ?? 0;
      const newCount = data?.new ?? 0;
      setSyncResults((prev) => ({
        ...prev,
        [id]: `获取 ${fetched} 条，新增 ${newCount} 条`,
      }));
      await fetchSources();
    } catch (err: any) {
      setSyncResults((prev) => ({
        ...prev,
        [id]: `同步失败: ${err.message}`,
      }));
    } finally {
      setSyncingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  // ─── Delete source ───
  const handleDelete = async (id: number) => {
    if (!confirm('确定要删除此信源吗？')) return;
    try {
      setDeletingIds((prev) => new Set(prev).add(id));
      await sourcesApi.delete(id);
      setSources((prev) => prev.filter((s) => s.id !== id));
    } catch (err: any) {
      setError(err.message || '删除失败');
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  const handleWeightChange = async (id: number, weight: number) => {
    try {
      await sourcesApi.update(id, { weight });
      setSources((prev) => prev.map((s) => (s.id === id ? { ...s, weight } : s)));
    } catch (err: any) {
      setError(err.message || '权重更新失败');
    }
  };

  // ─── Stats ───
  const activeCount = sources.filter((s) => s.status === 'active' && s.enabled).length;

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900, marginBottom: 6 }}>信源管理</h1>
          <p style={{ fontSize: 13, color: T.gray400 }}>
            共 <b style={{ fontFamily: T.mono, color: T.gray600 }}>{sources.length}</b> 个信源 ·
            活跃 <b style={{ fontFamily: T.mono, color: T.teal }}>{activeCount}</b> 个
          </p>
        </div>
        <button
          onClick={() => {
            setForm(emptyForm);
            setShowAddModal(true);
          }}
          style={{
            padding: '8px 20px',
            fontSize: 13,
            fontWeight: 600,
            background: T.primary,
            color: T.white,
            border: 'none',
            borderRadius: T.radiusSm,
            cursor: 'pointer',
          }}
        >
          + 添加信源
        </button>
        <input
          ref={opmlInputRef}
          type="file"
          accept=".opml,.xml"
          style={{ display: 'none' }}
          onChange={handleOPMLImport}
        />
        <button
          onClick={() => opmlInputRef.current?.click()}
          style={{
            padding: '8px 16px',
            background: T.gray100,
            border: `1px solid ${T.gray300}`,
            borderRadius: T.radiusSm,
            cursor: 'pointer',
            fontSize: 13,
            color: T.gray700,
            marginLeft: 8,
          }}
        >
          导入 OPML
        </button>
      </div>

      {/* Error Banner */}
      {rsshubError && (
        <div style={{ padding: '10px 16px', marginBottom: 12, background: T.redLight, color: T.red, borderRadius: T.radiusSm, fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span>{rsshubError}</span>
          <button onClick={() => setRsshubError(null)} style={{ background: 'none', border: 'none', color: T.red, cursor: 'pointer', fontSize: 16, fontWeight: 700, padding: '0 4px' }}>×</button>
        </div>
      )}

      {/* RSSHub Instances Manager */}
      <div style={{ background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray200}`, padding: 20, marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: T.gray800, marginBottom: 2 }}>RSSHub 实例</h2>
            <p style={{ fontSize: 12, color: T.gray400 }}>按优先级顺序尝试，禁用则跳过。添加小红书/微博/B站等路由时使用。</p>
          </div>
          {rsshubSaving && <span style={{ fontSize: 12, color: T.gray400 }}>保存中…</span>}
        </div>

        {/* Instance List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
          {rsshubLoading ? (
            <div style={{ color: T.gray400, fontSize: 13, padding: '8px 0' }}>加载中…</div>
          ) : rsshubInstances.length === 0 ? (
            <div style={{ color: T.gray400, fontSize: 13, padding: '8px 0' }}>暂无实例</div>
          ) : (
            rsshubInstances.map((inst, idx) => (
              <div key={inst.url} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', background: T.gray50, borderRadius: T.radiusSm, border: `1px solid ${T.gray100}` }}>
                <span style={{ fontFamily: T.mono, fontSize: 11, color: T.gray300, minWidth: 16 }}>#{idx + 1}</span>
                <span style={{ fontFamily: T.mono, fontSize: 13, color: inst.enabled ? T.gray800 : T.gray400, flex: 1, wordBreak: 'break-all' }}>{inst.url}</span>
                {inst.note && <span style={{ fontSize: 11, color: T.gray400 }}>{inst.note}</span>}
                <button
                  onClick={() => toggleInstance(inst.url)}
                  disabled={rsshubSaving}
                  style={{ padding: '3px 10px', fontSize: 11, fontWeight: 600, borderRadius: 999, border: 'none', cursor: rsshubSaving ? 'wait' : 'pointer', background: inst.enabled ? '#DCFCE7' : T.gray200, color: inst.enabled ? '#16A34A' : T.gray400 }}>
                  {inst.enabled ? '启用' : '禁用'}
                </button>
                <button
                  onClick={() => deleteInstance(inst.url)}
                  disabled={rsshubSaving}
                  style={{ padding: '3px 8px', fontSize: 11, borderRadius: T.radiusSm, border: 'none', cursor: rsshubSaving ? 'wait' : 'pointer', background: T.redLight, color: T.red }}>
                  删除
                </button>
              </div>
            ))
          )}
        </div>

        {/* Add Instance */}
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={newInstanceUrl}
            onChange={(e) => setNewInstanceUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addInstance()}
            placeholder="https://rsshub.example.com"
            style={{ flex: 1, padding: '7px 12px', fontSize: 13, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, outline: 'none', fontFamily: T.mono }}
          />
          <button
            onClick={addInstance}
            disabled={rsshubSaving || !newInstanceUrl.trim()}
            style={{ padding: '7px 16px', fontSize: 13, fontWeight: 600, background: rsshubSaving || !newInstanceUrl.trim() ? T.gray200 : T.primary, color: T.white, border: 'none', borderRadius: T.radiusSm, cursor: rsshubSaving || !newInstanceUrl.trim() ? 'wait' : 'pointer' }}>
            + 添加实例
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div
          style={{
            padding: '10px 16px',
            marginBottom: 16,
            background: T.redLight,
            color: T.red,
            borderRadius: T.radiusSm,
            fontSize: 13,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            style={{
              background: 'none',
              border: 'none',
              color: T.red,
              cursor: 'pointer',
              fontSize: 16,
              fontWeight: 700,
              lineHeight: 1,
              padding: '0 4px',
            }}
          >
            ×
          </button>
        </div>
      )}

      {/* Loading State */}
      {loading && sources.length === 0 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: 200,
            color: T.gray400,
            fontSize: 14,
            gap: 10,
          }}
        >
          <Spinner />
          <span>加载中…</span>
        </div>
      )}

      {/* Table */}
      {!loading && (
        <div
          style={{
            background: T.white,
            borderRadius: T.radius,
            border: `1px solid ${T.gray100}`,
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '2fr 1fr 1fr 1.2fr 1fr 0.8fr 1.5fr',
              padding: '12px 24px',
              background: T.gray50,
              borderBottom: `1px solid ${T.gray200}`,
              fontSize: 12,
              fontWeight: 600,
              color: T.gray500,
              textTransform: 'uppercase' as const,
              letterSpacing: '0.05em',
            }}
          >
            <span>信源名称</span>
            <span>类型</span>
            <span>分类</span>
            <span>最近同步</span>
            <span>权重</span>
            <span>状态</span>
            <span>操作</span>
          </div>

          {/* Empty State */}
          {sources.length === 0 && (
            <div
              style={{
                padding: '48px 24px',
                textAlign: 'center' as const,
                color: T.gray400,
                fontSize: 14,
              }}
            >
              暂无信源，点击「添加信源」开始
            </div>
          )}

          {/* Rows */}
          {sources.map((src) => (
            <SourceRowComponent
              key={src.id}
              source={src}
              syncing={syncingIds.has(src.id)}
              syncResult={syncResults[src.id] || null}
              deleting={deletingIds.has(src.id)}
              onSync={() => handleSync(src.id)}
              onEdit={() => openEditModal(src)}
              onDelete={() => handleDelete(src.id)}
              onWeightChange={(w) => handleWeightChange(src.id, w)}
            />
          ))}
        </div>
      )}

      {/* Add Source Modal */}
      {showAddModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowAddModal(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 32,
              width: 480,
              maxWidth: '90vw',
              boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
            }}
          >
            <h2 style={{ fontSize: 20, fontWeight: 700, color: T.gray900, marginBottom: 24 }}>添加信源</h2>
            <SourceForm form={form} setForm={setForm} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 28 }}>
              <button
                onClick={() => setShowAddModal(false)}
                disabled={submitting}
                style={{
                  padding: '8px 20px',
                  fontSize: 13,
                  fontWeight: 500,
                  background: T.gray100,
                  color: T.gray600,
                  border: 'none',
                  borderRadius: T.radiusSm,
                  cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={submitting || !form.name.trim()}
                style={{
                  padding: '8px 20px',
                  fontSize: 13,
                  fontWeight: 600,
                  background: submitting || !form.name.trim() ? T.gray300 : T.primary,
                  color: T.white,
                  border: 'none',
                  borderRadius: T.radiusSm,
                  cursor: submitting ? 'wait' : 'pointer',
                }}
              >
                {submitting ? '提交中…' : '添加'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Source Modal */}
      {editingSource && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => { setEditingSource(null); setForm(emptyForm); }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: T.white,
              borderRadius: T.radius,
              padding: 32,
              width: 480,
              maxWidth: '90vw',
              boxShadow: '0 20px 60px rgba(0,0,0,0.15)',
            }}
          >
            <h2 style={{ fontSize: 20, fontWeight: 700, color: T.gray900, marginBottom: 24 }}>编辑信源</h2>
            <SourceForm form={form} setForm={setForm} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 28 }}>
              <button
                onClick={() => { setEditingSource(null); setForm(emptyForm); }}
                disabled={submitting}
                style={{
                  padding: '8px 20px',
                  fontSize: 13,
                  fontWeight: 500,
                  background: T.gray100,
                  color: T.gray600,
                  border: 'none',
                  borderRadius: T.radiusSm,
                  cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={handleUpdate}
                disabled={submitting || !form.name.trim()}
                style={{
                  padding: '8px 20px',
                  fontSize: 13,
                  fontWeight: 600,
                  background: submitting || !form.name.trim() ? T.gray300 : T.primary,
                  color: T.white,
                  border: 'none',
                  borderRadius: T.radiusSm,
                  cursor: submitting ? 'wait' : 'pointer',
                }}
              >
                {submitting ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Source Form (shared between Add & Edit) ───

function SourceForm({ form, setForm }: { form: FormState; setForm: React.Dispatch<React.SetStateAction<FormState>> }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <label style={{ fontSize: 13, fontWeight: 500, color: T.gray700, display: 'block', marginBottom: 6 }}>
          信源名称 <span style={{ color: T.red }}>*</span>
        </label>
        <input
          type="text"
          placeholder="例：量子位"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          style={{ width: '100%', padding: '8px 12px', fontSize: 14, border: `1px solid ${T.gray200}`, borderRadius: T.radiusXs, outline: 'none', fontFamily: T.sans }}
        />
      </div>
      <div>
        <label style={{ fontSize: 13, fontWeight: 500, color: T.gray700, display: 'block', marginBottom: 6 }}>类型</label>
        <select
          value={form.source_type}
          onChange={(e) => setForm((f) => ({ ...f, source_type: e.target.value }))}
          style={{ width: '100%', padding: '8px 12px', fontSize: 14, border: `1px solid ${T.gray200}`, borderRadius: T.radiusXs, outline: 'none', background: T.white, fontFamily: T.sans }}
        >
          {SOURCE_TYPES.map((t) => (<option key={t} value={t}>{t}</option>))}
        </select>
      </div>
      <div>
        <label style={{ fontSize: 13, fontWeight: 500, color: T.gray700, display: 'block', marginBottom: 6 }}>URL / 地址</label>
        <input
          type="text"
          placeholder="https://example.com/feed"
          value={form.url}
          onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
          style={{ width: '100%', padding: '8px 12px', fontSize: 14, border: `1px solid ${T.gray200}`, borderRadius: T.radiusXs, outline: 'none', fontFamily: T.mono }}
        />
      </div>
      <div>
        <label style={{ fontSize: 13, fontWeight: 500, color: T.gray700, display: 'block', marginBottom: 6 }}>分类</label>
        <select
          value={form.category}
          onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
          style={{ width: '100%', padding: '8px 12px', fontSize: 14, border: `1px solid ${T.gray200}`, borderRadius: T.radiusXs, outline: 'none', background: T.white, fontFamily: T.sans }}
        >
          {CATEGORIES.map((c) => (<option key={c} value={c}>{c}</option>))}
        </select>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <input type="checkbox" checked={form.enabled} onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))} style={{ width: 16, height: 16, cursor: 'pointer' }} id="src-enabled" />
        <label htmlFor="src-enabled" style={{ fontSize: 13, fontWeight: 500, color: T.gray700, cursor: 'pointer' }}>启用此信源</label>
      </div>
    </div>
  );
}

// ─── Spinner ───

function Spinner() {
  return (
    <div
      style={{
        width: 18,
        height: 18,
        border: `2px solid ${T.gray200}`,
        borderTopColor: T.primary,
        borderRadius: '50%',
        animation: 'spin 0.6s linear infinite',
      }}
    />
  );
}

// ─── Source Row ───

function SourceRowComponent({
  source,
  syncing,
  syncResult,
  deleting,
  onSync,
  onEdit,
  onDelete,
  onWeightChange,
}: {
  source: BackendSource;
  syncing: boolean;
  syncResult: string | null;
  deleting: boolean;
  onSync: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onWeightChange?: (w: number) => void;
}) {
  const [hovered, setHovered] = useState(false);
  const tc = typeColors[source.source_type] || { bg: T.gray100, color: T.gray600 };
  const isActive = source.status === 'active' && source.enabled;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr 1fr 1.2fr 1fr 0.8fr 1.5fr',
        padding: '14px 24px',
        borderBottom: `1px solid ${T.gray100}`,
        fontSize: 13,
        color: T.gray700,
        alignItems: 'center',
        transition: 'background 0.1s',
        cursor: 'default',
        background: hovered ? T.gray50 : T.white,
        opacity: deleting ? 0.5 : 1,
      }}
    >
      {/* Name */}
      <div>
        <span style={{ fontWeight: 500 }}>{source.name}</span>
        {source.url && (
          <div
            style={{
              fontSize: 11,
              color: T.gray400,
              marginTop: 2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              maxWidth: 220,
            }}
          >
            {source.url}
          </div>
        )}
      </div>

      {/* Type */}
      <span
        style={{
          fontSize: 11,
          fontWeight: 500,
          padding: '2px 8px',
          borderRadius: 4,
          background: tc.bg,
          color: tc.color,
          display: 'inline-block',
          width: 'fit-content',
        }}
      >
        {source.source_type}
      </span>

      {/* Category */}
      <span style={{ color: T.gray500 }}>{source.category}</span>

      {/* Last Sync */}
      <div>
        <span style={{ fontSize: 12, color: source.sync_error ? T.red : T.gray400 }}>
          {source.sync_error ? '同步失败' : timeAgo(source.last_sync_at)}
        </span>
        {source.sync_error && (
          <div style={{ fontSize: 11, color: T.red, marginTop: 1 }}>{source.sync_error}</div>
        )}
        {syncResult && (
          <div style={{ fontSize: 11, color: T.teal, marginTop: 1 }}>{syncResult}</div>
        )}
      </div>

      {/* Weight — clickable to adjust */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }}
        title={`权重 ${source.weight}/5 — 影响精选加分：${source.weight > 3 ? '+' : ''}${(source.weight - 3) * 8} 分`}
      >
        {[1, 2, 3, 4, 5].map((w) => (
          <span
            key={w}
            onClick={() => onWeightChange?.(w)}
            style={{
              fontSize: 11,
              color: w <= source.weight ? T.primary : T.gray200,
              transition: 'color 0.15s',
              userSelect: 'none',
            }}
          >
            ●
          </span>
        ))}
        <span style={{ fontSize: 10, color: T.gray400, marginLeft: 4 }}>
          {(source.weight - 3) * 8 > 0 ? '+' : ''}{(source.weight - 3) * 8}
        </span>
      </div>

      {/* Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: isActive ? T.teal : T.red,
            display: 'inline-block',
          }}
        />
        <span style={{ fontSize: 11, color: isActive ? T.teal : T.red }}>
          {source.enabled ? (source.status === 'active' ? '正常' : source.status) : '已禁用'}
        </span>
      </div>

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button
          onClick={onSync}
          disabled={syncing}
          style={{
            padding: '4px 10px',
            fontSize: 11,
            fontWeight: 500,
            background: syncing ? T.gray100 : T.tealLight,
            color: syncing ? T.gray400 : T.teal,
            border: `1px solid ${syncing ? T.gray200 : T.tealBorder}`,
            borderRadius: 4,
            cursor: syncing ? 'wait' : 'pointer',
            transition: 'all 0.15s',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          {syncing ? <Spinner /> : null}
          {syncing ? '同步中' : '同步'}
        </button>
        <button
          onClick={onEdit}
          style={{
            padding: '4px 10px',
            fontSize: 11,
            fontWeight: 500,
            background: '#EEF2FF',
            color: '#4F46E5',
            border: '1px solid #C7D2FE',
            borderRadius: 4,
            cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          编辑
        </button>
        <button
          onClick={onDelete}
          disabled={deleting}
          style={{
            padding: '4px 10px',
            fontSize: 11,
            fontWeight: 500,
            background: 'transparent',
            color: deleting ? T.gray300 : T.red,
            border: 'none',
            borderRadius: 4,
            cursor: deleting ? 'wait' : 'pointer',
            transition: 'color 0.15s',
          }}
        >
          {deleting ? '删除中…' : '删除'}
        </button>
      </div>
    </div>
  );
}
