'use client';

import React from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { T } from '@/lib/design-tokens';

interface SidebarProps {
  topicCount?: number;
  favCount?: number;
  sourceCount?: number;
}

interface NavItem {
  id: string;
  label: string;
  href: string;
  count?: number;
  badge?: string;
}

export default function Sidebar({ topicCount = 0, favCount = 0, sourceCount = 0 }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const navItems: NavItem[] = [
    { id: 'lfv', label: '低粉爆文', href: '/low-follower-viral', badge: 'NEW' },
    { id: 'picks', label: '当日精选', href: '/today-picks', badge: 'HOT' },
    { id: 'my-topics', label: '我的母题', href: '/my-topics', badge: '私' },
    { id: 'today', label: '今日选题', href: '/', count: topicCount },
    { id: 'daily', label: 'AI 日报', href: '/daily', badge: 'NEW' },
    { id: 'weekly', label: 'AI 周刊', href: '/weekly', badge: 'NEW' },
    { id: 'stats', label: '数据统计', href: '/stats' },
    { id: 'favorites', label: '收藏夹', href: '/favorites', count: favCount },
    { id: 'sources', label: '信源管理', href: '/sources', count: sourceCount },
    { id: 'trends', label: '趋势追踪', href: '/trends', badge: 'NEW' },
    { id: 'trending', label: '趋势雷达', href: '/trending', badge: 'NEW' },
    { id: 'fanqie', label: '网文雷达', href: '/fanqie', badge: 'NEW' },
    { id: 'model-eval', label: '模型测评', href: '/model-eval' },
  ];

  const isActive = (href: string) => {
    if (href === '/') return pathname === '/';
    return pathname.startsWith(href);
  };

  return (
    <div
      style={{
        width: 220,
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
      <div style={{ padding: '28px 24px 32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
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
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: T.white }} />
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
          <div>
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
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ flex: 1, padding: '0 12px' }}>
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <button
              key={item.id}
              onClick={() => router.push(item.href)}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 12px',
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
              <span>{item.label}</span>
              {item.badge ? (
                <span
                  style={{
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: '0.06em',
                    color: T.white,
                    background: T.teal,
                    padding: '2px 6px',
                    borderRadius: 4,
                  }}
                >
                  {item.badge}
                </span>
              ) : (item.count ?? 0) > 0 ? (
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
      </nav>

      {/* Bottom User Area */}
      <div style={{ padding: '12px 12px 16px', borderTop: `1px solid ${T.gray100}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 12px' }}>
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
            U
          </div>
          <div>
            <div style={{ fontSize: 12, fontWeight: 500, color: T.gray700 }}>创作者</div>
            <div style={{ fontSize: 10, color: T.gray400 }}>免费版</div>
          </div>
        </div>
      </div>
    </div>
  );
}
