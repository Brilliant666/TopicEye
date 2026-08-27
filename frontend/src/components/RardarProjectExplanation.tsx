'use client';

import { useState } from 'react';
import { AlertTriangle, Loader2, Sparkles } from 'lucide-react';

import { explainProject, type ProjectExplanation } from '@/lib/rardar-product';
import styles from './RardarFoundation.module.css';

export default function RardarProjectExplanation({
  repository,
  generationId,
}: {
  repository: string;
  generationId: string;
}) {
  const [result, setResult] = useState<ProjectExplanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setResult(await explainProject(repository, generationId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'rardar_request_failed');
    } finally {
      setLoading(false);
    }
  }

  if (!result && !error) {
    return (
      <button type="button" className={styles.aiButton} onClick={run} disabled={loading}>
        {loading ? <Loader2 size={15} className={styles.spin} /> : <Sparkles size={15} />}
        {loading ? '正在读取项目事实并分析' : 'AI 解读'}
      </button>
    );
  }

  if (error || result?.state === 'unavailable') {
    return (
      <div className={`${styles.aiPanel} ${styles.aiUnavailable}`}>
        <div><AlertTriangle size={15} /><strong>AI 暂不可用</strong></div>
        <p>事实榜单不受影响。{error || result?.errorCode}</p>
        <button type="button" onClick={run} disabled={loading}>重试</button>
      </div>
    );
  }

  if (result?.state === 'plain') {
    return (
      <div className={styles.aiPanel}>
        <div><Sparkles size={15} /><strong>AI 项目解读 · 有界文本</strong></div>
        <p className={styles.aiPlain}>{result.plainText}</p>
        <AIProvenance result={result} />
      </div>
    );
  }

  const analysis = result?.analysis;
  if (!analysis) return null;
  return (
    <div className={styles.aiPanel} data-testid={`ai-explanation-${repository}`}>
      <div><Sparkles size={15} /><strong>AI 项目解读</strong><span>模型判断，不改变事实名次</span></div>
      <dl className={styles.aiGrid}>
        <div><dt>中文简介</dt><dd>{analysis.summaryZh}</dd></div>
        <div><dt>为什么值得看</dt><dd>{analysis.whyWorthWatching}</dd></div>
        <div><dt>可以怎样复用</dt><dd>{analysis.reuseIdeas.join('；')}</dd></div>
        <div><dt>风险与注意</dt><dd>{analysis.risks.join('；')}</dd></div>
      </dl>
      <AIProvenance result={result} />
    </div>
  );
}

function AIProvenance({ result }: { result: ProjectExplanation }) {
  return (
    <small className={styles.aiProvenance}>
      {result.model || '已配置的 rardar 模型'} · {result.cacheHit ? '缓存命中' : '本次生成'}
    </small>
  );
}
