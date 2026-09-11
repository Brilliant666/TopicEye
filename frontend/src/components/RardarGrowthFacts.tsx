import { Star } from 'lucide-react';
import { boardTime, type TrendingProject } from '@/lib/rardar-trending';
import styles from './RardarFoundation.module.css';

export const growthSourceLabel = { github: 'GitHub Trending', trendshift: 'Trendshift', rardar_history: 'Rardar 历史观测' };

/** The API chooses the same primary metric used by the full-list ordering. */
export default function RardarGrowthFacts({ project, historical = false }: { project: TrendingProject; historical?: boolean }) {
  const item = project.primaryGrowth;
  return <div className={`${styles.starFacts} ${styles.sourceGrowthFacts}`} aria-label={historical ? '历史来源增长' : '来源报告增长'}>
    {item ? <div className={styles.sourceGrowthMetric} data-growth-source={item.source} data-growth-value={item.value}>
      <span className={styles.growthSourceLabel}>{historical ? '历史 Star 增长' : 'Star 增长'} · {growthSourceLabel[item.source]}</span>
      <strong>{item.value >= 0 ? '+' : ''}{item.value.toLocaleString()}</strong>
      {item.sourceStatus && item.sourceStatus !== 'healthy' && <small>保留缓存 · 采集 {boardTime(item.fetchedAt)}</small>}
    </div> : <span className={styles.growthUnavailable}>增长暂未取得</span>}
    <span className={styles.totalStarsAuxiliary}><Star size={14} aria-hidden="true" />{typeof project.totalStars === 'number' ? `${project.totalStars.toLocaleString()} 累计 Star` : '累计 Star 未取得'}</span>
  </div>;
}
