'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Activity, Radar, Settings2 } from 'lucide-react';
import { useAuthContext } from '@/providers/AuthProvider';
import { currentLoginHref, loginHrefForPath } from '@/lib/auth-redirect';

import {
  RARDAR_NAVIGATION,
  isRardarNavigationActive,
} from '@/lib/product-profile';
import styles from './RardarFoundation.module.css';

export default function RardarShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { currentUser, authLoading, logout } = useAuthContext();

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
                aria-current={isRardarNavigationActive(pathname, item.href) ? 'page' : undefined}
                className={`${styles.navLink} ${
                  isRardarNavigationActive(pathname, item.href) ? styles.navLinkActive : ''
                }`}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className={styles.headerActions}>
            <span className={styles.statusPill}>
              <Activity size={14} aria-hidden="true" /> Facts first · AI assisted
            </span>
            {!authLoading && !currentUser && <Link href={loginHrefForPath(pathname)} className={styles.adminLink} onClick={(event) => { event.preventDefault(); router.push(currentLoginHref(pathname)); }}>登录</Link>}
            {currentUser && <button type="button" className={styles.adminLink} onClick={() => void logout()} aria-label="退出登录">退出</button>}
            {currentUser?.role === 'admin' && <Link href="/admin" className={styles.adminLink} aria-label="打开 TopicEye 管理后台">
              <Settings2 size={18} aria-hidden="true" />
            </Link>}
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
            aria-current={isRardarNavigationActive(pathname, item.href) ? 'page' : undefined}
            className={`${styles.navLink} ${
              isRardarNavigationActive(pathname, item.href) ? styles.navLinkActive : ''
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
