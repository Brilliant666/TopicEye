export type RardarFoundationPageKey =
  | 'today'
  | 'news'
  | 'activity'
  | 'discover'
  | 'find'
  | 'candidates'
  | 'watchlist';

export interface RardarFoundationPageDefinition {
  key: RardarFoundationPageKey;
  href: string;
  eyebrow: string;
  title: string;
  description: string;
  slot: string;
  nextStep: string;
}

export const RARDAR_FOUNDATION_PAGES: Record<
  RardarFoundationPageKey,
  RardarFoundationPageDefinition
> = {
  today: {
    key: 'today',
    href: '/',
    eyebrow: 'Today · Verified Facts',
    title: 'GitHub 24h 爆发事实',
    description: '优先读取经过 generation、Hash、Schema 与来源版本验证的 Explosion Artifact；本地可显式启用已标记的 Demo。',
    slot: 'Rardar Intelligence Adapter · AI explanation on demand',
    nextStep: '项目 AI 解读已经按需接入，且不会改变客观名次。',
  },
  news: {
    key: 'news',
    href: '/news',
    eyebrow: 'Hotspot News · Source Timeline',
    title: '热点资讯已接入',
    description: '从少量公开技术信源读取已保存的真实事件，按来源时间组织，并保留原文入口。',
    slot: 'TopicEye RSS · Rardar product surface',
    nextStep: '通过显式刷新命令更新；普通页面访问不会抓取源站或调用模型。',
  },
  activity: {
    key: 'activity',
    href: '/activity',
    eyebrow: 'Activity · Foundation',
    title: '动态尚未接入',
    description: '动态内容仍在规划中。目前不采集、不分析、不推送动态，也不会把已暂停的热点资讯移到这里。',
    slot: '后续计划',
    nextStep: '动态保留在后续计划；现在可以继续浏览今日热榜、历史回顾，或按具体需求找项目。',
  },
  discover: {
    key: 'discover',
    href: '/discover',
    eyebrow: 'Discover · Foundation',
    title: '发现能力尚未接入',
    description: '这里将用于多源候选召回与探索；当前不会声称已经扫描整个 GitHub。',
    slot: 'Discovery Adapter',
    nextStep: '后续接入带覆盖说明、来源和降级状态的候选召回结果。',
  },
  find: {
    key: 'find',
    href: '/find',
    eyebrow: 'Find Project · MVP',
    title: '找项目已接入',
    description: '支持自然语言需求、可选公开 GitHub URL、快速候选和 Top 3 AI 横向比较。',
    slot: 'GitHub Search · Rardar LLM route',
    nextStep: '后续可在独立迭代增加持久化 RequirementProfile 和异步深度分析。',
  },
  candidates: {
    key: 'candidates',
    href: '/candidates',
    eyebrow: 'Candidates · Foundation',
    title: '候选池尚未接入',
    description: '当前没有虚构候选、评分或处理进度，只保留正式的信息架构位置。',
    slot: 'Candidate Store',
    nextStep: '后续接入真实召回候选和可审计状态。',
  },
  watchlist: {
    key: 'watchlist',
    href: '/watchlist',
    eyebrow: 'Watchlist · Foundation',
    title: '观察列表尚未接入',
    description: '当前没有读取用户订阅或创建长期跟踪记录，用户数据不会因访问页面而改变。',
    slot: 'Watchlist Service',
    nextStep: '后续在独立数据合同下接入显式订阅和历史观察。',
  },
};

export const RARDAR_FOUNDATION_SLOTS = [
  {
    name: 'Intelligence Adapter',
    description: '版本化事实与页面之间的唯一读取边界。',
  },
  {
    name: 'Find Project Control Plane',
    description: '需求画像、异步 Job 与候选比较的未来插槽。',
  },
  {
    name: 'AI Runtime',
    description: '独立队列、Worker 与本地验证后的 AI 结果插槽。',
  },
] as const;
