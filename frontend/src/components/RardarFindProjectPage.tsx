'use client';

import { FormEvent, useEffect, useState } from 'react';
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
const sessionKey = 'rardar-find-last-result-v2';

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
  const [recent, setRecent] = useState<FindProjectResponse[]>([]);

  useEffect(() => {
    if (initialRepositoryUrl || invalidPrefill) return;
    try {
      const raw = sessionStorage.getItem(sessionKey);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (validSavedFindResults(saved)) {
        setRecent(saved.results.slice(0, 3));
        setResult(saved.results[0]);
        setRequirement(saved.results[0].requirement);
        setRepositoryUrl(saved.results[0].repositoryUrl || '');
      } else sessionStorage.removeItem(sessionKey);
    } catch { /* Storage may be unavailable; never issue a request to restore a view. */ }
  }, [initialRepositoryUrl, invalidPrefill]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const next = await findProjects(requirement.trim(), repositoryUrl.trim() || null);
      setResult(next);
      const results = [next, ...recent.filter((item) => item.requirement !== next.requirement || item.repositoryUrl !== next.repositoryUrl)].slice(0, 3);
      setRecent(results);
      try { sessionStorage.setItem(sessionKey, JSON.stringify({ expiresAt: Date.now() + 24 * 60 * 60 * 1000, results })); } catch { /* Reading still works without browser storage. */ }
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
          <p>输入用途、必须条件与排除项，也可附带公开 GitHub 仓库。检索真实候选，再用仓库资料核对需求；不以 Star 排名代替适配判断。</p>
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

      {recent.length > 0 && <section className={styles.aiPanel} aria-label="最近需求结果"><h2>最近需求结果</h2><p>仅在此标签页保留最近三组，最长 24 小时。查看不会重新检索或调用模型。</p>{recent.map((item, index) => <button type="button" className={styles.sourceLine} key={`${item.requirement}-${item.repositoryUrl}`} onClick={() => { setResult(item); setRequirement(item.requirement); setRepositoryUrl(item.repositoryUrl || ''); }}>{index + 1}. {item.requirement}</button>)}</section>}
      {result && <FindResults result={result} />}
      {result && <button type="button" className={styles.sourceLine} onClick={() => { setResult(null); setRecent([]); try { sessionStorage.removeItem(sessionKey); } catch { /* optional storage */ } }}>清除本标签页保存的需求与结果</button>}
    </div>
  );
}

export function FindResults({ result }: { result: FindProjectResponse }) {
  return (
    <div className={styles.findResults}>
      <section className={styles.aiPanel} aria-label="本次需求">
        <h2>本次需求</h2><p>{result.requirement}</p>
        <dl><dt>主要用途</dt><dd>{result.requirementProfile.purpose}</dd><dt>必须满足</dt><dd>{result.requirementProfile.mustHave.join('；') || '未明确'}</dd><dt>偏好</dt><dd>{result.requirementProfile.preferences.join('；') || '未提出'}</dd><dt>明确排除</dt><dd>{result.requirementProfile.exclusions.join('；') || '未提出'}</dd></dl>
      </section>
      <div className={styles.sectionHeading}>
        <div><h2>快速候选 · {result.quickCandidates.length}</h2><p>{result.coverageLabel}</p></div>
        <span className={`${styles.dataState} ${result.searchState === 'github_live' ? styles.dataLive : ''}`}>
          {result.searchState === 'github_live' ? 'GitHub 实时召回' : result.searchState === 'demo' ? '本地演示候选' : 'Limited Mode'}
        </span>
      </div>
      <p className={styles.sourceLine}>来源：{result.sources.join(' · ') || '无可用来源'}。结果不代表扫描了全部 GitHub。</p>
      <details className={styles.sourceLine}><summary>本次公开检索范围</summary><ul>{result.queriedQueries.map((query) => <li key={query}>{query}</li>)}</ul></details>
      <div className={styles.sectionHeading}><div><h2>需求与证据对照 · {result.comparison?.candidates.length || 0} 个重点方案</h2><p>README / 官方静态资料中的声明，不代表功能已实际运行验证。最多三个，不凑数量。</p></div></div>
      <AIComparison result={result} />
      <h2>全部真实召回候选</h2>
      <p className={styles.sourceLine}>未深入分析的候选不是已验证不合适；Star 仅作背景信息。</p>
      <section className={styles.quickGrid} aria-label="找项目快速候选">
        {result.quickCandidates.map((candidate) => <QuickCandidateCard key={`${candidate.dataState}-${candidate.githubRepositoryId}`} candidate={candidate} />)}
      </section>

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
      <p>{candidate.isProvided ? '你提供的仓库（不代表优先推荐）' : '本次检索候选'} · {candidate.evidenceState === 'ready' ? '已取得静态资料' : candidate.evidenceState === 'metadata_only' ? '仅元数据，能力待确认' : '尚未深入分析'}</p>
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
  if (result.aiState === 'unavailable' || result.aiState === 'insufficient_candidates' || result.aiState === 'plain') {
    return (
      <section className={`${styles.aiPanel} ${styles.aiUnavailable}`}>
        <div><AlertTriangle size={16} /><strong>AI 比较暂不可用</strong></div>
        <p>真实候选与原文入口仍可使用；目前没有足够依据形成推荐。{result.errorCode || '暂无可靠匹配资料'}</p>
      </section>
    );
  }
  if (!result.comparison) return null;
  return (
    <section className={styles.comparisonGrid} aria-label="需求与证据对照">
      {result.comparison.candidates.length === 0 && <p>本次没有找到足够依据的重点方案。可继续核对下方真实候选。</p>}
      {result.comparison.candidates.map((candidate, index) => (
        <article key={candidate.repository} className={styles.comparisonCard}>
          <div className={styles.comparisonRank}>AI 比较 #{index + 1}</div>
          <h3>{candidate.repository}</h3>
          <p>{result.quickCandidates.find((item) => item.repository === candidate.repository)?.isProvided ? '你提供的仓库' : result.repositoryUrl ? '本次检索的替代方案' : '本次检索方案'}</p>
          <span className={styles.reuseBadge}>{REUSE_TYPE_LABELS[candidate.reuseType]}</span>
          <dl>
            <div><dt>项目是做什么的</dt><dd>{candidate.whatItDoes}</dd></div>
            <div><dt>为什么匹配</dt><dd>{candidate.whyMatched}</dd></div>
            <div><dt>可复用内容</dt><dd>{candidate.reusableParts.join('；') || '尚未确认'}</dd></div>
            <div><dt>集成成本</dt><dd>{costLabel(candidate.integrationCost)}</dd></div>
            <div><dt>主要风险</dt><dd>{candidate.risks.join('；') || '资料未确认额外风险，不代表无风险'}</dd></div>
            <div><dt>推荐结论</dt><dd>{candidate.recommendation}</dd></div>
          </dl>
          <h4>逐项需求</h4>
          {candidate.requirementChecks.map((check, index) => <div key={`${index}-${check.requirement}`}><strong>{check.requirement} · {{ supported: '资料支持', not_supported: '资料表明不满足', unknown: '尚未确认' }[check.status]}</strong><p>{check.reason}</p>{check.supportingQuote && <blockquote>资料原句：{check.supportingQuote}</blockquote>}<EvidenceLinks refs={check.evidenceRefs} repository={candidate.repository} result={result} /></div>)}
          <EvidenceLinks refs={candidate.evidenceRefs} repository={candidate.repository} result={result} />
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

function EvidenceLinks({ refs, repository, result }: { refs: string[]; repository: string; result: FindProjectResponse }) {
  return <ul>{refs.map((ref) => { const source = result.evidenceSources.find((item) => item.ref === ref && item.repository === repository); if (!source || !/^https:\/\//.test(source.url)) return null; return <li key={ref}><a href={source.url} target="_blank" rel="noreferrer">核对资料：{source.kind} ↗</a><details><summary>查看取得的材料</summary><p>{source.text}</p></details></li>; })}</ul>;
}

export function validSavedFindResults(value: unknown): value is { expiresAt: number; results: FindProjectResponse[] } {
  const record = (item: unknown): item is Record<string, unknown> => typeof item === 'object' && item !== null && !Array.isArray(item);
  const strings = (item: unknown): item is string[] => Array.isArray(item) && item.length <= 100 && item.every((entry) => typeof entry === 'string');
  if (!record(value) || typeof value.expiresAt !== 'number' || value.expiresAt <= Date.now() || value.expiresAt > Date.now() + 86400000 || !Array.isArray(value.results) || value.results.length < 1 || value.results.length > 3) return false;
  return value.results.every((item) => {
    if (!record(item) || typeof item.requirement !== 'string' || (item.repositoryUrl !== null && typeof item.repositoryUrl !== 'string') || typeof item.coverageLabel !== 'string' || !strings(item.sources) || !strings(item.queriedQueries)) return false;
    const profile = item.requirementProfile;
    if (!record(profile) || typeof profile.purpose !== 'string' || !['mustHave', 'preferences', 'exclusions', 'queries'].every((key) => strings(profile[key]))) return false;
    if (!Array.isArray(item.quickCandidates) || item.quickCandidates.length > 100 || !item.quickCandidates.every((candidate) => record(candidate) && ['repository', 'htmlUrl', 'preliminaryMatch', 'updatedAt'].every((key) => typeof candidate[key] === 'string') && Number.isFinite(Date.parse(candidate.updatedAt as string)) && typeof candidate.totalStars === 'number' && typeof candidate.githubRepositoryId === 'number' && ['description', 'primaryLanguage', 'licenseSpdxId'].every((key) => candidate[key] === null || typeof candidate[key] === 'string'))) return false;
    if (!Array.isArray(item.evidenceSources) || item.evidenceSources.length > 100 || !item.evidenceSources.every((source) => record(source) && ['repository', 'ref', 'url', 'text', 'kind'].every((key) => typeof source[key] === 'string'))) return false;
    if (!['ready', 'unavailable', 'insufficient_candidates', 'plain'].includes(String(item.aiState)) || !['github_live', 'limited', 'demo'].includes(String(item.searchState))) return false;
    if (!['errorCode', 'model', 'provider', 'plainComparison'].every((key) => item[key] === null || typeof item[key] === 'string')) return false;
    if (item.comparison === null) return true;
    const comparison = item.comparison;
    return record(comparison) && typeof comparison.overallConclusion === 'string' && Array.isArray(comparison.candidates) && comparison.candidates.length <= 3 && comparison.candidates.every((candidate) => record(candidate)
      && ['repository', 'whatItDoes', 'whyMatched', 'recommendation'].every((key) => typeof candidate[key] === 'string')
      && typeof candidate.reuseType === 'string' && Object.hasOwn(REUSE_TYPE_LABELS, candidate.reuseType)
      && ['low', 'medium', 'high', 'unknown'].includes(String(candidate.integrationCost))
      && strings(candidate.reusableParts) && strings(candidate.risks) && strings(candidate.evidenceRefs)
      && Array.isArray(candidate.requirementChecks) && candidate.requirementChecks.length <= 100 && candidate.requirementChecks.every((check) => record(check) && typeof check.requirement === 'string' && typeof check.reason === 'string' && ['supported', 'not_supported', 'unknown'].includes(String(check.status)) && strings(check.evidenceRefs) && (check.supportingQuote === undefined || typeof check.supportingQuote === 'string')));
  });
}

function costLabel(value: 'low' | 'medium' | 'high' | 'unknown') {
  return { low: '低', medium: '中', high: '高', unknown: '未知，需实际验证' }[value];
}
