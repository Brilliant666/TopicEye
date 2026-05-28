'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Bell, Check, Info, X } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cx } from '@/components/ui';

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
    <div ref={panelRef} className="relative">
      {/* 铃铛按钮 */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cx('relative flex h-9 w-9 items-center justify-center rounded-full border-0 transition', open ? 'bg-gray-100' : 'bg-transparent hover:bg-gray-100')}
      >
        <Bell size={18} className="text-gray-600" strokeWidth={2} />
        {/* 未读数角标 */}
        {unreadCount > 0 && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red px-1 font-mono text-[10px] font-bold text-white">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* 通知面板 */}
      {open && (
        <div className="absolute right-0 top-11 z-[1000] max-h-[480px] w-[360px] overflow-hidden rounded-lg border border-gray-200 bg-white shadow-[0_8px_30px_rgba(0,0,0,0.12)]">
          {/* 头部 */}
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <span className="text-sm font-bold text-gray-900">
              通知
            </span>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="border-0 bg-transparent text-[11px] font-medium text-primary"
              >
                全部已读
              </button>
            )}
          </div>

          {/* 通知列表 */}
          <div className="max-h-[400px] overflow-auto">
            {notifications.length === 0 ? (
              <div className="py-10 text-center text-[13px] text-gray-400">
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
                    className={cx('border-b border-gray-50 px-4 py-3 transition', n.is_read ? 'cursor-default bg-transparent' : 'cursor-pointer bg-[#FAFAFE]')}
                  >
                    <div className="flex items-start gap-2.5">
                      {/* 类型图标 */}
                      <div className="flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full" style={{ background: ts.bg, color: ts.color }}>
                        <Icon size={13} strokeWidth={2.2} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className={cx('truncate text-[13px] text-gray-900', n.is_read ? 'font-normal' : 'font-semibold')}>
                          {n.title}
                        </div>
                        <div className="mt-0.5 truncate text-xs text-gray-500">
                          {n.message}
                        </div>
                        <div className="mt-1 font-mono text-[10px] text-gray-400">
                          {formatTime(n.created_at)}
                        </div>
                      </div>
                      {/* 未读指示点 */}
                      {!n.is_read && (
                        <div className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />
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
