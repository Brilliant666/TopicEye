'use client';

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Plus, RadioTower, Search } from 'lucide-react';
import { sourcesApi } from '@/lib/api';
import type { CreateSourceRequest, UpdateSourceRequest } from '@/lib/api';
import type { Source, SyncResult } from '@/types';
import { Badge, Button, Panel, Toolbar, cx } from '@/components/ui';
import SourceForm, { FormState, emptyForm } from '@/components/SourceForm';
import SourceRowComponent, { type BackendSource, Spinner } from '@/components/SourceRow';
import { timeAgo } from '@/lib/utils';
import { sourceTypeLabel } from '@/lib/source-sync-board';

// ─── Page Component ───
//
// User-facing page for managing private (user-owned) sources.
// Reuses the same SourceForm / SourceRowComponent widgets as the admin
// /sources page so the create/edit/sync UX is identical — only the API
// endpoint differs (calls the /sources/me/* dual-track surface from T1-3a).
//
// Scope differences vs admin /sources/page.tsx:
//   - no RSSHub instance manager, no OPML import, no batch import, no
//     drag-to-reorder board (private sources don't need any of these).
//   - extra 403 "plan upgrade" banner when a free user tries to create.

type FormMode = 'create' | 'edit';

const pageSize = 50;

export default function MySourcesPage() {
  const [items, setItems] = useState<BackendSource[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<BackendSource | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');

  const [lastSync, setLastSync] = useState<SyncResult | null>(null);
  const [lastSyncedId, setLastSyncedId] = useState<number | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);

  // ─── Data fetching ───
  const fetchMine = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await sourcesApi.listMine({
        page: 1,
        page_size: pageSize,
        keyword: searchKeyword.trim() || undefined,
      });
      const list = (res?.items || []) as BackendSource[];
      setItems(list);
      setTotal(res?.total ?? list.length);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载我的信源失败');
    } finally {
      setLoading(false);
    }
  }, [searchKeyword]);

  useEffect(() => {
    fetchMine();
  }, [fetchMine]);

  // ─── Create ───
  const handleOpenCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setPlanError(null);
    setError(null);
    setShowForm(true);
  };

  // ─── Edit ───
  const handleEdit = (source: BackendSource) => {
    setEditing(source);
    setForm({
      name: source.name,
      source_type: source.source_type as FormState['source_type'],
      url: source.url,
      keyword: source.keyword || '',
      category: source.category || '',
      weight: source.weight || 3,
      fetch_interval_minutes: source.fetch_interval_minutes || 60,
      enabled: source.enabled !== false,
    });
    setPlanError(null);
    setError(null);
    setShowForm(true);
  };

  // ─── Submit (create or edit) ───
  const handleSubmit = async () => {
    if (!form.name.trim()) {
      setError('请输入信源名称');
      return;
    }
    if (!form.url.trim()) {
      setError('请输入信源 URL');
      return;
    }
    try {
      setSubmitting(true);
      setError(null);
      setPlanError(null);
      const payload = {
        name: form.name.trim(),
        source_type: form.source_type,
        url: form.url.trim(),
        keyword: form.keyword.trim() || null,
        category: form.category || null,
        weight: form.weight,
        fetch_interval_minutes: form.fetch_interval_minutes,
        enabled: form.enabled,
      } as CreateSourceRequest;

      if (editing) {
        await sourcesApi.updateMine(editing.id, payload as UpdateSourceRequest);
      } else {
        await sourcesApi.createMine(payload);
      }
      setShowForm(false);
      setEditing(null);
      setForm(emptyForm);
      await fetchMine();
    } catch (err: unknown) {
      const e = err as { status?: number; message?: string; detail?: string };
      if (e?.status === 403 || e?.message?.includes('套餐') || e?.message?.includes('Pro')) {
        setPlanError(e?.detail || e?.message || '当前套餐不支持创建私有信源，请升级到 Pro 及以上');
      } else {
        setError(e instanceof Error ? e.message : (editing ? '更新失败' : '创建失败'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ─── Delete ───
  const handleDelete = async (source: BackendSource) => {
    if (!confirm(`确定删除「${source.name}」吗？\n该操作不可撤销。`)) return;
    try {
      await sourcesApi.deleteMine(source.id);
      await fetchMine();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '删除失败');
    }
  };

  // ─── Sync ───
  const handleSync = async (source: BackendSource) => {
    if (!source.enabled) {
      setError('信源已禁用，请先启用再同步');
      return;
    }
    try {
      setSyncingId(source.id);
      const result = await sourcesApi.syncMine(source.id);
      setLastSync(result);
      setLastSyncedId(source.id);
      await fetchMine();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '同步失败');
    } finally {
      setSyncingId(null);
    }
  };

  // ─── Render ───
  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <Toolbar>
        <div className="flex items-center gap-2">
          <RadioTower className="w-5 h-5 text-primary" />
          <h1 className="text-xl font-semibold">我的信源</h1>
          <Badge tone="teal">{total}</Badge>
        </div>
        <p className="text-sm text-text-muted">
          私有信源仅自己可见，抓取的内容不会出现在全局信源池中
        </p>
        <div className="ml-auto flex items-center gap-2">
          <SearchBox value={searchKeyword} onChange={setSearchKeyword} />
          <Button
            variant="primary"
            onClick={handleOpenCreate}
            aria-label="新建私有信源"
          >
            <Plus className="w-4 h-4 mr-1" /> 新建私有信源
          </Button>
        </div>
      </Toolbar>

      {/* Plan upgrade banner (403 on create) */}
      {planError && (
        <Panel className="border-amber-border bg-amber-light text-amber">
          <div className="flex items-start justify-between gap-3">
            <div>
              <strong className="font-semibold">当前套餐不支持创建私有信源</strong>
              <p className="text-sm mt-1">{planError}</p>
            </div>
            <Button variant="ghost" onClick={() => setPlanError(null)}>关闭</Button>
          </div>
        </Panel>
      )}

      {/* Error banner */}
      {error && (
        <Panel className="border-red-border bg-red-light text-red">
          <div className="flex items-start justify-between gap-3">
            <p className="text-sm">{error}</p>
            <Button variant="ghost" onClick={() => setError(null)}>关闭</Button>
          </div>
        </Panel>
      )}

      {/* Sync result notice */}
      {lastSync && (
        <Panel className="border-teal-border bg-teal-light text-teal">
          <p className="text-sm">
            同步完成：抓取 {lastSync.fetched} 条，新增 {lastSync.new} 条，重复 {lastSync.duplicates} 条
          </p>
        </Panel>
      )}

      {/* List */}
      <Panel title="私有信源">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : items.length === 0 ? (
          <EmptyState keyword={searchKeyword} onCreate={handleOpenCreate} />
        ) : (
          <SourceList
            items={items}
            syncingId={syncingId}
            lastSyncedId={lastSyncedId}
            onEdit={handleEdit}
            onDelete={handleDelete}
            onSync={handleSync}
          />
        )}
      </Panel>

      {/* Create / edit modal */}
      {showForm && (
        <FormModal
          editing={editing}
          form={form}
          setForm={setForm}
          submitting={submitting}
          onSubmit={handleSubmit}
          onClose={() => {
            setShowForm(false);
            setEditing(null);
            setForm(emptyForm);
          }}
        />
      )}
    </div>
  );
}

// ─── Sub-components ───

function SearchBox({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="relative">
      <Search className="w-4 h-4 absolute left-2 top-1/2 -translate-y-1/2 text-text-muted" />
      <input
        type="text"
        placeholder="按名称 / URL 搜索"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="pl-8 pr-3 py-1.5 text-sm bg-surface-1 border border-border rounded-md w-56"
      />
    </div>
  );
}

function EmptyState({ keyword, onCreate }: { keyword: string; onCreate: () => void }) {
  if (keyword) {
    return (
      <div className="text-center py-12 text-text-muted">
        <p>没有匹配「{keyword}」的私有信源</p>
      </div>
    );
  }
  return (
    <div className="text-center py-12 space-y-3">
      <RadioTower className="w-12 h-12 mx-auto text-text-muted opacity-50" />
      <p className="text-text-muted">还没有私有信源</p>
      <p className="text-sm text-text-muted">
        创建私有信源来抓取专属内容（仅你可见，不进全局池）
      </p>
      <Button variant="primary" onClick={onCreate}>
        <Plus className="w-4 h-4 mr-1" /> 创建第一个私有信源
      </Button>
    </div>
  );
}

function SourceList({
  items,
  syncingId,
  lastSyncedId,
  onEdit,
  onDelete,
  onSync,
}: {
  items: BackendSource[];
  syncingId: number | null;
  lastSyncedId: number | null;
  onEdit: (s: BackendSource) => void;
  onDelete: (s: BackendSource) => void;
  onSync: (s: BackendSource) => void;
}) {
  return (
    <div className="divide-y divide-border">
      {items.map((source) => (
        <SourceRowComponent
          key={source.id}
          source={source}
          syncing={syncingId === source.id}
          syncResult={syncingId === source.id ? null : (lastSyncedId === source.id ? '同步完成' : null)}
          deleting={false}
          onEdit={() => onEdit(source)}
          onDelete={() => onDelete(source)}
          onSync={() => onSync(source)}
        />
      ))}
    </div>
  );
}

function FormModal({
  editing,
  form,
  setForm,
  submitting,
  onSubmit,
  onClose,
}: {
  editing: BackendSource | null;
  form: FormState;
  setForm: (f: FormState) => void;
  submitting: boolean;
  onSubmit: () => void;
  onClose: () => void;
}) {
  const mode: FormMode = editing ? 'edit' : 'create';
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-surface-1 rounded-lg shadow-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-border flex items-center justify-between">
          <h2 className="text-lg font-semibold">
            {mode === 'create' ? '新建私有信源' : `编辑：${editing?.name ?? ''}`}
          </h2>
          <Button variant="ghost" onClick={onClose}>取消</Button>
        </div>
        <div className="px-6 py-4">
          <SourceForm form={form} setForm={setForm as React.Dispatch<React.SetStateAction<FormState>>} />
        </div>
        <div className="px-6 py-3 border-t border-border flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={onSubmit} disabled={submitting}>
            {submitting ? '提交中…' : (mode === 'create' ? '创建' : '保存')}
          </Button>
        </div>
      </div>
    </div>
  );
}
