import { Star } from 'lucide-react';
import { boardTime, latestBoardAppearances, type BoardAppearance, type TrendingProject } from '@/lib/rardar-trending';
import styles from './RardarFoundation.module.css';

export const growthSourceLabel = { github: 'GitHub Trending', trendshift: 'Trendshift' };
const sourceState = { healthy: '', stale: '历史缓存', failed: '来源失败 · 保留缓存' };
const knownPeriods: Record<string, string> = { 'GitHub reported stars today': '来源报告 stars today', 'Trendshift daily (source-defined window)': '来源日榜周期，具体起止未提供', daily: '来源日榜周期' };

function growthValue(appearance: BoardAppearance) {
  const value = appearance.source === 'github' ? appearance.reportedDelta : appearance.trendshiftStarsGained;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function metricPeriod(appearance: BoardAppearance) {
  const period = appearance.source === 'github' ? appearance.reportedDeltaPeriod : appearance.trendshiftMetricPeriod;
  return period ? knownPeriods[period] || period : '统计起止时间未提供';
}

function displayGrowth(appearance: BoardAppearance) {
  const value = growthValue(appearance)!;
  // Trendshift's integer comes from repository_stars_gained, independently of its visible abbreviated label.
  return `${value >= 0 ? '+' : ''}${value.toLocaleString()}`;
}

/** Both list and detail preserve source-specific growth; no synthetic aggregate or baseline. */
export default function RardarGrowthFacts({ project, historical = false }: { project: TrendingProject; historical?: boolean }) {
  const appearances = latestBoardAppearances(project.appearances);
  const available = appearances.filter(item => growthValue(item) !== null);
  const original = !appearances.length && historical
    ? [...(project.historicalRardarEvidence || [])].sort((a, b) => Date.parse(b.windowEndedAt) - Date.parse(a.windowEndedAt))[0]
    : null;
  const totalSource = project.totalStarsSource;
  return <div className={`${styles.starFacts} ${styles.sourceGrowthFacts}`} aria-label={historical ? '历史来源增长' : '来源报告增长'}>
    {available.map(item => <div className={styles.sourceGrowthMetric} key={item.source} data-growth-source={item.source} data-growth-value={growthValue(item)} title={item.source === 'trendshift' && item.trendshiftStarsGainedLabel ? `来源页面原标签：${item.trendshiftStarsGainedLabel}` : undefined}>
      <span className={styles.growthSourceLabel}>{historical ? '历史 · ' : ''}{growthSourceLabel[item.source]}{item.sourceStatus && sourceState[item.sourceStatus] ? ` · ${sourceState[item.sourceStatus]}` : ''}</span>
      <strong>{displayGrowth(item)}</strong>
      <small>来源报告 Star 增长 · {metricPeriod(item)}</small>
      <small>{historical ? '历史榜日期' : '榜单日期'} {boardTime(item.sourceDate)} · 采集 {boardTime(item.fetchedAt)}</small>
    </div>)}
    {original && <div className={styles.sourceGrowthMetric} data-growth-source="rardar_history" data-growth-value={original.observedStarDelta}>
      <span className={styles.growthSourceLabel}>Rardar 历史观测</span><strong>{original.observedStarDelta >= 0 ? '+' : ''}{original.observedStarDelta.toLocaleString()}</strong>
      <small>历史窗口 {boardTime(original.windowStartedAt)} → {boardTime(original.windowEndedAt)}</small>
    </div>}
    {available.length === 0 && !original && <span className={styles.growthUnavailable}>来源增长未取得</span>}
    {appearances.filter(item => growthValue(item) === null).map(item => <small key={item.source}>{growthSourceLabel[item.source]}：增长未取得{historical ? '（历史）' : ''}</small>)}
    <span className={styles.totalStarsAuxiliary}><Star size={14} aria-hidden="true" />{typeof project.totalStars === 'number' ? `${project.totalStars.toLocaleString()} 累计 Star` : '累计 Star 未取得'}</span>
    {totalSource ? <small>累计来源 {growthSourceLabel[totalSource.source]}{sourceState[totalSource.status] ? ` · ${sourceState[totalSource.status]}` : ''} · 源榜 {boardTime(totalSource.sourceDate)} · 采集 {boardTime(totalSource.fetchedAt)}</small>
      : original ? <small>累计为历史窗口结束时的保存值</small> : <small>累计值来源时间未记录</small>}
  </div>;
}
