import Link from 'next/link';
import {
  AlertTriangle,
  ArrowUpRight,
  Clock3,
  MessageCircle,
  Newspaper,
  RadioTower,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';

import {
  type HotspotContentType,
  type HotspotNewsLoadResult,
  type HotspotNewsResponse,
  type HotspotSourceKind,
  type HotspotSourceStatus,
} from '@/lib/rardar-hotspot-news';
import styles from './RardarFoundation.module.css';
import RardarNewsOperations from './RardarNewsOperations';

export default function RardarHotspotNewsPage({ result }: { result: HotspotNewsLoadResult }) {
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
  const quickReadCount = news.items.filter((item) => item.quickRead !== null).length;
  return (
    <div className={`${styles.page} ${styles.newsPage}`} data-rardar-route="/news">
      <NewsHero syncedAt={news.syncedAt} status={news.status} />
      <RardarNewsOperations source={news.selectedSource} topic={news.selectedTopic} sort={news.sort} page={news.page} itemCount={news.itemCount} />

      {news.status === 'degraded' && (
        <section className={styles.newsWarning} role="status">
          <AlertTriangle size={18} aria-hidden="true" />
          部分来源同步失败；以下仍是最近一次成功保存的内容，其他来源和原文入口保持可用。
        </section>
      )}
      {news.status === 'stale' && (
        <section className={styles.newsWarning} role="status">
          <Clock3 size={18} aria-hidden="true" /> 已保存内容超过 24 小时未刷新，管理员可通过资讯更新入口同步。
        </section>
      )}

      <NewsBrowseControls news={news} />

      <div className={styles.newsSectionHeading}>
        <div>
          <h2>{news.sort === 'balanced' ? '综合浏览' : '最新时间线'}</h2>
          <p>{news.sort === 'balanced' ? '在相近时间内分散来源，避免单一高频源连续占屏；不改变文章事实。' : '严格按可依据的文章、更新或讨论时间倒序；这不是全网热度排名。'}</p>
        </div>
        <span>符合条件 {news.totalItems} 条 · 第 {news.page}/{news.totalPages} 页</span>
      </div>

      {news.items.length > 0 ? (
        <section className={styles.newsTimeline} aria-label="热点资讯列表">
          {news.items.map((item) => (
            <article className={styles.newsCard} key={item.url}>
              <div className={styles.newsCardMeta}>
                <span><RadioTower size={13} /> {item.publisherName}</span>
                <b>{item.topicLabel}</b>
                <b>{contentTypeLabel(item.contentType)}</b>
                <time dateTime={item.publishedAt || undefined}>
                  {item.publishedAt ? `发布于 ${formatNewsTime(item.publishedAt)}` : '原始发布时间未知'}
                </time>
                {item.updatedAt && item.updatedAt !== item.publishedAt && (
                  <time dateTime={item.updatedAt}>更新于 {formatNewsTime(item.updatedAt)}</time>
                )}
              </div>
              <h3>{item.quickRead?.titleZh || item.title}</h3>
              {item.quickRead && (
                <span className={styles.newsAiBadge}>AI 中文速读 · {quickReadMaterialLabel(item.quickRead.materialKind)}</span>
              )}
              <p className={(item.quickRead?.summaryZh || item.summary) ? styles.newsSummary : styles.newsSummaryMissing}>
                {item.quickRead?.summaryZh
                  || item.summary
                  || (item.quickRead?.state === 'title_only'
                    ? '目前仅取得标题，未生成超出材料的事件说明；请打开原文核对。'
                    : '来源未提供可验证摘要，请打开原文核对完整内容。')}
              </p>
              {item.quickRead && (
                <details className={styles.newsOriginal}>
                  <summary>查看原始标题与来源摘要</summary>
                  <strong>{item.title}</strong>
                  <p>{item.summary || '来源未提供摘要。'}</p>
                </details>
              )}
              <div className={styles.newsDiscoveries}>
                {item.discoveryChannels.map((channel) => (
                  <span key={channel.key}>
                    经 {channel.name} 发现
                    {channel.rank ? ` · 平台第 ${channel.rank}` : ''}
                    {channel.points !== null ? ` · ${channel.points} points` : ''}
                    {channel.comments !== null ? ` · ${channel.comments} 评论` : ''}
                    {channel.discussionAt ? ` · 讨论于 ${formatNewsTime(channel.discussionAt)}` : ''}
                    {channel.discussionUrl && (
                      <a href={channel.discussionUrl} target="_blank" rel="noreferrer">
                        <MessageCircle size={13} /> 查看讨论
                      </a>
                    )}
                  </span>
                ))}
              </div>
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
            <><RefreshCw size={24} /><div><h2>热点资讯尚未同步</h2><p>管理员点击更新资讯后，这里会读取真实保存结果。</p></div></>
          ) : (
            <><Newspaper size={24} /><div><h2>当前筛选暂无已保存内容</h2><p>这不代表源站没有资讯；可清除筛选或检查来源状态。</p></div></>
          )}
        </section>
      )}

      <NewsPagination news={news} />

      <section className={styles.newsSourcePanel} aria-label="资讯来源状态">
        <div className={styles.newsSourceHeading}>
          <div><p className={styles.eyebrow}>Source health</p><h2>同步与来源状态</h2></div>
          <span><ShieldCheck size={15} /> 页面只读取已保存内容 · 本页 {quickReadCount} 条中文速读</span>
        </div>
        <div className={styles.newsSourceGrid}>
          {news.sources.map((source) => (
            <a key={source.key} href={source.homepageUrl} target="_blank" rel="noreferrer">
              <span>{source.name}<small>{sourceKindLabel(source.kind)}</small></span>
              <i data-status={source.status}>{sourceStatusLabel(source.status)} · {source.itemCount} 条</i>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}

function NewsBrowseControls({ news }: { news: HotspotNewsResponse }) {
  return (
    <section className={styles.newsBrowsePanel} aria-label="资讯浏览方式">
      <div className={styles.newsModeSwitch}>
        <Link aria-current={news.sort === 'balanced' ? 'page' : undefined} href={newsHref(news, { sort: 'balanced', page: 1 })}>综合</Link>
        <Link aria-current={news.sort === 'latest' ? 'page' : undefined} href={newsHref(news, { sort: 'latest', page: 1 })}>最新</Link>
      </div>
      <div className={styles.newsFilterGroup}>
        <strong>来源</strong>
        <div className={styles.newsFilters}>
          <Link aria-current={news.selectedSource === null ? 'page' : undefined} href={newsHref(news, { source: null, page: 1 })}>全部 <span>{news.sourceScopeItemCount}</span></Link>
          {news.sources.map((source) => (
            <Link key={source.key} aria-current={news.selectedSource === source.key ? 'page' : undefined} href={newsHref(news, { source: source.key, page: 1 })}>
              {source.name} <span>{source.itemCount}</span>
            </Link>
          ))}
        </div>
      </div>
      <div className={styles.newsFilterGroup}>
        <strong>主题</strong>
        <div className={styles.newsFilters}>
          <Link aria-current={news.selectedTopic === null ? 'page' : undefined} href={newsHref(news, { topic: null, page: 1 })}>全部 <span>{news.topicScopeItemCount}</span></Link>
          {news.topics.map((topic) => (
            <Link key={topic.key} aria-current={news.selectedTopic === topic.key ? 'page' : undefined} href={newsHref(news, { topic: topic.key, page: 1 })}>
              {topic.label} <span>{topic.itemCount}</span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function NewsPagination({ news }: { news: HotspotNewsResponse }) {
  if (news.totalPages <= 1) return null;
  return (
    <nav className={styles.newsPagination} aria-label="资讯分页">
      {news.page > 1 ? <Link href={newsHref(news, { page: news.page - 1 })}>上一页</Link> : <span>上一页</span>}
      <small>第 {news.page} / {news.totalPages} 页</small>
      {news.page < news.totalPages ? <Link href={newsHref(news, { page: news.page + 1 })}>下一页</Link> : <span>下一页</span>}
    </nav>
  );
}

function newsHref(news: HotspotNewsResponse, changes: { source?: string | null; topic?: string | null; sort?: 'balanced' | 'latest'; page?: number }): string {
  const source = changes.source === undefined ? news.selectedSource : changes.source;
  const topic = changes.topic === undefined ? news.selectedTopic : changes.topic;
  const sort = changes.sort ?? news.sort;
  const page = changes.page ?? news.page;
  const params = new URLSearchParams();
  if (source) params.set('source', source);
  if (topic) params.set('topic', topic);
  if (sort !== 'balanced') params.set('sort', sort);
  if (page > 1) params.set('page', String(page));
  return params.size ? `/news?${params}` : '/news';
}

function NewsHero({ syncedAt, status }: { syncedAt: string | null; status: string }) {
  return (
    <section className={styles.newsHero}>
      <div>
        <p className={styles.eyebrow}>Hotspot News · 多渠道科技资讯</p>
        <h1>先看发生了什么，<span>再回到原始来源。</span></h1>
        <p>汇集官方更新、科技报道与社区讨论，覆盖软件、云与数据、安全、硬件、科研和 AI；按真实时间与发现渠道组织，不伪装成全网统一排名。</p>
      </div>
      <dl>
        <div><dt>同步状态</dt><dd>{newsStatusLabel(status)}</dd></div>
        <div><dt>最近同步</dt><dd>{syncedAt ? formatNewsTime(syncedAt) : '尚未同步'}</dd></div>
        <div><dt>阅读原则</dt><dd>来源可核对 · 时间不补造</dd></div>
      </dl>
    </section>
  );
}

function sourceStatusLabel(status: HotspotSourceStatus): string {
  return { healthy: '正常', stale: '过期', failed: '失败', not_synced: '未同步' }[status];
}

function sourceKindLabel(kind: HotspotSourceKind): string {
  return { official: '官方', media: '科技媒体', community: '社区', aggregate: '聚合' }[kind];
}

function contentTypeLabel(type: HotspotContentType): string {
  return { official_update: '官方更新', report: '报道', research: '研究', community_discussion: '社区讨论', uncategorized: '未分类' }[type];
}

function quickReadMaterialLabel(kind: 'feed_summary' | 'article_body' | 'title_only'): string {
  return { feed_summary: '依据来源摘要', article_body: '依据公开原文', title_only: '仅翻译标题' }[kind];
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
