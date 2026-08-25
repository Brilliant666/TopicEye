'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { ArrowLeft, RouteOff } from 'lucide-react';

import styles from './RardarFoundation.module.css';

export default function RardarLegacyRouteRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/');
  }, [router]);

  return (
    <div className={styles.page} data-route-policy="REDIRECT">
      <section className={styles.emptyCard}>
        <div className={styles.emptyContent}>
          <span className={styles.emptyIcon} aria-hidden="true">
            <RouteOff size={30} />
          </span>
          <h1>该 TopicEye 内容页未在 Rardar 前台开放</h1>
          <p>旧路由仍保留在默认 TopicEye 模式中；Rardar 模式会返回新的产品首页。</p>
          <div className={styles.slotLabel}>REDIRECT → /</div>
          <p className={styles.nextStep}>
            <Link href="/">
              <ArrowLeft size={15} aria-hidden="true" /> 返回 Rardar 今日
            </Link>
          </p>
        </div>
      </section>
    </div>
  );
}
