'use client';

import Link, { useLinkStatus } from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, Radar, Settings2 } from 'lucide-react';

import {
  RARDAR_NAVIGATION,
  isRardarNavigationActive,
} from '@/lib/product-profile';
import styles from './RardarFoundation.module.css';

function NavigationPendingHint() {
  const { pending } = useLinkStatus();
  return <span
    className={styles.navPendingHint}
    data-testid="rardar-navigation-pending"
    data-pending={pending ? 'true' : 'false'}
    role="status"
    aria-live="polite"
    aria-label={pending ? '正在切换页面' : undefined}
  />;
}

export default function RardarShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div
      className={styles.product}
      data-product-profile="rardar"
      data-rardar-shell="true"
    >
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link href="/" className={styles.brand} aria-label="Rardar 今日">
            <span className={styles.logo} aria-hidden="true">
              <Radar size={21} strokeWidth={2.4} />
            </span>
            <span>
              <span className={styles.brandName}>Rardar</span>
              <span className={styles.brandTagline}>Developer Intelligence</span>
            </span>
          </Link>

          <nav className={styles.desktopNav} aria-label="Rardar 主导航">
            {RARDAR_NAVIGATION.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-label={item.label}
                aria-current={isRardarNavigationActive(pathname, item.href) ? 'page' : undefined}
                className={`${styles.navLink} ${
                  isRardarNavigationActive(pathname, item.href) ? styles.navLinkActive : ''
                }`}
              >
                {item.label}
                <NavigationPendingHint />
              </Link>
            ))}
          </nav>

          <div className={styles.headerActions}>
            <span className={styles.statusPill}>
              <Activity size={14} aria-hidden="true" /> Facts first · AI assisted
            </span>
            {/* The admin route has its own HTTP authentication boundary. Never prefetch it from public reading pages. */}
            <a href="/admin" className={styles.adminLink} aria-label="打开 TopicEye 管理后台">
              <Settings2 size={18} aria-hidden="true" />
            </a>
          </div>
        </div>
      </header>

      <main id="main-content" className={styles.main}>
        {children}
      </main>

      <nav className={styles.mobileNav} aria-label="Rardar 移动导航">
        {RARDAR_NAVIGATION.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            aria-label={item.label}
            aria-current={isRardarNavigationActive(pathname, item.href) ? 'page' : undefined}
            className={`${styles.navLink} ${
              isRardarNavigationActive(pathname, item.href) ? styles.navLinkActive : ''
            }`}
          >
            {item.label}
            <NavigationPendingHint />
          </Link>
        ))}
      </nav>
    </div>
  );
}
