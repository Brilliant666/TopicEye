import { notFound } from 'next/navigation';
import { Blocks, Construction, DatabaseZap, Radar, SearchCheck, Sparkles } from 'lucide-react';

import { isRardarProduct } from '@/lib/product-profile';
import {
  RARDAR_FOUNDATION_PAGES,
  RARDAR_FOUNDATION_SLOTS,
  type RardarFoundationPageKey,
} from '@/lib/rardar-foundation';
import styles from './RardarFoundation.module.css';

export default function RardarFoundationPage({ pageKey }: { pageKey: RardarFoundationPageKey }) {
  if (!isRardarProduct()) notFound();

  const page = RARDAR_FOUNDATION_PAGES[pageKey];
  if (pageKey === 'today') return <TodayFoundation />;

  return (
    <div className={styles.page} data-rardar-route={page.href}>
      <section className={styles.emptyCard}>
        <div className={styles.emptyContent}>
          <span className={styles.emptyIcon} aria-hidden="true">
            <Construction size={30} />
          </span>
          <p className={styles.eyebrow}>{page.eyebrow}</p>
          <h1>{page.title}</h1>
          <p>{page.description}</p>
          <div className={styles.slotLabel}>{page.slot}</div>
          <p className={styles.nextStep}>{page.nextStep}</p>
        </div>
      </section>
    </div>
  );
}

function TodayFoundation() {
  const today = RARDAR_FOUNDATION_PAGES.today;
  const icons = [Radar, SearchCheck, Sparkles] as const;

  return (
    <div className={styles.page} data-rardar-route="/">
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <p className={styles.eyebrow}>{today.eyebrow}</p>
          <h1 className={styles.heroTitle}>
            把 GitHub 热点变成
            <span className={styles.heroTitleAccent}>可行动的开发情报</span>
          </h1>
          <p className={styles.heroDescription}>
            Rardar 的正式产品壳已经建立。当前不读取 fixture、不调用 AI、不创建数据库记录，
            只为下一阶段经过审计的数据能力保留清晰插槽。
          </p>
          <div className={styles.foundationNotice}>
            <span className={styles.noticePill}>
              <Blocks size={15} aria-hidden="true" /> Product Profile 已启用
            </span>
            <span className={`${styles.noticePill} ${styles.noticePillWarning}`}>
              <DatabaseZap size={15} aria-hidden="true" /> 业务数据尚未接入
            </span>
          </div>
        </div>
      </section>

      <div className={styles.sectionHeading}>
        <div>
          <h2>后续能力插槽</h2>
          <p>每项能力都必须通过独立、可回滚的工程阶段接入。</p>
        </div>
      </div>

      <section className={styles.slotGrid} aria-label="Rardar 后续能力插槽">
        {RARDAR_FOUNDATION_SLOTS.map((slot, index) => {
          const Icon = icons[index];
          return (
            <article key={slot.name} className={styles.slotCard}>
              <span className={styles.slotIcon} aria-hidden="true">
                <Icon size={22} />
              </span>
              <h3>{slot.name}</h3>
              <p>{slot.description}</p>
              <span className={styles.slotStatus}>尚未接入</span>
            </article>
          );
        })}
      </section>

      <div className={styles.sectionHeading}>
        <div>
          <h2>今日</h2>
          <p>没有伪造榜单，也不会用旧 TopicEye 内容代替项目事实。</p>
        </div>
      </div>

      <section className={styles.emptyCard}>
        <div className={styles.emptyContent}>
          <span className={styles.emptyIcon} aria-hidden="true">
            <Radar size={30} />
          </span>
          <h2>{today.title}</h2>
          <p>{today.description}</p>
          <div className={styles.slotLabel}>{today.slot}</div>
          <p className={styles.nextStep}>{today.nextStep}</p>
        </div>
      </section>
    </div>
  );
}
