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
import { T } from '@/lib/design-tokens';

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
        { id: 'daily', label: '日报', href: '/daily', icon: Newspaper },
        { id: 'weekly', label: '周刊', href: '/weekly', icon: ClipboardList },
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
        { id: 'stats', label: '数据统计', href: '/stats', icon: BarChart3 },
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
      style={{
        width: compact ? 72 : 220,
        height: '100vh',
        background: T.white,
        borderRight: `1px solid ${T.gray200}`,
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
        position: 'relative',
        userSelect: 'none',
      }}
    >
      {/* Brand */}
      <div style={{ padding: compact ? '24px 14px 28px' : '28px 24px 32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, justifyContent: compact ? 'center' : 'flex-start' }}>
          <div style={{ position: 'relative', width: 28, height: 28 }}>
            {/* Radar icon */}
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: '50%',
                background: `linear-gradient(135deg, ${T.primary}, #FF8F65)`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Radar size={16} color={T.white} strokeWidth={2.4} />
            </div>
            {/* Ping */}
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: 28,
                height: 28,
                borderRadius: '50%',
                border: `2px solid ${T.primary}`,
                animation: 'radar-ping 2s cubic-bezier(0, 0, 0.2, 1) infinite',
              }}
            />
          </div>
          {!compact && <div>
            <div
              style={{ fontSize: 17, fontWeight: 700, color: T.gray900, lineHeight: 1.2 }}
            >
              选题雷达
            </div>
            <div
              style={{ fontSize: 10, color: T.gray400, letterSpacing: '0.08em', marginTop: 1 }}
            >
              TOPIC RADAR
            </div>
          </div>}
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: compact ? '0 10px' : '0 12px', overflowY: 'auto' }}>
        {navSpaces.map((space) => (
          <div key={space.id} style={{ marginBottom: compact ? 12 : 18 }}>
            {!compact && (
              <div style={{
                fontSize: 11,
                fontWeight: 700,
                color: T.gray400,
                padding: '0 12px 7px',
                letterSpacing: '0.08em',
              }}>
                {space.label}
              </div>
            )}
            {space.items.map((item) => {
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  title={compact ? item.label : undefined}
                  onClick={() => router.push(item.href)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: compact ? 'center' : 'space-between',
                    padding: compact ? '10px 0' : '9px 12px',
                    marginBottom: 2,
                    fontSize: 14,
                    fontWeight: active ? 600 : 400,
                    color: active ? T.primary : T.gray600,
                    background: active ? T.primaryLight : 'transparent',
                    border: 'none',
                    borderRadius: T.radiusSm,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                    textAlign: 'left',
                  }}
                >
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Icon size={16} strokeWidth={active ? 2.2 : 1.8} />
                    {!compact && <span>{item.label}</span>}
                  </span>
                  {!compact && (item.count ?? 0) > 0 ? (
                    <span
                      style={{
                        fontSize: 11,
                        fontFamily: T.mono,
                        fontWeight: 500,
                        color: active ? T.primary : T.gray400,
                        background: active ? 'rgba(255,107,53,0.12)' : T.gray100,
                        padding: '1px 7px',
                        borderRadius: 10,
                      }}
                    >
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
      <div style={{ padding: compact ? '12px 10px 16px' : '12px 12px 16px', borderTop: `1px solid ${T.gray100}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: compact ? 0 : '0 12px', justifyContent: compact ? 'center' : 'flex-start' }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: '50%',
              background: `linear-gradient(135deg, ${T.teal}, #7DD3C0)`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 12,
              fontWeight: 600,
              color: T.white,
            }}
          >
            <UserRound size={14} strokeWidth={2} />
          </div>
          {!compact && <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: T.gray700 }}>创作者</div>
            <div style={{ fontSize: 10, color: T.gray400 }}>免费版</div>
          </div>}
        </div>
      </div>
    </div>
  );
}
