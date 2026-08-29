import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Boxes,
  ExternalLink,
  FileSearch,
  Gauge,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
} from 'lucide-react';

import type { ProjectCapability, ProjectDetail } from '@/lib/rardar-intelligence';
import styles from './RardarFoundation.module.css';
import RardarProjectExplanation from './RardarProjectExplanation';

export default function RardarProjectDetailPage({ detail }: { detail: ProjectDetail }) {
  const { project, profile } = detail;
  const relativeGrowth = project.baselineStars > 0 ? project.observedStarDelta / project.baselineStars : null;
  const findHref = `/find?repositoryUrl=${encodeURIComponent(project.htmlUrl)}`;
  const rejected = profile.qualityState === 'rejected';
  const primaryLinks = profile.startHere.slice(0, 4);
  const moreLinks = profile.startHere.slice(4);

  return (
    <div className={`${styles.page} ${styles.detailPage}`} data-rardar-route="/project">
      <nav className={styles.breadcrumb} aria-label="面包屑">
        <Link href="/"><ArrowLeft size={14} /> 今日</Link><span>/</span><span>{project.repository}</span>
      </nav>

      <section className={styles.detailHero} data-testid="project-identity-hero">
        <div className={styles.detailHeroCopy}>
          <div className={styles.detailEyebrow}><ShieldCheck size={15} /> 静态官方档案 · {profile.sourceLabel}</div>
          <h1>{project.repository}</h1>
          <p>{profile.identitySummaryZh}</p>
          {!rejected && (
            <div className={styles.profileSignalGrid} aria-label="项目形态、环境与交付形式">
              <ProfileSignal label="产品形态" values={profile.productFormsZh} />
              <ProfileSignal label="适用环境" values={profile.supportedEnvironmentsZh} />
              <ProfileSignal label="交付形式" values={profile.deliveryFormsZh} />
            </div>
          )}
          <div className={styles.tags}>
            {project.primaryLanguage && <span>{project.primaryLanguage}</span>}
            {project.topics.slice(0, 4).map((topic) => <span key={topic}>{topic}</span>)}
            {project.licenseSpdxId && <span>{project.licenseSpdxId}</span>}
            <span>{qualityLabel(profile.qualityState)}</span>
          </div>
          <div className={styles.detailActions}>
            <a href={project.htmlUrl} target="_blank" rel="noreferrer">打开 GitHub <ArrowUpRight size={15} /></a>
            <Link href={findHref}>用这个仓库评估我的需求 <ArrowRight size={15} /></Link>
          </div>
        </div>
        <dl className={styles.heroFactPair} aria-label="今日核心事实">
          <Fact label="今日排名" value={`#${project.rank}`} />
          <Fact label="24h 新增" value={`+${formatNumber(project.observedStarDelta)}`} accent />
        </dl>
      </section>

      <div className={styles.detailFlow} data-testid="project-detail-flow">
        <section className={styles.detailCoreValue} data-testid="project-core-value">
          <div className={styles.sectionKicker}><Sparkles size={16} /> 核心价值</div>
          {profile.coreValueZh && !rejected ? (
            <>
              <h2>{profile.coreValueZh}</h2>
              {profile.keyDifferentiators.length > 0 && (
                <div className={styles.differentiatorGrid} aria-label="关键差异">
                  {profile.keyDifferentiators.slice(0, 2).map((item) => (
                    <Differentiator key={`${item.title}-${item.detail}`} item={item} />
                  ))}
                </div>
              )}
              <EvidenceBadges values={profile.coreValueEvidenceRefs} />
            </>
          ) : (
            <div className={styles.qualityFallback}>
              <strong>核心价值仍在补证</strong>
              <p>当前只展示已通过质量门禁的项目身份与事实，不用低质量原文填充判断。</p>
            </div>
          )}
        </section>

        {profile.capabilities.length > 0 && !rejected && (
          <DetailSection icon={Boxes} title="它能做什么" subtitle="按采用价值阅读完整能力，而不是浏览等权功能框。">
            <ol className={styles.capabilityNarrative}>
              {profile.capabilities.slice(0, 8).map((capability, index) => (
                <li key={`${capability.title}-${capability.detail}`}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <div><strong>{capability.title}</strong><p>{capability.detail}</p><EvidenceBadges values={capability.evidenceRefs} /></div>
                </li>
              ))}
            </ol>
          </DetailSection>
        )}

        <section className={styles.adoptionLayer} data-testid="rardar-adoption-layer">
          <div className={styles.adoptionIntro}>
            <div className={styles.sectionKicker}><Gauge size={16} /> Rardar 决策与采用</div>
            <h2>从“看懂项目”进入“是否值得复用”</h2>
            <p>AI 只分析差异、可复用资产、成本、适合场景和落地边界；项目身份、官方能力与今日名次不由模型改写。</p>
            {profile.primaryUseCasesZh.length > 0 && (
              <div className={styles.useCaseStrip} aria-label="适合场景">
                <Target size={16} />
                <span>{profile.primaryUseCasesZh.slice(0, 4).join(' · ')}</span>
              </div>
            )}
            <p className={styles.findDecisionHint}>已有明确需求时，可从页面顶部进入 Top 3 横向比较。</p>
          </div>
          <div className={styles.adoptionAction}>
            <RardarProjectExplanation
              repository={project.repository}
              githubRepositoryId={project.githubRepositoryId}
              generationId={detail.generationId}
            />
          </div>
        </section>

        {primaryLinks.length > 0 && (
          <DetailSection icon={FileSearch} title="如何开始" subtitle="先看最有助于理解和采用的四个入口，其余资料按需展开。">
            <div className={styles.startHerePrimary}>
              {primaryLinks.map((item, index) => (
                <a key={item.path} href={item.htmlUrl} target="_blank" rel="noreferrer">
                  <span className={styles.startHereIndex}>{index + 1}</span>
                  <span><strong>{item.label}</strong><small>{startHereReason(item.label)}</small><code>{item.path}</code></span>
                  <ExternalLink size={14} />
                </a>
              ))}
            </div>
            {moreLinks.length > 0 && (
              <details className={styles.moreResources}>
                <summary>更多官方资料（{moreLinks.length}）</summary>
                <div>
                  {moreLinks.map((item) => (
                    <a key={item.path} href={item.htmlUrl} target="_blank" rel="noreferrer">
                      <span>{item.label}</span><code>{item.path}</code><ExternalLink size={13} />
                    </a>
                  ))}
                </div>
              </details>
            )}
          </DetailSection>
        )}

        <section className={styles.observationFacts} data-testid="project-observation-facts">
          <header><Star size={17} /><div><h2>24 小时事实</h2><p>Hero 已给出结果，这里补充基线、窗口与覆盖，不重复名次和增量。</p></div></header>
          <dl>
            <Fact label="基线 Star" value={formatNumber(project.baselineStars)} />
            <Fact label="当前 Star" value={formatNumber(project.totalStars)} />
            <Fact label="相对增长" value={relativeGrowth === null ? '—' : `${(relativeGrowth * 100).toFixed(1)}%`} />
            <Fact label="窗口开始" value={formatTime(project.windowStartedAt)} />
            <Fact label="窗口结束" value={formatTime(project.windowEndedAt)} />
            <Fact label="覆盖状态" value={detail.coverage?.state === 'degraded' ? '部分来源降级' : '覆盖健康'} />
          </dl>
          {detail.coverage?.state === 'degraded' && (
            <p className={styles.coverageNote}>本轮仍按已验证事实排序；{coverageReason(detail.coverage.metadataFailureCount, detail.conflictCount)}。</p>
          )}
        </section>

        <details className={styles.provenanceDetails} data-testid="official-evidence">
          <summary><BookOpen size={16} /> 来源、官方原文与审计 <span>按需查看</span></summary>
          <div className={styles.provenanceDetailsBody}>
            <dl className={styles.sourceFacts}>
              <div><dt>来源</dt><dd>{profile.sourceLabel}</dd></div>
              <div><dt>README</dt><dd>{profile.readmePath || '未取得'}</dd></div>
              <div><dt>Revision</dt><dd><code>{profile.readmeBlobSha || 'GitHub Description'}</code></dd></div>
              <div><dt>翻译状态</dt><dd>{translationLabel(profile.translationState)}</dd></div>
              <div><dt>Profile 质量</dt><dd>{qualityLabel(profile.qualityState)}</dd></div>
              <div><dt>Generation</dt><dd><code>{detail.generationId}</code></dd></div>
              <div><dt>Serving</dt><dd><code>{detail.servingGenerationId}</code></dd></div>
              <div><dt>Evidence</dt><dd><code>{profile.evidenceDigest}</code></dd></div>
            </dl>
            {profile.selectedSections.length > 0 && <p className={styles.sourceSections}>来源章节：{profile.selectedSections.slice(0, 8).map((section) => section.heading).join(' · ')}</p>}
            {profile.originalExcerpts.length > 0 && (
              <div className={styles.officialExcerpts}>
                <h3>官方原文摘录</h3>
                {profile.originalExcerpts.slice(0, 4).map((excerpt) => <blockquote key={excerpt}>{excerpt}</blockquote>)}
              </div>
            )}
            {profile.qualityIssues.length > 0 && <p className={styles.qualityIssues}>质量说明：{profile.qualityIssues.join(' · ')}</p>}
          </div>
        </details>
      </div>
    </div>
  );
}

function ProfileSignal({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null;
  return <div><span>{label}</span><strong>{values.slice(0, 5).join(' · ')}</strong></div>;
}

function Differentiator({ item }: { item: ProjectCapability }) {
  return <article><strong>{item.title}</strong><p>{item.shortDetail || item.detail}</p><EvidenceBadges values={item.evidenceRefs} /></article>;
}

function EvidenceBadges({ values }: { values: string[] }) {
  if (values.length === 0) return null;
  const counts = new Map<string, number>();
  values.forEach((value) => {
    const label = evidenceSourceLabel(value);
    counts.set(label, (counts.get(label) || 0) + 1);
  });
  return <small className={styles.capabilityEvidence}>{Array.from(counts, ([label, count]) => count > 1 ? `${label} · ${count}处证据` : label).join(' · ')}</small>;
}

function evidenceSourceLabel(value: string) {
  if (value === 'description') return 'GitHub Description';
  if (value.startsWith('readme:')) return '官方 README';
  if (value.startsWith('documented-path:')) return 'README 路径';
  if (value.startsWith('path:')) return '仓库目录';
  return '官方仓库证据';
}

function coverageReason(metadataFailures: number, conflicts: number) {
  const reasons = [];
  if (metadataFailures > 0) reasons.push(`${metadataFailures} 个 metadata failure`);
  if (conflicts > 0) reasons.push(`${conflicts} 个负增长冲突`);
  return reasons.length > 0 ? reasons.join('，') : '少量候选来源不可用';
}

function Fact({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div><dt>{label}</dt><dd className={accent ? styles.factAccent : undefined}>{value}</dd></div>;
}

function DetailSection({ icon: Icon, title, subtitle, children }: { icon: typeof BookOpen; title: string; subtitle: string; children: ReactNode }) {
  return <section className={styles.detailSection}><header><span><Icon size={18} /></span><div><h2>{title}</h2><p>{subtitle}</p></div></header><div className={styles.detailSectionBody}>{children}</div></section>;
}

function startHereReason(label: string) {
  if (label.includes('快速开始') || label.includes('安装')) return '先确认安装、运行和最短验证路径';
  if (label.includes('定位') || label.includes('介绍')) return '先建立项目边界与用途认知';
  if (label.includes('能力') || label.includes('特性')) return '核对核心能力是否覆盖你的任务';
  if (label.includes('实现') || label.includes('架构')) return '理解关键机制与工程边界';
  return '查看与采用判断最相关的官方资料';
}

function qualityLabel(value: ProjectDetail['profile']['qualityState']) {
  return { ready: '档案可用', partial: '档案部分可用', rejected: '低质量内容已隔离' }[value];
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value));
}

function translationLabel(value: ProjectDetail['profile']['translationState']) {
  return { not_needed: '官方中文原文', translated: '官方英文内容忠实翻译', pending: '翻译待补全', unavailable: '模型不可用，使用安全降级' }[value];
}
