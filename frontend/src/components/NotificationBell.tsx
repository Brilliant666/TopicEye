'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Check, Info, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { T } from '@/lib/design-tokens';

interface Notification {
  id: number;
  type: string;      // success / error / warning / info
  category: string;  // fanqie_sync / daily_report / weekly_digest / system
  title: string;
  message: string;
  is_read: boolean;
  created_at: string | null;
}

const TYPE_STYLES: Record<string, { color: string; bg: string; icon: LucideIcon }> = {
  success: { color: '#059669', bg: '#ECFDF5', icon: Check },
  error:   { color: '#DC2626', bg: '#FEF2F2', icon: X },
  warning: { color: '#D97706', bg: '#FFFBEB', icon: Info },
  info:    { color: '#2563EB', bg: '#EFF6FF', icon: Info },
};

export default function NotificationBell() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/notifications/unread-count');
      const data = await res.json();
      setUnreadCount(data.count ?? 0);
    } catch {}
  }, []);

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch('/api/v1/notifications?limit=20');
      const data = await res.json();
      setNotifications(data.notifications ?? []);
    } catch {}
  }, []);

  useEffect(() => {
    void fetchUnreadCount();
    // 每 30 秒轮询一次未读数
    const timer = setInterval(() => void fetchUnreadCount(), 30000);
    return () => clearInterval(timer);
  }, [fetchUnreadCount]);

  useEffect(() => {
    if (open) void fetchNotifications();
  }, [open, fetchNotifications]);

  // 点击外部关闭
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const markRead = async (id: number) => {
    try {
      await fetch(`/api/v1/notifications/${id}/read`, { method: 'POST' });
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
      setUnreadCount(prev => Math.max(0, prev - 1));
    } catch {}
  };

  const markAllRead = async () => {
    try {
      await fetch('/api/v1/notifications/read-all', { method: 'POST' });
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {}
  };

  const formatTime = (iso: string | null) => {
    if (!iso) return '';
    const d = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}小时前`;
    return `${Math.floor(diffHr / 24)}天前`;
  };

  return (
    <div ref={panelRef} style={{ position: 'relative' }}>
      {/* 铃铛按钮 */}
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: 36, height: 36, borderRadius: '50%',
          background: open ? T.gray100 : 'transparent',
          border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          position: 'relative', transition: 'background 0.12s ease',
        }}
      >
        {/* 铃铛 SVG */}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={T.gray600} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {/* 未读数角标 */}
        {unreadCount > 0 && (
          <span style={{
            position: 'absolute', top: 4, right: 4,
            minWidth: 16, height: 16, borderRadius: 8,
            background: '#EF4444', color: '#fff',
            fontSize: 10, fontWeight: 700, fontFamily: T.mono,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: '0 4px',
          }}>
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* 通知面板 */}
      {open && (
        <div style={{
          position: 'absolute', top: 44, right: 0,
          width: 360, maxHeight: 480,
          background: T.white,
          border: `1px solid ${T.gray200}`,
          borderRadius: T.radius,
          boxShadow: '0 8px 30px rgba(0,0,0,0.12)',
          overflow: 'hidden',
          zIndex: 1000,
        }}>
          {/* 头部 */}
          <div style={{
            padding: '12px 16px',
            borderBottom: `1px solid ${T.gray100}`,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: T.gray900 }}>
              通知
            </span>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                style={{
                  fontSize: 11, color: T.primary, background: 'none',
                  border: 'none', cursor: 'pointer', fontWeight: 500,
                }}
              >
                全部已读
              </button>
            )}
          </div>

          {/* 通知列表 */}
          <div style={{ maxHeight: 400, overflow: 'auto' }}>
            {notifications.length === 0 ? (
              <div style={{
                padding: '40px 0', textAlign: 'center',
                fontSize: 13, color: T.gray400,
              }}>
                暂无通知
              </div>
            ) : (
              notifications.map(n => {
                const ts = TYPE_STYLES[n.type] || TYPE_STYLES.info;
                const Icon = ts.icon;
                return (
                  <div
                    key={n.id}
                    onClick={() => { if (!n.is_read) void markRead(n.id); }}
                    style={{
                      padding: '12px 16px',
                      borderBottom: `1px solid ${T.gray50}`,
                      background: n.is_read ? 'transparent' : '#FAFAFE',
                      cursor: n.is_read ? 'default' : 'pointer',
                      transition: 'background 0.1s ease',
                    }}
                  >
                    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                      {/* 类型图标 */}
                      <div style={{
                        width: 22, height: 22, borderRadius: '50%',
                        background: ts.bg, color: ts.color,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>
                        <Icon size={13} strokeWidth={2.2} />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          fontSize: 13, fontWeight: n.is_read ? 400 : 600,
                          color: T.gray900,
                          overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}>
                          {n.title}
                        </div>
                        <div style={{
                          fontSize: 12, color: T.gray500, marginTop: 2,
                          overflow: 'hidden', textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}>
                          {n.message}
                        </div>
                        <div style={{
                          fontSize: 10, color: T.gray400, marginTop: 4,
                          fontFamily: T.mono,
                        }}>
                          {formatTime(n.created_at)}
                        </div>
                      </div>
                      {/* 未读指示点 */}
                      {!n.is_read && (
                        <div style={{
                          width: 8, height: 8, borderRadius: '50%',
                          background: T.primary, flexShrink: 0, marginTop: 6,
                        }} />
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
