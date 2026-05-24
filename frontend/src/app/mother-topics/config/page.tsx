'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { motherTopicsApi, type MotherTopic } from '@/lib/api';

/* ── helpers ── */

function TopicCard({
  topic,
  onSave,
  onDelete,
}: {
  topic: MotherTopic;
  onSave: (updated: Partial<MotherTopic>) => void;
  onDelete: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    name: topic.name,
    description: topic.description || '',
    keywords: topic.keywords.join(', '),
    weight: topic.weight,
    content_type: topic.content_type || '',
    target_reader: topic.target_reader || '',
    is_active: topic.is_active,
    display_order: topic.display_order,
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    const keywords = form.keywords.split(',').map(k => k.trim()).filter(Boolean);
    await onSave({
      name: form.name,
      description: form.description || undefined,
      keywords,
      weight: form.weight,
      content_type: form.content_type || undefined,
      target_reader: form.target_reader || undefined,
      is_active: form.is_active,
      display_order: form.display_order,
    });
    setSaving(false);
    setEditing(false);
  };

  const contentTypeColor: Record<string, string> = {
    '工具评测': '#6366f1',
    '方法论': '#10b981',
    '观察': '#f59e0b',
    '随笔': '#ec4899',
    '教程': '#0ea5e9',
    '观点': '#8b5cf6',
  };

  return (
    <div style={{
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      padding: '20px',
      marginBottom: 16,
      background: '#fff',
    }}>
      {/* card header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: '#111827', margin: 0 }}>{topic.name}</h3>
            {topic.content_type && (
              <span style={{
                padding: '2px 8px',
                borderRadius: 8,
                fontSize: 11,
                fontWeight: 500,
                background: `${contentTypeColor[topic.content_type] || '#6366f1'}15`,
                color: contentTypeColor[topic.content_type] || '#6366f1',
              }}>
                {topic.content_type}
              </span>
            )}
          </div>
          {topic.description && (
            <p style={{ fontSize: 12, color: '#6b7280', margin: '2px 0 0', lineHeight: 1.5 }}>
              {topic.description}
            </p>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: '#9ca3af' }}>权重 {topic.weight}</span>
          {!topic.is_active && (
            <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 8, background: '#fee2e2', color: '#dc2626' }}>
              已停用
            </span>
          )}
        </div>
      </div>

      {editing ? (
        /* edit form */
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
              名称
            </label>
            <input
              value={form.name}
              onChange={e => setForm({ ...form, name: e.target.value })}
              style={{ width: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
              描述
            </label>
            <input
              value={form.description}
              onChange={e => setForm({ ...form, description: e.target.value })}
              style={{ width: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
            />
          </div>
          <div>
            <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
              关键词（逗号分隔）
            </label>
            <textarea
              value={form.keywords}
              onChange={e => setForm({ ...form, keywords: e.target.value })}
              rows={4}
              style={{ width: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 12, fontFamily: 'monospace', resize: 'vertical' }}
            />
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
              当前 {form.keywords.split(',').filter(k => k.trim()).length} 个关键词
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12 }}>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
                权重乘数
              </label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="3"
                value={form.weight}
                onChange={e => setForm({ ...form, weight: parseFloat(e.target.value) })}
                style={{ width: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: '#374151', display: 'block', marginBottom: 4 }}>
                目标读者
              </label>
              <input
                value={form.target_reader}
                onChange={e => setForm({ ...form, target_reader: e.target.value })}
                style={{ width: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13 }}
              />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '6px 16px',
                borderRadius: 8,
                background: '#10b981',
                color: '#fff',
                border: 'none',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
                opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              onClick={() => setEditing(false)}
              style={{
                padding: '6px 16px',
                borderRadius: 8,
                background: '#f3f4f6',
                color: '#374151',
                border: 'none',
                fontSize: 13,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        /* view mode */
        <>
          {/* keywords display */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#374151', marginBottom: 6 }}>
              关键词 ({topic.keywords.length})
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {topic.keywords.slice(0, 20).map(kw => (
                <span key={kw} style={{
                  padding: '3px 10px',
                  borderRadius: 12,
                  fontSize: 12,
                  background: '#f3f4f6',
                  color: '#374151',
                }}>
                  {kw}
                </span>
              ))}
              {topic.keywords.length > 20 && (
                <span style={{ fontSize: 12, color: '#9ca3af', padding: '3px 8px' }}>
                  +{topic.keywords.length - 20} 更多
                </span>
              )}
            </div>
          </div>

          {/* target reader */}
          {topic.target_reader && (
            <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
              <b>目标读者:</b> {topic.target_reader}
            </div>
          )}

          {/* actions */}
          <div style={{ display: 'flex', gap: 8, marginTop: 12, paddingTop: 12, borderTop: '1px solid #f3f4f6' }}>
            <button
              onClick={() => setEditing(true)}
              style={{
                padding: '5px 14px',
                borderRadius: 8,
                background: '#6366f1',
                color: '#fff',
                border: 'none',
                fontSize: 12,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              编辑
            </button>
            <button
              onClick={() => onDelete(topic.id)}
              style={{
                padding: '5px 14px',
                borderRadius: 8,
                background: '#fee2e2',
                color: '#dc2626',
                border: 'none',
                fontSize: 12,
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              停用
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/* ── Main Page ── */

export default function MotherTopicsConfigPage() {
  const router = useRouter();
  const [topics, setTopics] = useState<MotherTopic[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const loadTopics = useCallback(() => {
    setLoading(true);
    motherTopicsApi.list(false).then(ts => {
      setTopics(ts.sort((a, b) => a.display_order - b.display_order));
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, []);

  useEffect(() => { loadTopics(); }, [loadTopics]);

  const handleSave = async (id: number, updated: Partial<MotherTopic>) => {
    await motherTopicsApi.update(id, updated);
    await loadTopics();
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确认停用此母题？停用后相关推荐将不再出现。')) return;
    await motherTopicsApi.delete(id);
    await loadTopics();
  };

  return (
    <div style={{ padding: '20px 24px', maxWidth: 860 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#111827', marginBottom: 4 }}>
            ⚙️ 母题配置
          </h1>
          <p style={{ fontSize: 13, color: '#6b7280', margin: 0 }}>
            配置你的公众号内容支柱，调整关键词以精准匹配你的写作方向
          </p>
        </div>
        <button
          onClick={() => router.push('/my-topics')}
          style={{
            padding: '7px 16px',
            borderRadius: 8,
            background: '#f3f4f6',
            color: '#374151',
            border: 'none',
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
            textDecoration: 'none',
          }}
        >
          ← 返回我的母题
        </button>
      </div>

      {/* Info box */}
      <div style={{
        padding: '12px 16px',
        background: '#eff6ff',
        border: '1px solid #bfdbfe',
        borderRadius: 10,
        marginBottom: 24,
        fontSize: 13,
        color: '#1e40af',
        lineHeight: 1.6,
      }}>
        <b>打分规则:</b> 母题匹配分 × 权重 + 新鲜度加成 → 最终得分<br/>
        <b>阈值:</b> 80+ 今日主选题 / 65-79 值得储备 / 50-64 观察池 / &lt;50 过滤
      </div>

      {/* Topics */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#9ca3af' }}>加载中...</div>
      ) : (
        <div>
          {topics.map(topic => (
            <TopicCard
              key={topic.id}
              topic={topic}
              onSave={updated => handleSave(topic.id, updated)}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* Scoring explanation */}
      <div style={{
        marginTop: 32,
        padding: '16px',
        background: '#f9fafb',
        borderRadius: 10,
        border: '1px solid #e5e7eb',
      }}>
        <h3 style={{ fontSize: 14, fontWeight: 700, color: '#374151', marginBottom: 12 }}>打分公式详解</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 24px' }}>
          {[
            ['母题匹配', '0.0~1.0（匹配1个=0.3，2个=0.6，3个+=1.0）'],
            ['权重', '默认 1.0，可调整为 0.5~2.0'],
            ['新鲜度', 'hot_value/10000（0~1.0）'],
            ['最终得分', 'keyword_score × weight + freshness × 0.1'],
          ].map(([label, desc]) => (
            <div key={label} style={{ display: 'flex', gap: 8, fontSize: 12 }}>
              <span style={{ fontWeight: 600, color: '#374151', minWidth: 60 }}>{label}</span>
              <span style={{ color: '#6b7280' }}>{desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}