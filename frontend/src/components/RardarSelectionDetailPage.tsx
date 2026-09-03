import Link from 'next/link';
import { ArrowLeft, ArrowRight, ArrowUpRight, BookOpenCheck, Braces, FolderGit2, ShieldCheck } from 'lucide-react';

import type { SelectionProjectDetail, SelectionReason } from '@/lib/rardar-selection';
import styles from './RardarFoundation.module.css';

export default function RardarSelectionDetailPage({ detail }: { detail: SelectionProjectDetail }) {
  const { context } = detail;
  const { card } = context;
  const profile = context.canonicalProfile;
  const capabilities = records(profile.capabilities).slice(0, 6);
  const startHere = records(profile.startHere).slice(0, 6);

  return (
    <div className={`${styles.page} ${styles.selectionDetailPage}`} data-rardar-route="/discover/project">
      <Link href="/discover" className={styles.selectionBack}><ArrowLeft size={15} /> 返回值得看</Link>
      <section className={styles.selectionDetailHero}>
        <div>
          <div className={styles.selectionCardTopline}>
            <span>{reasonLabel(card.primaryReason)}</span>
            <span>Selection context v1</span>
          </div>
          <h1><FolderGit2 size={26} /> {card.repository}</h1>
          <p className={styles.selectionIdentity}>{card.identitySummaryZh}</p>
          <div className={styles.selectionTags}>
            {card.productFormsZh.map((item) => <span key={item}>{item}</span>)}
            {card.primaryLanguage && <span>{card.primaryLanguage}</span>}
            {card.licenseSpdxId && <span>{card.licenseSpdxId}</span>}
          </div>
        </div>
        <div className={styles.selectionDetailActions}>
          <a href={card.htmlUrl} target="_blank" rel="noreferrer">打开 GitHub <ArrowUpRight size={15} /></a>
          <Link href={`/find?repositoryUrl=${encodeURIComponent(card.htmlUrl)}`}>用它评估我的需求 <ArrowRight size={15} /></Link>
        </div>
      </section>

      <section className={styles.selectionDetailDecision}>
        <div><BookOpenCheck size={20} /><span>为什么值得看</span><p>{card.whyWorthSeeingZh}</p></div>
        <div><ShieldCheck size={20} /><span>为什么是现在</span><p>{card.whyNowZh || '长期价值成立，但当前没有足够强的“为什么是现在”证据。'}</p></div>
      </section>

      {(card.reusableAssets.length > 0 || card.bestFit.length > 0) && (
        <section className={styles.selectionDetailSection}>
          <header><div><BookOpenCheck size={19} /><div><p>Selection context</p><h2>可复用资产与适合场景</h2></div></div></header>
          <div className={styles.selectionCapabilityGrid}>
            {card.reusableAssets.map((item) => <article key={`asset-${item}`}><strong>可复用资产</strong><p>{item}</p></article>)}
            {card.bestFit.map((item) => <article key={`fit-${item}`}><strong>适合场景</strong><p>{item}</p></article>)}
          </div>
        </section>
      )}

      <section className={styles.selectionDetailSection}>
        <header><div><Braces size={19} /><div><p>Canonical Project Profile</p><h2>关键能力与可复用入口</h2></div></div></header>
        {capabilities.length > 0 ? (
          <div className={styles.selectionCapabilityGrid}>
            {capabilities.map((item, index) => (
              <article key={`${text(item.title)}-${index}`}><strong>{text(item.title) || `能力 ${index + 1}`}</strong><p>{text(item.detail)}</p></article>
            ))}
          </div>
        ) : <p className={styles.selectionMuted}>当前 Canonical Profile 没有可发布的结构化能力，不会在详情页补造。</p>}
        {startHere.length > 0 && (
          <div className={styles.selectionStartHere}>
            <h3>从这里开始</h3>
            {startHere.map((item, index) => {
              const href = text(item.htmlUrl);
              return href ? <a key={`${href}-${index}`} href={href} target="_blank" rel="noreferrer"><span>{text(item.label) || '项目资料'}</span><code>{text(item.path)}</code><ArrowUpRight size={13} /></a> : null;
            })}
          </div>
        )}
      </section>

      <details className={styles.selectionEvidencePanel}>
        <summary>查看 Selection 证据与版本边界 <span>{context.evidence.length} 条</span></summary>
        <div>
          {context.evidence.map((item) => (
            <article key={item.evidenceId}><strong>{item.evidenceId} · {item.sourceType}</strong><p>{item.excerpt}</p><code>{item.sourcePath} @ {item.sourceRevision}</code></article>
          ))}
          <dl>
            <div><dt>Selection Generation</dt><dd><code>{detail.selectionGenerationId}</code></dd></div>
            <div><dt>Observation Source</dt><dd><code>{detail.sourceObservationSetId}</code></dd></div>
            <div><dt>Generated at</dt><dd><code>{context.generatedAt}</code></dd></div>
            <div><dt>Evidence digest</dt><dd><code>{context.selectionEvidenceDigest}</code></dd></div>
          </dl>
        </div>
      </details>
    </div>
  );
}

function records(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => (
    typeof item === 'object' && item !== null && !Array.isArray(item)
  )) : [];
}

function text(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function reasonLabel(value: SelectionReason) {
  return {
    directly_reusable: '可直接复用',
    specific_problem_solution: '解决具体问题',
    distinctive_implementation: '实现有辨识度',
    reference_or_learning_value: '参考与学习',
  }[value];
}
