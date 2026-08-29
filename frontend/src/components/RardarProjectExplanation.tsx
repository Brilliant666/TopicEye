'use client';

import { type ReactNode, useState } from 'react';
import { AlertTriangle, BookOpen, Boxes, Compass, Gauge, Loader2, Sparkles, Target } from 'lucide-react';

import { explainProject, explainProjectById, type ProjectExplanation } from '@/lib/rardar-product';
import styles from './RardarFoundation.module.css';

export default function RardarProjectExplanation({
  repository,
  githubRepositoryId,
  generationId,
}: {
  repository: string;
  githubRepositoryId?: number;
  generationId: string;
}) {
  const usesStaticEvidence = githubRepositoryId !== undefined;
  const [result, setResult] = useState<ProjectExplanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        githubRepositoryId === undefined
          ? await explainProject(repository, generationId)
          : await explainProjectById(githubRepositoryId, generationId),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'rardar_request_failed');
    } finally {
      setLoading(false);
    }
  }

  if (!result && !error) {
    return (
      <>
        <button type="button" className={styles.aiButton} onClick={run} disabled={loading}>
          {loading ? <Loader2 size={15} className={styles.spin} /> : <Sparkles size={15} />}
          {loading
            ? (usesStaticEvidence ? '正在基于静态证据分析' : '正在读取项目事实并分析')
            : (usesStaticEvidence ? '生成 AI 深度解读' : 'AI 解读')}
        </button>
        {loading && (
          <div className={`${styles.aiPanel} ${styles.aiLoading}`} role="status" aria-live="polite">
            <div><Loader2 size={15} className={styles.spin} /><strong>正在基于静态证据分析</strong></div>
            <p>首次生成预计需要一些时间。页面其他官方档案与 Today 事实仍可继续阅读，请勿重复提交。</p>
          </div>
        )}
      </>
    );
  }

  if (error || result?.state === 'unavailable') {
    return (
      <div className={`${styles.aiPanel} ${styles.aiUnavailable}`}>
        <div><AlertTriangle size={15} /><strong>AI 暂不可用</strong></div>
        <p>{usesStaticEvidence ? '官方档案和今日事实不受影响，可以稍后安全重试。' : '事实榜单不受影响，可以稍后安全重试。'}</p>
        <button type="button" onClick={run} disabled={loading}>重试</button>
      </div>
    );
  }

  const analysis = result?.analysis;
  if (!analysis) return null;
  return (
    <div className={styles.aiPanel} data-testid={`ai-explanation-${repository}`}>
      <div>
        <Sparkles size={15} />
        <strong>{usesStaticEvidence ? 'AI 深度解读' : '项目证据解读'}</strong>
        <span>{usesStaticEvidence ? '基于当前 Serving Projection 的官方 README、目录、Release 与许可证证据' : '按需生成 · 不复述榜单事实'}</span>
      </div>
      <section className={styles.insightConclusion}>
        <span>结论摘要</span>
        <p>{analysis.conclusionSummary.text}</p>
        <EvidenceRefs values={analysis.conclusionSummary.evidenceRefs} />
      </section>
      <div className={styles.insightSections}>
        {analysis.differentiators.length > 0 && (
          <InsightSection icon={Sparkles} title="差异化判断">
            {analysis.differentiators.map((item) => (
              <InsightItem key={`${item.text}-${item.evidenceRefs.join()}`} text={item.text} refs={item.evidenceRefs} />
            ))}
          </InsightSection>
        )}
        <InsightSection icon={Boxes} title="可复用资产">
          {analysis.reusableAssets.map((item) => (
            <div className={styles.insightItem} key={`${item.asset}-${item.evidenceRefs.join()}`}>
              <strong>{item.asset}</strong>
              <span className={styles.reuseType}>{reuseLabel(item.reuseType)}</span>
              <p>{item.howToUse}</p>
              <EvidenceRefs values={item.evidenceRefs} />
            </div>
          ))}
        </InsightSection>
        <InsightSection icon={Gauge} title="复用成本">
          <div className={styles.insightItem}>
            <strong>{reuseCostLabel(analysis.reuseCost.level)}</strong>
            <p>{analysis.reuseCost.reason}</p>
            <EvidenceRefs values={analysis.reuseCost.evidenceRefs} />
          </div>
        </InsightSection>
        <InsightSection icon={Target} title="适合场景">
          {analysis.bestFitScenarios.map((item) => (
            <InsightItem key={`${item.text}-${item.evidenceRefs.join()}`} text={item.text} refs={item.evidenceRefs} />
          ))}
        </InsightSection>
        <InsightSection icon={Compass} title="建议先看">
          {analysis.startHere.map((item) => (
            <div className={styles.insightItem} key={`${item.path}-${item.evidenceRefs.join()}`}>
              <strong>{item.label}</strong><code>{item.path}</code>
              <EvidenceRefs values={item.evidenceRefs} />
            </div>
          ))}
        </InsightSection>
        {analysis.implementationBoundaries.length > 0 && (
          <InsightSection icon={BookOpen} title="落地边界">
            {analysis.implementationBoundaries.map((item) => (
              <InsightItem key={`${item.text}-${item.evidenceRefs.join()}`} text={item.text} refs={item.evidenceRefs} />
            ))}
          </InsightSection>
        )}
      </div>
      <AIProvenance result={result} usesStaticEvidence={usesStaticEvidence} />
    </div>
  );
}

function InsightSection({ icon: Icon, title, children }: { icon: typeof Sparkles; title: string; children: ReactNode }) {
  return <section className={styles.insightSection}><h4><Icon size={14} /> {title}</h4>{children}</section>;
}

function InsightItem({ text, refs }: { text: string; refs: string[] }) {
  return <div className={styles.insightItem}><p>{text}</p><EvidenceRefs values={refs} /></div>;
}

function EvidenceRefs({ values }: { values: string[] }) {
  const labels = Array.from(new Set(values.map(evidenceLabel)));
  return <div className={styles.evidenceRefs}>{labels.map((value) => <span key={value}>{value}</span>)}</div>;
}

function evidenceLabel(value: string) {
  if (value === 'description') return 'GitHub Description';
  if (value === 'license') return '许可证';
  if (value === 'release:latest') return '最新 Release';
  if (value.startsWith('readme:')) return 'README';
  if (value.startsWith('tree:')) return `目录 ${value.slice(5)}`;
  if (value.startsWith('file:')) return `文件 ${value.slice(5)}`;
  return '仓库资料';
}

function reuseLabel(value: string) {
  return {
    whole_product: '整套产品', module_library: '模块 / 类库', provider_connector: 'Provider / 连接器',
    workflow: '工作流', reference_only: '参考资产', not_recommended: '不建议复用',
  }[value] || value;
}

function reuseCostLabel(value: 'low' | 'medium' | 'high' | 'unknown') {
  return { low: '低成本', medium: '中等成本', high: '高成本', unknown: '证据不足，成本未知' }[value];
}

function AIProvenance({ result, usesStaticEvidence }: { result: ProjectExplanation; usesStaticEvidence: boolean }) {
  return (
    <small className={styles.aiProvenance}>
      {result.model || '已配置的 rardar 模型'} · {result.cacheHit ? 'AI 缓存命中' : '本次生成'} · {usesStaticEvidence ? '静态证据缓存命中' : (result.evidenceCacheHit ? '证据缓存命中' : '实时有界证据')}
    </small>
  );
}
