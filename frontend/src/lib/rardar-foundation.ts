export type RardarFoundationPageKey =
  | 'today'
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
    description: '只读取经过 generation、Hash、Schema 与来源版本验证的 Explosion Artifact。',
    slot: 'Rardar Intelligence Adapter · Read-only',
    nextStep: '后续独立阶段接入 AI 项目解释，不改变客观名次。',
  },
  activity: {
    key: 'activity',
    href: '/activity',
    eyebrow: 'Activity · Foundation',
    title: '动态信号尚未接入',
    description: '这里将承接可追溯的 GitHub、社区与时事信号；Foundation 不模拟信号流。',
    slot: 'Signal Intelligence Adapter',
    nextStep: '后续从正式 Signal contract 读取审计过的动态事实。',
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
    eyebrow: 'Find Project · Foundation',
    title: '找项目控制面尚未接入',
    description: '当前没有发送请求、创建 Job 或展示模拟候选；输入与异步状态将在独立阶段实现。',
    slot: 'Find Project Control Plane',
    nextStep: '后续接入 RequirementProfile、durable Job 与有证据的候选比较。',
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
