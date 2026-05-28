'use client';

import React from 'react';
import { useRouter, usePathname } from 'next/navigation';
import {
  BarChart3,
  BookOpen,
  Bookmark,
  BrainCircuit,
  ClipboardList,
  Crosshair,
  GitBranch,
  Flame,
  Lightbulb,
  Newspaper,
  Radar,
  RadioTower,
  Search,
  Star,
  TrendingUp,
  UserRound,
  type LucideIcon,
} from 'lucide-react';
import { cx } from '@/components/ui';

interface SidebarProps {
  topicCount?: number;
  favCount?: number;
  sourceCount?: number;
  compact?: boolean;
}

interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  count?: number;
}

interface NavSpace {
  id: string;
  label: string;
  items: NavItem[];
}

export default function Sidebar({ topicCount = 0, favCount = 0, sourceCount = 0, compact = false }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const navSpaces: NavSpace[] = [
    {
      id: 'discover',
      label: '发现',
      items: [
        { id: 'lfv', label: '低粉爆文', href: '/low-follower-viral', icon: Flame },
        { id: 'trending', label: '趋势雷达', href: '/trending', icon: Search },
        { id: 'trends', label: '趋势追踪', href: '/trends', icon: TrendingUp },
      ],
    },
    {
      id: 'today',
      label: '今日',
      items: [
        { id: 'today', label: '今日选题', href: '/', icon: Lightbulb, count: topicCount },
        { id: 'picks', label: '当日精选', href: '/today-picks', icon: Star },
      ],
    },
    {
      id: 'review',
      label: '复盘',
      items: [
        { id: 'daily', label: '日报', href: '/daily', icon: Newspaper },
        { id: 'weekly', label: '周刊', href: '/weekly', icon: ClipboardList },
        { id: 'stats', label: '数据统计', href: '/stats', icon: BarChart3 },
      ],
    },
    {
      id: 'create',
      label: '创作',
      items: [
        { id: 'my-topics', label: '我的母题', href: '/my-topics', icon: Crosshair },
        { id: 'favorites', label: '收藏夹', href: '/favorites', icon: Bookmark, count: favCount },
        { id: 'algorithm', label: '算法流程', href: '/algorithm', icon: GitBranch },
      ],
    },
    {
      id: 'manage',
      label: '管理',
      items: [
        { id: 'sources', label: '信源管理', href: '/sources', icon: RadioTower, count: sourceCount },
        { id: 'fanqie', label: '网文雷达', href: '/fanqie', icon: BookOpen },
        { id: 'model-eval', label: 'AI 引擎', href: '/model-eval', icon: BrainCircuit },
      ],
    },
  ];

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  return (
    <div
      className="relative flex h-screen shrink-0 select-none flex-col border-r border-gray-200 bg-white"
      style={{ width: compact ? 72 : 220 }}
    >
      {/* Brand */}
      <div className={compact ? 'px-3.5 pb-7 pt-6' : 'px-6 pb-8 pt-7'}>
        <div className={cx('flex items-center gap-2.5', compact ? 'justify-center' : 'justify-start')}>
          <div className="relative h-7 w-7">
            {/* Radar icon */}
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-primary to-[#FF8F65]">
              <Radar size={16} className="text-white" strokeWidth={2.4} />
            </div>
            {/* Ping */}
            <div className="absolute left-0 top-0 h-7 w-7 animate-radar-ping rounded-full border-2 border-primary" />
          </div>
          {!compact && <div>
            <div className="text-[17px] font-bold leading-tight text-gray-900">
              选题雷达
            </div>
            <div className="mt-px text-[10px] tracking-[0.08em] text-gray-400">
              TOPIC RADAR
            </div>
          </div>}
        </div>
      </div>

      {/* Navigation */}
      <nav className={cx('flex-1 overflow-y-auto', compact ? 'px-2.5' : 'px-3')}>
        {navSpaces.map((space) => (
          <div key={space.id} className={compact ? 'mb-3' : 'mb-4.5'}>
            {!compact && (
              <div className="px-3 pb-2 text-[11px] font-bold tracking-[0.08em] text-gray-400">
                {space.label}
              </div>
            )}
            {space.items.map((item) => {
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  title={compact ? item.label : undefined}
                  onClick={() => router.push(item.href)}
                  className={cx(
                    'mb-0.5 flex w-full items-center rounded-sm border-0 text-sm transition',
                    compact ? 'justify-center px-0 py-2.5' : 'justify-between px-3 py-2.5 text-left',
                    active ? 'bg-primary-light font-semibold text-primary' : 'bg-transparent font-normal text-gray-600 hover:bg-gray-50 hover:text-gray-900',
                  )}
                >
                  <span className="flex items-center gap-2">
                    <Icon size={16} strokeWidth={active ? 2.2 : 1.8} />
                    {!compact && <span>{item.label}</span>}
                  </span>
                  {!compact && (item.count ?? 0) > 0 ? (
                    <span className={cx('rounded-full px-2 py-px font-mono text-[11px] font-medium', active ? 'bg-primary/10 text-primary' : 'bg-gray-100 text-gray-400')}>
                      {item.count}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Bottom User Area */}
      <div className={cx('border-t border-gray-100 pb-4 pt-3', compact ? 'px-2.5' : 'px-3')}>
        <div className={cx('flex items-center gap-2', compact ? 'justify-center p-0' : 'justify-start px-3')}>
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-teal to-[#7DD3C0] text-xs font-semibold text-white">
            <UserRound size={14} strokeWidth={2} />
          </div>
          {!compact && <div>
            <div className="text-xs font-medium text-gray-700">创作者</div>
            <div className="text-[10px] text-gray-400">免费版</div>
          </div>}
        </div>
      </div>
    </div>
  );
}
