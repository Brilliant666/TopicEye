'use client';

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { List, Network, Plus, Upload } from 'lucide-react';
import { T } from '@/lib/design-tokens';
import { sourcesApi, settingsApi } from '@/lib/api';
import type { RSSHubInstance, CreateSourceRequest } from '@/lib/api';
import { timeAgo } from '@/lib/utils';
import SourceForm, { FormState, emptyForm } from '@/components/SourceForm';
import SourceRowComponent, { type BackendSource } from '@/components/SourceRow';
import { Spinner } from '@/components/SourceRow';

// ─── Page Component ───

type SourceTierKey = 'core' | 'stable' | 'watch' | 'attention';

const sourceTierMeta: Record<SourceTierKey, { label: string; desc: string; color: string; bg: string }> = {
  core: { label: '核心信源', desc: '高权重、正常采集，影响精选排序', color: T.primary, bg: T.primaryLight },
  stable: { label: '稳定信源', desc: '常规权重，作为日常覆盖面', color: T.teal, bg: T.tealLight },
  watch: { label: '观察池', desc: '低权重或新来源，先保留信号', color: T.amber, bg: T.amberLight },
  attention: { label: '待处理', desc: '禁用、报错或同步异常', color: T.red, bg: T.redLight },
};

function getSourceTier(source: BackendSource): SourceTierKey {
  if (!source.enabled || source.status === 'error' || source.sync_error) return 'attention';
  if ((source.weight ?? 3) >= 4) return 'core';
  if ((source.weight ?? 3) <= 2) return 'watch';
  return 'stable';
}

function sourceTypeLabel(type: string): string {
  const map: Record<string, string> = {
    rss: 'RSS',
    rsshub: 'RSSHub',
    twitter_rss: 'Twitter RSS',
    hackernews: 'HackerNews',
    zhihu: '知乎',
  };
  return map[type] || type;
}

function SourceMapView({
  sourceMap,
  syncingIds,
  onEdit,
  onSync,
}: {
  sourceMap: {
    tiers: Record<SourceTierKey, BackendSource[]>;
    categories: [string, number][];
    types: [string, number][];
    attentionCount: number;
    coreCount: number;
  };
  syncingIds: Set<number>;
  onEdit: (source: BackendSource) => void;
  onSync: (id: number) => void;
}) {
  const tierKeys: SourceTierKey[] = ['core', 'stable', 'watch', 'attention'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 16 }}>
        <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
            <Network size={18} color={T.primary} strokeWidth={2} />
            <h2 style={{ fontSize: 15, color: T.gray800, margin: 0 }}>等级分布</h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(92px, 1fr))', gap: 10 }}>
            {tierKeys.map((key) => {
              const meta = sourceTierMeta[key];
              return (
                <div key={key} style={{ border: `1px solid ${T.gray100}`, borderRadius: T.radiusSm, padding: 12, background: meta.bg }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: meta.color, marginBottom: 6 }}>{meta.label}</div>
                  <div style={{ fontSize: 24, fontFamily: T.mono, color: T.gray900, lineHeight: 1 }}>{sourceMap.tiers[key].length}</div>
                  <div style={{ fontSize: 11, color: T.gray500, marginTop: 6, lineHeight: 1.45 }}>{meta.desc}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ background: T.white, border: `1px solid ${T.gray200}`, borderRadius: T.radius, padding: 18 }}>
          <h2 style={{ fontSize: 15, color: T.gray800, margin: '0 0 14px' }}>分类与类型</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 14 }}>
            {sourceMap.categories.map(([name, count]) => (
              <span key={name} style={{ padding: '5px 9px', borderRadius: 999, background: T.gray50, border: `1px solid ${T.gray200}`, color: T.gray600, fontSize: 12 }}>
                {name} <b style={{ fontFamily: T.mono, color: T.gray900 }}>{count}</b>
              </span>
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {sourceMap.types.map(([name, count]) => (
              <span key={name} style={{ padding: '5px 9px', borderRadius: 999, background: T.tealLight, color: T.teal, fontSize: 12, fontWeight: 600 }}>
                {name} · {count}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        {tierKeys.map((key) => {
          const meta = sourceTierMeta[key];
          return (
            <section key={key} style={{ minWidth: 0, display: 'flex', flexDirection: 'column', maxHeight: 'min(620px, calc(100vh - 360px))' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 8,
                padding: '0 2px',
                flexShrink: 0,
              }}>
                <h3 style={{ fontSize: 13, fontWeight: 700, color: meta.color, margin: 0 }}>{meta.label}</h3>
                <span style={{ fontSize: 11, fontFamily: T.mono, color: T.gray400 }}>{sourceMap.tiers[key].length} 条</span>
              </div>
              <div
                className="source-map-column-scroll"
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  overflowY: 'auto',
                  minHeight: 180,
                  paddingRight: 4,
                  overscrollBehavior: 'contain',
                }}
              >
                {sourceMap.tiers[key].map((source) => (
                  <div key={source.id} style={{ background: T.white, border: `1px solid ${source.sync_error ? T.redLight : T.gray200}`, borderRadius: T.radiusSm, padding: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 13, fontWeight: 700, color: T.gray800, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{source.name}</div>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                          <span style={{ fontSize: 10, color: T.gray500, background: T.gray100, padding: '2px 6px', borderRadius: 4 }}>{sourceTypeLabel(source.source_type)}</span>
                          <span style={{ fontSize: 10, color: T.gray500, background: T.gray100, padding: '2px 6px', borderRadius: 4 }}>{source.category || '未分类'}</span>
                          <span style={{ fontSize: 10, color: T.primary, background: T.primaryLight, padding: '2px 6px', borderRadius: 4 }}>权重 {source.weight ?? 3}</span>
                        </div>
                      </div>
                      <span style={{ width: 8, height: 8, marginTop: 5, borderRadius: '50%', background: getSourceTier(source) === 'attention' ? T.red : T.teal, flexShrink: 0 }} />
                    </div>
                    <div style={{ fontSize: 11, color: source.sync_error ? T.red : T.gray400, marginTop: 8, lineHeight: 1.45 }}>
                      {source.sync_error ? source.sync_error : `最近同步 ${timeAgo(source.last_sync_at)}`}
                    </div>
                    <div style={{ display: 'flex', gap: 6, marginTop: 10 }}>
                      <button onClick={() => onSync(source.id)} disabled={syncingIds.has(source.id)} style={{ flex: 1, padding: '5px 8px', fontSize: 11, border: `1px solid ${T.tealBorder}`, background: T.tealLight, color: T.teal, borderRadius: T.radiusXs, cursor: syncingIds.has(source.id) ? 'wait' : 'pointer' }}>
                        {syncingIds.has(source.id) ? '同步中' : '同步'}
                      </button>
                      <button onClick={() => onEdit(source)} style={{ flex: 1, padding: '5px 8px', fontSize: 11, border: `1px solid ${T.gray200}`, background: T.white, color: T.gray600, borderRadius: T.radiusXs, cursor: 'pointer' }}>
                        编辑
                      </button>
                    </div>
                  </div>
                ))}
                {sourceMap.tiers[key].length === 0 && (
                  <div style={{ padding: 16, textAlign: 'center', color: T.gray400, fontSize: 12, background: T.gray50, borderRadius: T.radiusSm, border: `1px dashed ${T.gray200}` }}>暂无信源</div>
                )}
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

export default function SourcesPage() {
  const [sources, setSources] = useState<BackendSource[]>([]);
  const [mapSources, setMapSources] = useState<BackendSource[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [viewMode, setViewMode] = useState<'map' | 'list'>('map');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [filterType, setFilterType] = useState('');
  const [filterEnabled, setFilterEnabled] = useState<boolean | undefined>(undefined);
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
  const [, setImportingOPML] = useState(false);

  // ─── Fetch sources ───
  const fetchSources = useCallback(async (p: number = 1) => {
    try {
      setLoading(true);
      setError(null);
      const res = await sourcesApi.list({
        page: p,
        page_size: pageSize,
        source_type: filterType || undefined,
        enabled: filterEnabled,
        keyword: searchKeyword || undefined,
      });
      const items = res?.items || [];
      setSources(items as BackendSource[]);
      setTotal(res?.total ?? 0);
      setPage(p);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载信源列表失败');
    } finally {
      setLoading(false);
    }
  }, [pageSize, filterType, filterEnabled, searchKeyword]);

  const fetchSourceMap = useCallback(async () => {
    try {
      const pageSizeForMap = 100;
      const firstPage = await sourcesApi.list({
        page: 1,
        page_size: pageSizeForMap,
        source_type: filterType || undefined,
        enabled: filterEnabled,
        keyword: searchKeyword || undefined,
      });
      const allItems = [...((firstPage?.items || []) as BackendSource[])];
      const totalItems = firstPage?.total ?? allItems.length;
      const totalPages = Math.ceil(totalItems / pageSizeForMap);

      if (totalPages > 1) {
        const rest = await Promise.all(
          Array.from({ length: totalPages - 1 }, (_, idx) =>
            sourcesApi.list({
              page: idx + 2,
              page_size: pageSizeForMap,
              source_type: filterType || undefined,
              enabled: filterEnabled,
              keyword: searchKeyword || undefined,
            })
          )
        );
        rest.forEach((res) => allItems.push(...((res?.items || []) as BackendSource[])));
      }

      setMapSources(allItems);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载信源地图失败');
    }
  }, [filterType, filterEnabled, searchKeyword]);

  // ─── Fetch RSSHub instances ───
  const fetchRSSHubInstances = useCallback(async () => {
    try {
      setRsshubLoading(true);
      const data = await settingsApi.getRSSHubInstances();
      setRsshubInstances(data.instances || []);
    } catch (err: unknown) {
      setRsshubError(err instanceof Error ? err.message : '加载RSSHub实例失败');
    } finally {
      setRsshubLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSources(1);
    fetchSourceMap();
    fetchRSSHubInstances();
  }, [fetchSources, fetchSourceMap, fetchRSSHubInstances]);

  // ─── Toggle instance enabled ───
  const toggleInstance = async (url: string) => {
    const updated = rsshubInstances.map((i) =>
      i.url === url ? { ...i, enabled: !i.enabled } : i
    );
    setRsshubInstances(updated);
    try {
      setRsshubSaving(true);
      await settingsApi.updateRSSHubInstances(updated);
    } catch (err: unknown) {
      setRsshubError(err instanceof Error ? err.message : '更新失败');
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
    } catch (err: unknown) {
      setRsshubError(err instanceof Error ? err.message : '添加失败');
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
    } catch (err: unknown) {
      setRsshubError(err instanceof Error ? err.message : '删除失败');
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
        weight: form.weight,
        enabled: form.enabled,
      } as CreateSourceRequest);
      setShowAddModal(false);
      setForm(emptyForm);
      await fetchSources();
      await fetchSourceMap();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '添加信源失败');
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
      // Show success as a temporary rsshubError display (reuses existing banner)
      setRsshubError(result.message);
      fetchSources();
      fetchSourceMap();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'OPML 导入失败');
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
        weight: form.weight,
        enabled: form.enabled,
      } as CreateSourceRequest);
      setEditingSource(null);
      setForm(emptyForm);
      await fetchSources();
      await fetchSourceMap();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '更新信源失败');
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
      weight: src.weight ?? 3,
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
      const res = await sourcesApi.sync(id);
      const fetched = res?.fetched ?? 0;
      const newCount = res?.new ?? 0;
      setSyncResults((prev) => ({
        ...prev,
        [id]: `获取 ${fetched} 条，新增 ${newCount} 条`,
      }));
      await fetchSources();
      await fetchSourceMap();
    } catch (err: unknown) {
      setSyncResults((prev) => ({
        ...prev,
        [id]: `同步失败: ${err instanceof Error ? err.message : String(err)}`,
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
      setMapSources((prev) => prev.filter((s) => s.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '删除失败');
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
      setMapSources((prev) => prev.map((s) => (s.id === id ? { ...s, weight } : s)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '权重更新失败');
    }
  };

  const handleIntervalChange = async (id: number, fetch_interval_minutes: number) => {
    try {
      await sourcesApi.update(id, { fetch_interval_minutes });
      setSources((prev) => prev.map((s) => (s.id === id ? { ...s, fetch_interval_minutes } : s)));
      setMapSources((prev) => prev.map((s) => (s.id === id ? { ...s, fetch_interval_minutes } : s)));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '采集频率更新失败');
    }
  };

  // ─── Stats ───
  const activeCount = sources.filter((s) => s.status === 'active' && s.enabled).length;
  const sourceMap = useMemo(() => {
    const tiers: Record<SourceTierKey, BackendSource[]> = {
      core: [],
      stable: [],
      watch: [],
      attention: [],
    };
    const categoryCount = new Map<string, number>();
    const typeCount = new Map<string, number>();

    mapSources.forEach((source) => {
      tiers[getSourceTier(source)].push(source);
      categoryCount.set(source.category || '未分类', (categoryCount.get(source.category || '未分类') || 0) + 1);
      typeCount.set(sourceTypeLabel(source.source_type), (typeCount.get(sourceTypeLabel(source.source_type)) || 0) + 1);
    });

    const sortEntries = (entries: [string, number][]) => entries.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    Object.values(tiers).forEach((items) => {
      items.sort((a, b) => {
        const weightDiff = (b.weight ?? 3) - (a.weight ?? 3);
        if (weightDiff !== 0) return weightDiff;
        return a.name.localeCompare(b.name);
      });
    });

    return {
      tiers,
      categories: sortEntries([...categoryCount.entries()]),
      types: sortEntries([...typeCount.entries()]),
      attentionCount: tiers.attention.length,
      coreCount: tiers.core.length,
    };
  }, [mapSources]);

  return (
    <div className="fade-in" style={{ padding: '32px 40px', height: '100%', overflowY: 'auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28, gap: 16, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 26, fontWeight: 700, color: T.gray900, marginBottom: 6 }}>信源管理</h1>
          <p style={{ fontSize: 13, color: T.gray400 }}>
            共 <b style={{ fontFamily: T.mono, color: T.gray600 }}>{total}</b> 个信源 ·
            活跃 <b style={{ fontFamily: T.mono, color: T.teal }}>{activeCount}</b> 个
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            onClick={() => {
              setForm(emptyForm);
              setShowAddModal(true);
            }}
            style={{
              padding: '8px 16px', fontSize: 13, fontWeight: 600,
              background: T.primary, color: T.white, border: 'none',
              borderRadius: T.radiusSm, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
            }}
          >
            <Plus size={15} strokeWidth={2.2} />
            添加信源
          </button>
          <button
            onClick={() => opmlInputRef.current?.click()}
            style={{
              padding: '8px 14px', background: T.gray100,
              border: `1px solid ${T.gray300}`, borderRadius: T.radiusSm,
              cursor: 'pointer', fontSize: 13, color: T.gray700,
              display: 'flex', alignItems: 'center', gap: 6, whiteSpace: 'nowrap',
            }}
          >
            <Upload size={15} strokeWidth={2} />
            导入 OPML
          </button>
        </div>
        <input ref={opmlInputRef} type="file" accept=".opml,.xml" style={{ display: 'none' }} onChange={handleOPMLImport} />
      </div>

      {/* Search & Filter Bar */}
      <div style={{
        display: 'flex', gap: 10, alignItems: 'center',
        marginBottom: 16, flexWrap: 'wrap' as const,
      }}>
        <input
          type="text"
          placeholder="搜索信源名称..."
          value={searchKeyword}
          onChange={(e) => setSearchKeyword(e.target.value)}
          style={{
            padding: '7px 14px', fontSize: 13, width: 220,
            border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
            outline: 'none',
          }}
        />
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          style={{
            padding: '7px 12px', fontSize: 13,
            border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
            background: T.white, cursor: 'pointer',
          }}
        >
          <option value="">全部类型</option>
          <option value="rss">RSS</option>
          <option value="rsshub">RSSHub</option>
          <option value="twitter_rss">Twitter RSS</option>
          <option value="reddit">Reddit</option>
          <option value="zhihu">知乎</option>
          <option value="hackernews">HackerNews</option>
        </select>
        <select
          value={filterEnabled === undefined ? '' : filterEnabled ? 'yes' : 'no'}
          onChange={(e) => setFilterEnabled(e.target.value === '' ? undefined : e.target.value === 'yes')}
          style={{
            padding: '7px 12px', fontSize: 13,
            border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
            background: T.white, cursor: 'pointer',
          }}
        >
          <option value="">全部状态</option>
          <option value="yes">已启用</option>
          <option value="no">已禁用</option>
        </select>
        {(searchKeyword || filterType || filterEnabled !== undefined) && (
          <button
            onClick={() => { setSearchKeyword(''); setFilterType(''); setFilterEnabled(undefined); }}
            style={{
              padding: '6px 12px', fontSize: 12, color: T.gray500,
              background: 'transparent', border: `1px solid ${T.gray200}`,
              borderRadius: T.radiusSm, cursor: 'pointer',
            }}
          >
            清除筛选
          </button>
        )}
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 10, flexWrap: 'wrap' }}>
        <div style={{ display: 'inline-flex', padding: 3, background: T.gray100, borderRadius: T.radiusSm, border: `1px solid ${T.gray200}` }}>
          {[
            { key: 'map' as const, label: '信源地图', icon: Network },
            { key: 'list' as const, label: '列表管理', icon: List },
          ].map((item) => {
            const Icon = item.icon;
            const active = viewMode === item.key;
            return (
              <button
                key={item.key}
                onClick={() => setViewMode(item.key)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  padding: '6px 12px', border: 'none', borderRadius: T.radiusXs,
                  background: active ? T.white : 'transparent',
                  color: active ? T.primary : T.gray500,
                  fontSize: 13, fontWeight: active ? 700 : 500,
                  cursor: 'pointer',
                  boxShadow: active ? '0 1px 2px rgba(15, 23, 42, 0.08)' : 'none',
                }}
              >
                <Icon size={15} strokeWidth={2} />
                {item.label}
              </button>
            );
          })}
        </div>
        <span style={{ fontSize: 12, color: T.gray400 }}>
          地图统计全部 {mapSources.length} 个匹配信源
        </span>
      </div>

      {/* Error Banner */}
      {rsshubError && (
        <div style={{ padding: '10px 16px', marginBottom: 16, background: T.redLight, color: T.red, borderRadius: T.radiusSm, fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{rsshubError}</span>
          <button onClick={() => setRsshubError(null)} style={{ background: 'none', border: 'none', color: T.red, cursor: 'pointer', fontSize: 16, fontWeight: 700, padding: '0 4px' }}>×</button>
        </div>
      )}

      {error && (
        <div style={{ padding: '10px 16px', marginBottom: 16, background: T.redLight, color: T.red, borderRadius: T.radiusSm, fontSize: 13, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{error}</span>
          <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', color: T.red, cursor: 'pointer', fontSize: 16, fontWeight: 700, lineHeight: 1, padding: '0 4px' }}>×</button>
        </div>
      )}

      {viewMode === 'map' && (
        <SourceMapView
          sourceMap={sourceMap}
          syncingIds={syncingIds}
          onEdit={openEditModal}
          onSync={handleSync}
        />
      )}

      {viewMode === 'list' && (
        <>
      {/* RSSHub Instances Manager */}
      <div style={{ background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray200}`, padding: 20, marginBottom: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <h2 style={{ fontSize: 15, fontWeight: 700, color: T.gray800, marginBottom: 2 }}>RSSHub 实例</h2>
            <p style={{ fontSize: 12, color: T.gray400 }}>按优先级顺序尝试，禁用则跳过。添加小红书/微博/B站等路由时使用。</p>
          </div>
          {rsshubSaving && <span style={{ fontSize: 12, color: T.gray400 }}>保存中…</span>}
        </div>

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
                <button onClick={() => toggleInstance(inst.url)} disabled={rsshubSaving}
                  style={{ padding: '3px 10px', fontSize: 11, fontWeight: 600, borderRadius: 999, border: 'none', cursor: rsshubSaving ? 'wait' : 'pointer', background: inst.enabled ? '#DCFCE7' : T.gray200, color: inst.enabled ? '#16A34A' : T.gray400 }}>
                  {inst.enabled ? '启用' : '禁用'}
                </button>
                <button onClick={() => deleteInstance(inst.url)} disabled={rsshubSaving}
                  style={{ padding: '3px 8px', fontSize: 11, borderRadius: T.radiusSm, border: 'none', cursor: rsshubSaving ? 'wait' : 'pointer', background: T.redLight, color: T.red }}>
                  删除
                </button>
              </div>
            ))
          )}
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <input type="text" value={newInstanceUrl} onChange={(e) => setNewInstanceUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addInstance()} placeholder="https://rsshub.example.com"
            style={{ flex: 1, padding: '7px 12px', fontSize: 13, border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm, outline: 'none', fontFamily: T.mono }} />
          <button onClick={addInstance} disabled={rsshubSaving || !newInstanceUrl.trim()}
            style={{ padding: '7px 16px', fontSize: 13, fontWeight: 600, background: rsshubSaving || !newInstanceUrl.trim() ? T.gray200 : T.primary, color: T.white, border: 'none', borderRadius: T.radiusSm, cursor: rsshubSaving || !newInstanceUrl.trim() ? 'wait' : 'pointer' }}>
            + 添加实例
          </button>
        </div>
      </div>

      {/* Loading State */}
      {loading && sources.length === 0 && (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 200, color: T.gray400, fontSize: 14, gap: 10 }}>
          <Spinner />
          <span>加载中…</span>
        </div>
      )}

      {/* Table */}
      {!loading && (
        <div style={{ background: T.white, borderRadius: T.radius, border: `1px solid ${T.gray100}`, overflow: 'hidden' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1.2fr 1fr 1fr 0.8fr 1.5fr', padding: '12px 24px', background: T.gray50, borderBottom: `1px solid ${T.gray200}`, fontSize: 12, fontWeight: 600, color: T.gray500, textTransform: 'uppercase' as const, letterSpacing: '0.05em' }}>
            {['名称', '类型', '分类', '最后同步', '采集频率', '权重', '状态', '操作'].map((h) => (
              <div key={h}>{h}</div>
            ))}
          </div>
          {sources.length === 0 && (
            <div style={{ padding: '48px 24px', textAlign: 'center' as const, color: T.gray400, fontSize: 14 }}>暂无信源，点击「添加信源」开始</div>
          )}
          {sources.map((src) => (
            <SourceRowComponent key={src.id} source={src} syncing={syncingIds.has(src.id)} syncResult={syncResults[src.id] || null}
              deleting={deletingIds.has(src.id)} onSync={() => handleSync(src.id)} onEdit={() => openEditModal(src)}
              onDelete={() => handleDelete(src.id)} onWeightChange={(w) => handleWeightChange(src.id, w)}
              onIntervalChange={(mins) => handleIntervalChange(src.id, mins)} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {total > pageSize && (
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginTop: 16, padding: '12px 0', fontSize: 13, color: T.gray500,
        }}>
          <span>
            第 {(page - 1) * pageSize + 1}-{Math.min(page * pageSize, total)} 条，共 {total} 条
          </span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              disabled={page <= 1}
              onClick={() => fetchSources(page - 1)}
              style={{
                padding: '6px 14px', fontSize: 13,
                background: page <= 1 ? T.gray100 : T.white,
                color: page <= 1 ? T.gray300 : T.gray700,
                border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
                cursor: page <= 1 ? 'not-allowed' : 'pointer',
              }}
            >
              上一页
            </button>
            {Array.from({ length: Math.ceil(total / pageSize) }, (_, i) => i + 1)
              .filter((p) => {
                // Show first, last, and ±2 around current
                if (p === 1 || p === Math.ceil(total / pageSize)) return true;
                return Math.abs(p - page) <= 2;
              })
              .map((p, idx, arr) => {
                const pages = arr;
                const showEllipsis = idx > 0 && p - pages[idx - 1] > 1;
                return (
                  <React.Fragment key={p}>
                    {showEllipsis && <span style={{ padding: '6px 4px', color: T.gray400 }}>…</span>}
                    <button
                      onClick={() => fetchSources(p)}
                      style={{
                        padding: '6px 12px', fontSize: 13,
                        background: p === page ? T.primary : T.white,
                        color: p === page ? T.white : T.gray700,
                        border: `1px solid ${p === page ? T.primary : T.gray200}`,
                        borderRadius: T.radiusSm,
                        cursor: p === page ? 'default' : 'pointer',
                        fontWeight: p === page ? 600 : 400,
                      }}
                    >
                      {p}
                    </button>
                  </React.Fragment>
                );
              })}
            <button
              disabled={page >= Math.ceil(total / pageSize)}
              onClick={() => fetchSources(page + 1)}
              style={{
                padding: '6px 14px', fontSize: 13,
                background: page >= Math.ceil(total / pageSize) ? T.gray100 : T.white,
                color: page >= Math.ceil(total / pageSize) ? T.gray300 : T.gray700,
                border: `1px solid ${T.gray200}`, borderRadius: T.radiusSm,
                cursor: page >= Math.ceil(total / pageSize) ? 'not-allowed' : 'pointer',
              }}
            >
              下一页
            </button>
          </div>
        </div>
      )}
        </>
      )}

      {/* Add Source Modal */}
      {showAddModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => setShowAddModal(false)}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: T.white, borderRadius: T.radius, padding: 32, width: 480, maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: T.gray900, marginBottom: 24 }}>添加信源</h2>
            <SourceForm form={form} setForm={setForm} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 28 }}>
              <button onClick={() => setShowAddModal(false)} disabled={submitting}
                style={{ padding: '8px 20px', fontSize: 13, fontWeight: 500, background: T.gray100, color: T.gray600, border: 'none', borderRadius: T.radiusSm, cursor: 'pointer' }}>
                取消
              </button>
              <button onClick={handleCreate} disabled={submitting || !form.name.trim()}
                style={{ padding: '8px 20px', fontSize: 13, fontWeight: 600, background: submitting || !form.name.trim() ? T.gray300 : T.primary, color: T.white, border: 'none', borderRadius: T.radiusSm, cursor: submitting ? 'wait' : 'pointer' }}>
                {submitting ? '提交中…' : '添加'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Source Modal */}
      {editingSource && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
          onClick={() => { setEditingSource(null); setForm(emptyForm); }}>
          <div onClick={(e) => e.stopPropagation()} style={{ background: T.white, borderRadius: T.radius, padding: 32, width: 480, maxWidth: '90vw', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
            <h2 style={{ fontSize: 20, fontWeight: 700, color: T.gray900, marginBottom: 24 }}>编辑信源</h2>
            <SourceForm form={form} setForm={setForm} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 28 }}>
              <button onClick={() => { setEditingSource(null); setForm(emptyForm); }} disabled={submitting}
                style={{ padding: '8px 20px', fontSize: 13, fontWeight: 500, background: T.gray100, color: T.gray600, border: 'none', borderRadius: T.radiusSm, cursor: 'pointer' }}>
                取消
              </button>
              <button onClick={handleUpdate} disabled={submitting || !form.name.trim()}
                style={{ padding: '8px 20px', fontSize: 13, fontWeight: 600, background: submitting || !form.name.trim() ? T.gray300 : T.primary, color: T.white, border: 'none', borderRadius: T.radiusSm, cursor: submitting ? 'wait' : 'pointer' }}>
                {submitting ? '保存中…' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
