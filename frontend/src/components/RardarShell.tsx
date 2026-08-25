'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, Radar, Settings2 } from 'lucide-react';
import { RARDAR_NAVIGATION } from '@/lib/product-profile';

export default function RardarShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === '/' ? pathname === '/' || pathname === '/rardar-poc' : pathname.startsWith(href);

  return (
    <div className="min-h-dvh overflow-auto bg-[#f5f8ff] text-slate-950">
      <header className="sticky top-0 z-50 border-b border-blue-100/80 bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-7 px-4 sm:px-7 lg:px-10">
          <Link href="/" className="group flex shrink-0 items-center gap-2.5" aria-label="Rardar 今日">
            <span className="relative grid h-9 w-9 place-items-center rounded-xl bg-blue-600 text-white shadow-lg shadow-blue-600/25">
              <Radar size={20} strokeWidth={2.4} />
              <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-cyan-400" />
            </span>
            <span>
              <span className="block text-[17px] font-black tracking-tight">Rardar</span>
              <span className="block text-[9px] font-bold uppercase tracking-[0.18em] text-blue-500">Developer Intel</span>
            </span>
          </Link>

          <nav className="hidden min-w-0 flex-1 items-center gap-1 lg:flex" aria-label="Rardar 主导航">
            {RARDAR_NAVIGATION.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-2 text-sm font-bold transition ${
                  isActive(item.href)
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700 sm:inline-flex">
              <Activity size={13} /> POC 数据已验证
            </span>
            <Link
              href="/admin/rardar-poc"
              aria-label="打开 TopicEye 管理诊断"
              className="grid h-9 w-9 place-items-center rounded-lg border border-slate-200 bg-white text-slate-500 transition hover:border-blue-300 hover:text-blue-600"
            >
              <Settings2 size={17} />
            </Link>
          </div>
        </div>
      </header>

      <main id="main-content" className="min-h-[calc(100dvh-4rem)] pb-24 lg:pb-8">
        {children}
      </main>

      <nav
        className="fixed inset-x-3 bottom-3 z-50 grid grid-cols-6 rounded-2xl border border-blue-100 bg-white/95 p-1.5 shadow-2xl shadow-blue-950/15 backdrop-blur-xl lg:hidden"
        aria-label="Rardar 移动导航"
      >
        {RARDAR_NAVIGATION.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded-xl px-1 py-2 text-center text-[10px] font-bold ${
              isActive(item.href) ? 'bg-blue-600 text-white' : 'text-slate-500'
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
