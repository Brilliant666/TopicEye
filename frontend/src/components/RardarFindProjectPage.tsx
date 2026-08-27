'use client';

import { FormEvent, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Code2,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  Star,
} from 'lucide-react';

import {
  findProjects,
  REUSE_TYPE_LABELS,
  type FindProjectResponse,
  type QuickProjectCandidate,
} from '@/lib/rardar-product';
import styles from './RardarFoundation.module.css';

const examples = [
  '我想找一个可以获取抖音主页作品和下载视频的 Python 项目。',
  '我在做开发者热点雷达，需要 GitHub 趋势采集、证据保存和项目匹配能力。',
];

export default function RardarFindProjectPage({
  initialRepositoryUrl = '',
  importedRepository = null,
  invalidPrefill = false,
}: {
  initialRepositoryUrl?: string;
  importedRepository?: string | null;
  invalidPrefill?: boolean;
}) {
  const [requirement, setRequirement] = useState(examples[0]);
  const [repositoryUrl, setRepositoryUrl] = useState(initialRepositoryUrl);
  const [result, setResult] = useState<FindProjectResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      setResult(await findProjects(requirement.trim(), repositoryUrl.trim() || null));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'rardar_request_failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page} data-rardar-route="/find">
      <section className={styles.findHero}>
        <div>
          <p className={styles.eyebrow}>Find Project · 可操作 MVP</p>
          <h1>别从零开始，先找到<span>能复用的开源项目</span></h1>
          <p>输入任务目标，也可以附带一个公开 GitHub 仓库。候选来自真实 GitHub Search；覆盖不足时会明确标注本地演示候选。</p>
        </div>
        <div className={styles.findBoundary}>
          <ShieldCheck size={18} />
          <p><strong>事实候选先行</strong><br />AI 只比较真实召回结果，不凭空生成仓库。</p>
        </div>
      </section>

      <form className={styles.findForm} onSubmit={submit}>
        <label htmlFor="rardar-requirement">你想完成什么？</label>
        <textarea
          id="rardar-requirement"
          value={requirement}
          onChange={(event) => setRequirement(event.target.value)}
          minLength={6}
          maxLength={1200}
          rows={5}
          required
        />
        <div className={styles.exampleRow}>
          {examples.map((example, index) => (
            <button type="button" key={example} onClick={() => setRequirement(example)}>示例 {index + 1}</button>
          ))}
        </div>
        <label htmlFor="rardar-repository-url"><Code2 size={15} /> 公开 GitHub 仓库 URL <span>（可选）</span></label>
        {importedRepository && (
          <p className={styles.importedRepository}><CheckCircle2 size={15} /> 已带入仓库：<strong>{importedRepository}</strong></p>
        )}
        {invalidPrefill && (
          <p className={styles.formError}><AlertTriangle size={15} /> URL 参数不是合法的公开 GitHub 仓库，已拒绝预填。</p>
        )}
        <input
          id="rardar-repository-url"
          type="url"
          inputMode="url"
          value={repositoryUrl}
          onChange={(event) => setRepositoryUrl(event.target.value)}
          placeholder="https://github.com/owner/repository"
        />
        <button className={styles.findSubmit} type="submit" disabled={loading || requirement.trim().length < 6}>
          {loading ? <Loader2 size={17} className={styles.spin} /> : <Search size={17} />}
          {loading ? '正在召回候选并比较' : '开始找项目'}
        </button>
        {error && <p className={styles.formError}><AlertTriangle size={15} /> 请求失败：{error}</p>}
      </form>

      {result && <FindResults result={result} />}
    </div>
  );
}

function FindResults({ result }: { result: FindProjectResponse }) {
  return (
    <div className={styles.findResults}>
      <div className={styles.sectionHeading}>
        <div><h2>快速候选 · {result.quickCandidates.length}</h2><p>{result.coverageLabel}</p></div>
        <span className={`${styles.dataState} ${result.searchState === 'github_live' ? styles.dataLive : ''}`}>
          {result.searchState === 'github_live' ? 'GitHub 实时召回' : result.searchState === 'demo' ? '本地演示候选' : 'Limited Mode'}
        </span>
      </div>
      <p className={styles.sourceLine}>来源：{result.sources.join(' · ') || '无可用来源'}。结果不代表扫描了全部 GitHub。</p>
      <section className={styles.quickGrid} aria-label="找项目快速候选">
        {result.quickCandidates.map((candidate) => <QuickCandidateCard key={`${candidate.dataState}-${candidate.githubRepositoryId}`} candidate={candidate} />)}
      </section>

      <div className={styles.sectionHeading}>
        <div><h2>AI 横向比较 · Top 3</h2><p>同一需求与三份标准化仓库事实一次比较，reasoning effort 不作前置要求。</p></div>
      </div>
      <AIComparison result={result} />
    </div>
  );
}

function QuickCandidateCard({ candidate }: { candidate: QuickProjectCandidate }) {
  return (
    <article className={styles.quickCard}>
      <div className={styles.quickCardTop}>
        <a href={candidate.htmlUrl} target="_blank" rel="noreferrer">{candidate.repository}<ArrowUpRight size={14} /></a>
        <span className={candidate.dataState === 'github_live' ? styles.liveBadge : styles.demoBadge}>
          {candidate.dataState === 'github_live' ? 'GitHub live' : '本地演示'}
        </span>
      </div>
      <p>{candidate.description || 'GitHub 暂未提供简介。'}</p>
      <dl className={styles.quickFacts}>
        <div><dt>Star</dt><dd><Star size={13} /> {formatNumber(candidate.totalStars)}</dd></div>
        <div><dt>语言</dt><dd>{candidate.primaryLanguage || '未知'}</dd></div>
        <div><dt>许可证</dt><dd>{candidate.licenseSpdxId || '需验证'}</dd></div>
        <div><dt>更新</dt><dd>{formatDate(candidate.updatedAt)}</dd></div>
      </dl>
      <p className={styles.matchReason}><CheckCircle2 size={14} /> {candidate.preliminaryMatch}</p>
    </article>
  );
}

function AIComparison({ result }: { result: FindProjectResponse }) {
  if (result.aiState === 'unavailable' || result.aiState === 'insufficient_candidates') {
    return (
      <section className={`${styles.aiPanel} ${styles.aiUnavailable}`}>
        <div><AlertTriangle size={16} /><strong>AI 比较暂不可用</strong></div>
        <p>快速候选事实仍可使用。{result.errorCode || '可比较候选不足 3 个'}</p>
      </section>
    );
  }
  if (result.aiState === 'plain') {
    return (
      <section className={styles.aiPanel}>
        <div><Sparkles size={16} /><strong>AI 横向比较 · 有界文本</strong></div>
        <p className={styles.aiPlain}>{result.plainComparison}</p>
      </section>
    );
  }
  if (!result.comparison) return null;
  return (
    <section className={styles.comparisonGrid} aria-label="AI Top 3 横向比较">
      {result.comparison.candidates.map((candidate, index) => (
        <article key={candidate.repository} className={styles.comparisonCard}>
          <div className={styles.comparisonRank}>AI 比较 #{index + 1}</div>
          <h3>{candidate.repository}</h3>
          <span className={styles.reuseBadge}>{REUSE_TYPE_LABELS[candidate.reuseType]}</span>
          <dl>
            <div><dt>项目是做什么的</dt><dd>{candidate.whatItDoes}</dd></div>
            <div><dt>为什么匹配</dt><dd>{candidate.whyMatched}</dd></div>
            <div><dt>可复用内容</dt><dd>{candidate.reusableParts.join('；')}</dd></div>
            <div><dt>集成成本</dt><dd>{costLabel(candidate.integrationCost)}</dd></div>
            <div><dt>主要风险</dt><dd>{candidate.risks.join('；')}</dd></div>
            <div><dt>推荐结论</dt><dd>{candidate.recommendation}</dd></div>
          </dl>
        </article>
      ))}
      <div className={styles.overallConclusion}><Sparkles size={17} /><p><strong>整体结论</strong><br />{result.comparison.overallConclusion}</p></div>
      <small className={styles.aiProvenance}>{result.model || '已配置的 rardar 模型'} · {result.cacheHit ? '缓存命中' : '本次生成'} · AI 不拥有 GitHub 事实</small>
    </section>
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit' }).format(new Date(value));
}

function costLabel(value: 'low' | 'medium' | 'high') {
  return { low: '低', medium: '中', high: '高' }[value];
}
