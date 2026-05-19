'use client';

import React from 'react';
import { T } from '@/lib/design-tokens';

export interface FormState {
  name: string;
  source_type: string;
  url: string;
  category: string;
  enabled: boolean;
}

export const emptyForm: FormState = {
  name: '',
  source_type: 'RSS',
  url: '',
  category: 'AI',
  enabled: true,
};

export const CATEGORIES = ['AI', '商业', '科技', '教育', '自媒体', '生活', '职场', '产品'];
export const SOURCE_TYPES = ['RSS', 'RSSHub', '公众号', '网站'];

interface SourceFormProps {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
}

export default function SourceForm({ form, setForm }: SourceFormProps) {
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
