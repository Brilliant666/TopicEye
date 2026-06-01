'use client';

import React from 'react';
import { cx } from '@/components/ui';

export interface FormState {
  name: string;
  source_type: string;
  url: string;
  keyword: string;
  category: string;
  weight: number;
  enabled: boolean;
}

export const emptyForm: FormState = {
  name: '',
  source_type: 'RSS',
  url: '',
  keyword: '',
  category: 'AI',
  weight: 3,
  enabled: true,
};

export const CATEGORIES = ['AI', '商业', '科技', '教育', '自媒体', '生活', '职场', '产品'];
export const SOURCE_TYPES = ['RSS', 'RSSHub', 'Reddit', 'TwitterRSS', 'API', '公众号', '网站', 'Zhihu'];

interface SourceFormProps {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return <label className="mb-1.5 block text-[13px] font-bold text-gray-700">{children}</label>;
}

const inputClass = 'h-9 w-full rounded-xs border border-gray-200 bg-white px-3 text-sm text-gray-800 outline-none transition placeholder:text-gray-300 focus:border-primary-border focus:ring-2 focus:ring-primary-light';

export default function SourceForm({ form, setForm }: SourceFormProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <FieldLabel>
          信源名称 <span className="text-red">*</span>
        </FieldLabel>
        <input
          type="text"
          placeholder="例：量子位"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          className={inputClass}
        />
      </div>

      <div>
        <FieldLabel>类型</FieldLabel>
        <select
          value={form.source_type}
          onChange={(e) => setForm((f) => ({ ...f, source_type: e.target.value }))}
          className={inputClass}
        >
          {SOURCE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      <div>
        <FieldLabel>URL / 地址</FieldLabel>
        <input
          type="text"
          placeholder={form.source_type === 'API' ? 'https://example.com/api/items' : 'https://example.com/feed'}
          value={form.url}
          onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
          className={cx(inputClass, 'font-mono')}
        />
      </div>

      {form.source_type === 'API' && (
        <div>
          <FieldLabel>
            API 配置
            <span className="ml-2 text-[11px] font-normal text-gray-400">JSON，可选</span>
          </FieldLabel>
          <textarea
            value={form.keyword}
            onChange={(e) => setForm((f) => ({ ...f, keyword: e.target.value }))}
            placeholder={'{"items_path":"data.items","fields":{"title":"title","url":"url","summary":"summary"}}'}
            className="min-h-28 w-full resize-y rounded-xs border border-gray-200 bg-white px-3 py-2 font-mono text-xs leading-5 text-gray-800 outline-none transition placeholder:text-gray-300 focus:border-primary-border focus:ring-2 focus:ring-primary-light"
          />
        </div>
      )}

      <div>
        <FieldLabel>分类</FieldLabel>
        <select
          value={form.category}
          onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
          className={inputClass}
        >
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      <div>
        <FieldLabel>
          信源权重
          <span className="ml-2 text-[11px] font-normal text-gray-400">权重越高，精选评分加分越多</span>
        </FieldLabel>
        <div className="flex items-center gap-1">
          {[1, 2, 3, 4, 5].map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setForm((f) => ({ ...f, weight: w }))}
              className={cx('text-lg leading-none transition', w <= form.weight ? 'text-primary' : 'text-gray-200')}
            >
              ●
            </button>
          ))}
          <span className="ml-2 font-mono text-xs text-gray-500">
            {form.weight}/5 {form.weight > 3 ? `(+${(form.weight - 3) * 6}分)` : form.weight < 3 ? `(${(form.weight - 3) * 6}分)` : '(基准)'}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
          className="h-4 w-4 cursor-pointer accent-primary"
          id="src-enabled"
        />
        <label htmlFor="src-enabled" className="cursor-pointer text-[13px] font-bold text-gray-700">启用此信源</label>
      </div>
    </div>
  );
}
