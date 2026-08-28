import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Boxes,
  Braces,
  ExternalLink,
  FileSearch,
  GitFork,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
} from 'lucide-react';

import type { ProjectDetail } from '@/lib/rardar-intelligence';
import styles from './RardarFoundation.module.css';
import RardarProjectExplanation from './RardarProjectExplanation';

export default function RardarProjectDetailPage({ detail }: { detail: ProjectDetail }) {
  const { project, profile } = detail;
  const relativeGrowth = project.baselineStars > 0 ? project.observedStarDelta / project.baselineStars : null;
  const findHref = `/find?repositoryUrl=${encodeURIComponent(project.htmlUrl)}`;

  return (
    <div className={`${styles.page} ${styles.detailPage}`} data-rardar-route="/project">
      <nav className={styles.breadcrumb} aria-label="面包屑">
        <Link href="/"><ArrowLeft size={14} /> 今日</Link><span>/</span><span>{project.repository}</span>
      </nav>

      <section className={styles.detailHero}>
        <div className={styles.detailHeroCopy}>
          <div className={styles.detailEyebrow}><ShieldCheck size={15} /> 静态官方档案 · {profile.sourceLabel}</div>
          <h1>{project.repository}</h1>
          <p>{profile.officialSummaryZh}</p>
          <div className={styles.tags}>
            {project.primaryLanguage && <span>{project.primaryLanguage}</span>}
            {project.topics.slice(0, 5).map((topic) => <span key={topic}>{topic}</span>)}
            {project.licenseSpdxId && <span>{project.licenseSpdxId}</span>}
            <span>{profile.profileState === 'complete' ? '档案完整' : profile.profileState === 'partial' ? '档案部分可用' : '官方来源有限'}</span>
          </div>
          <div className={styles.detailActions}>
            <a href={project.htmlUrl} target="_blank" rel="noreferrer">打开 GitHub <ArrowUpRight size={15} /></a>
            <Link href={findHref}>用这个仓库评估我的需求 <ArrowRight size={15} /></Link>
          </div>
        </div>
        <dl className={styles.detailFactGrid}>
          <Fact label="今日排名" value={`#${project.rank}`} />
          <Fact label="24h 新增" value={`+${formatNumber(project.observedStarDelta)}`} accent />
          <Fact label="总 Star" value={formatNumber(project.totalStars)} />
          <Fact label="相对增长" value={relativeGrowth === null ? '—' : `${(relativeGrowth * 100).toFixed(1)}%`} />
        </dl>
      </section>

      <div className={styles.detailColumns}>
        <main className={styles.detailMain}>
          <DetailSection icon={BookOpen} title="这个项目是什么" subtitle="官方 README / Description 的可验证整理，不含榜单热度判断。">
            <p className={styles.detailLead}>{profile.officialSummaryZh}</p>
            <dl className={styles.sourceFacts}>
              <div><dt>来源</dt><dd>{profile.sourceLabel}</dd></div>
              <div><dt>README</dt><dd>{profile.readmePath || '未取得'}</dd></div>
              <div><dt>Revision</dt><dd><code>{profile.readmeBlobSha || 'GitHub Description'}</code></dd></div>
              <div><dt>翻译状态</dt><dd>{translationLabel(profile.translationState)}</dd></div>
            </dl>
            {profile.originalExcerpts.length > 0 && (
              <div className={styles.officialExcerpts}>
                <h3>官方原文摘录</h3>
                {profile.originalExcerpts.slice(0, 4).map((excerpt) => <blockquote key={excerpt}>{excerpt}</blockquote>)}
              </div>
            )}
          </DetailSection>

          {profile.capabilityBulletsZh.length > 0 && (
            <DetailSection icon={Boxes} title="核心能力" subtitle="每项来自已保存的官方证据。">
              <ul className={styles.detailBulletGrid}>
                {profile.capabilityBulletsZh.map((capability) => <li key={capability}>{capability}</li>)}
              </ul>
            </DetailSection>
          )}

          {profile.primaryUseCasesZh.length > 0 && (
            <DetailSection icon={Target} title="适合解决什么" subtitle="官方资料明确描述的使用场景。">
              <ul className={styles.detailBulletGrid}>
                {profile.primaryUseCasesZh.map((useCase) => <li key={useCase}>{useCase}</li>)}
              </ul>
            </DetailSection>
          )}

          {profile.startHere.length > 0 && (
            <DetailSection icon={FileSearch} title="建议先看" subtitle="全部链接都来自这份 Serving Projection 保存的真实 README、文件或目录。">
              <div className={styles.startHereGrid}>
                {profile.startHere.map((item) => (
                  <a key={item.path} href={item.htmlUrl} target="_blank" rel="noreferrer">
                    <span>{item.label}</span><code>{item.path}</code><ExternalLink size={14} />
                  </a>
                ))}
              </div>
            </DetailSection>
          )}

          <DetailSection icon={Sparkles} title="AI 深度解读" subtitle="按需调用已配置的 rardar 模型，只使用上面的静态证据；失败不会影响官方档案。">
            <RardarProjectExplanation
              repository={project.repository}
              githubRepositoryId={project.githubRepositoryId}
              generationId={detail.generationId}
            />
          </DetailSection>
        </main>

        <aside className={styles.detailAside}>
          <section className={styles.todayReason}>
            <h2><Star size={17} /> 今日为什么出现在这里</h2>
            <p>这里只解释客观入榜事实，AI 不参与名次。</p>
            <dl>
              <div><dt>精确排名</dt><dd>#{project.rank}</dd></div>
              <div><dt>基线 Star</dt><dd>{formatNumber(project.baselineStars)}</dd></div>
              <div><dt>当前 Star</dt><dd>{formatNumber(project.totalStars)}</dd></div>
              <div><dt>观测增量</dt><dd>+{formatNumber(project.observedStarDelta)}</dd></div>
              <div><dt>窗口开始</dt><dd>{formatTime(project.windowStartedAt)}</dd></div>
              <div><dt>窗口结束</dt><dd>{formatTime(project.windowEndedAt)}</dd></div>
            </dl>
          </section>
          <section className={styles.generationCard}>
            <h2><Braces size={17} /> 快照来源</h2>
            <p>详情与榜单绑定同一个 immutable generation。</p>
            <code>{detail.generationId}</code>
            <small>Serving {detail.servingGenerationId}</small>
            <span title={profile.evidenceDigest}>Evidence {profile.evidenceDigest.slice(0, 12)}</span>
          </section>
          <Link className={styles.detailFindCta} href={findHref}>
            <GitFork size={18} />
            <span><strong>用这个仓库评估我的需求</strong><small>进入现有 Find Project 双输入流程</small></span>
            <ArrowRight size={16} />
          </Link>
        </aside>
      </div>
    </div>
  );
}

function Fact({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return <div><dt>{label}</dt><dd className={accent ? styles.factAccent : undefined}>{value}</dd></div>;
}

function DetailSection({ icon: Icon, title, subtitle, children }: { icon: typeof BookOpen; title: string; subtitle: string; children: ReactNode }) {
  return (
    <section className={styles.detailSection}>
      <header><span><Icon size={18} /></span><div><h2>{title}</h2><p>{subtitle}</p></div></header>
      <div className={styles.detailSectionBody}>{children}</div>
    </section>
  );
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
  return { not_needed: '官方中文原文', translated: '官方英文内容忠实翻译', pending: '翻译待补全', unavailable: '模型不可用，保留官方原文' }[value];
}
