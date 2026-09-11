import Link from 'next/link';
import { notFound } from 'next/navigation';
import { isRardarProduct } from '@/lib/product-profile';

export default function RardarPausedPage({ title }: { title: string }) {
  if (!isRardarProduct()) notFound();
  return <section className="mx-auto max-w-3xl px-5 py-12">
    <h1 className="text-3xl font-bold">{title}已暂停</h1>
    <p className="mt-4 leading-7 text-gray-600">该模块已退出 Rardar 当前产品主线。已有数据与共享项目资料保留，不再启动专属采集或 AI 处理。</p>
    <p className="mt-6"><Link href="/" className="text-blue-700">浏览今日热榜</Link> · <Link href="/historical-hot" className="text-blue-700">浏览历史回顾</Link> · <Link href="/find" className="text-blue-700">按需求找项目</Link></p>
  </section>;
}
