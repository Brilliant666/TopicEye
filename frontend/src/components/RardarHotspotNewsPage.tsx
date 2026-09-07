'use client';

import { useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  Clock3,
  Newspaper,
  RadioTower,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

import {
  filterHotspotNews,
  type HotspotNewsLoadResult,
  type HotspotSourceStatus,
} from '@/lib/rardar-hotspot-news';
import styles from './RardarFoundation.module.css';

export default function RardarHotspotNewsPage({ result }: { result: HotspotNewsLoadResult }) {
  const [sourceKey, setSourceKey] = useState<string | null>(null);

  if (result.kind === 'error') {
    return (
      <div className={`${styles.page} ${styles.newsPage}`} data-rardar-route="/news">
        <NewsHero syncedAt={null} status="unavailable" />
        <section className={styles.newsFailure} role="status">
          <AlertTriangle size={22} aria-hidden="true" />
          <div><h2>已保存的资讯暂时无法读取</h2><p>没有把读取失败伪装成空列表 · {result.code}</p></div>
        </section>
      </div>
    );
  }

  const news = result.news;
  const visibleItems = filterHotspotNews(news.items, sourceKey);
  return (
    <div className={`${styles.page} ${styles.newsPage}`} data-rardar-route="/news">
      <NewsHero syncedAt={news.syncedAt} status={news.status} />

      <section className={styles.newsSourcePanel} aria-label="资讯来源状态">
        <div className={styles.newsSourceHeading}>
          <div>
            <p className={styles.eyebrow}>Sources</p>
            <h2>公开技术信源</h2>
          </div>
          <span><ShieldCheck size={15} /> 页面只读取已保存内容 · 0 次模型调用</span>
        </div>
        <div className={styles.newsFilters} aria-label="按来源筛选">
          <button type="button" aria-pressed={sourceKey === null} onClick={() => setSourceKey(null)}>
            全部 <span>{news.items.length}</span>
          </button>
          {news.sources.map((source) => (
            <button
              type="button"
              key={source.key}
              aria-pressed={sourceKey === source.key}
              onClick={() => setSourceKey(source.key)}
            >
              {source.name} <span>{source.itemCount}</span>
              <i data-status={source.status}>{sourceStatusLabel(source.status)}</i>
            </button>
          ))}
        </div>
      </section>

      {news.status === 'degraded' && (
        <section className={styles.newsWarning} role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          部分来源同步失败；以下仍是最近一次成功保存的内容，原文入口保持可用。
        </section>
      )}
      {news.status === 'stale' && (
        <section className={styles.newsWarning} role="status">
          <Clock3 size={18} aria-hidden="true" /> 已保存内容超过 24 小时未刷新，请显式运行资讯刷新命令。
        </section>
      )}

      <div className={styles.newsSectionHeading}>
        <div><h2>技术资讯时间线</h2><p>按原始发布时间或更新时间组织；这不是“全网最热”排名。</p></div>
        <span>{sourceKey ? `筛选后 ${visibleItems.length} 条` : `已保存 ${news.items.length} 条`}</span>
      </div>

      {visibleItems.length > 0 ? (
        <section className={styles.newsTimeline} aria-label="热点资讯列表">
          {visibleItems.map((item) => (
            <article className={styles.newsCard} key={item.url}>
              <div className={styles.newsCardMeta}>
                <span><RadioTower size={13} /> {item.sourceName}</span>
                <time dateTime={item.publishedAt || undefined}>
                  {item.publishedAt ? `发布于 ${formatNewsTime(item.publishedAt)}` : '发布时间未知'}
                </time>
                {item.updatedAt && item.updatedAt !== item.publishedAt && (
                  <time dateTime={item.updatedAt}>更新于 {formatNewsTime(item.updatedAt)}</time>
                )}
              </div>
              <h3>{item.title}</h3>
              <p className={item.summary ? styles.newsSummary : styles.newsSummaryMissing}>
                {item.summary || 'Feed 未提供可验证摘要，请打开原文核对完整内容。'}
              </p>
              <footer>
                <small>获取于 {formatNewsTime(item.fetchedAt)}</small>
                <a href={item.url} target="_blank" rel="noreferrer">
                  阅读原文 <ArrowUpRight size={15} aria-hidden="true" />
                </a>
              </footer>
            </article>
          ))}
        </section>
      ) : (
        <section className={styles.newsEmpty} role="status">
          {result.kind === 'not_synced' ? (
            <><RefreshCw size={24} /><div><h2>热点资讯尚未同步</h2><p>运行本地 refresh-news 命令后，这里会读取真实保存结果。</p></div></>
          ) : (
            <><Newspaper size={24} /><div><h2>该来源暂无已保存内容</h2><p>这不代表源站没有资讯；请检查来源状态或稍后刷新。</p></div></>
          )}
        </section>
      )}
    </div>
  );
}

function NewsHero({ syncedAt, status }: { syncedAt: string | null; status: string }) {
  return (
    <section className={styles.newsHero}>
      <div>
        <p className={styles.eyebrow}>Hotspot News · Verified Sources</p>
        <h1>发生了什么，<span>从原始来源开始。</span></h1>
        <p>聚合少量公开技术信源的真实更新，用 Feed 内容快速理解变化，并保留可核对的原文入口。英文条目首版保留原文，尚未调用模型翻译。</p>
      </div>
      <dl>
        <div><dt>同步状态</dt><dd>{newsStatusLabel(status)}</dd></div>
        <div><dt>最近同步</dt><dd>{syncedAt ? formatNewsTime(syncedAt) : '尚未同步'}</dd></div>
        <div><dt>内容处理</dt><dd>Feed 原文摘要 · 未调用 AI</dd></div>
      </dl>
    </section>
  );
}

function sourceStatusLabel(status: HotspotSourceStatus): string {
  return { healthy: '正常', stale: '过期', failed: '失败', not_synced: '未同步' }[status];
}

function newsStatusLabel(status: string): string {
  return { ready: '已更新', degraded: '部分降级', stale: '需要刷新', not_synced: '未同步', unavailable: '不可用' }[status] || status;
}

function formatNewsTime(value: string): string {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '时间未知';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}
