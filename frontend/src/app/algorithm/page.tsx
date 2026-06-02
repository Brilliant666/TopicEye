'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { contentsApi, feedbackApi, type FeedbackType, type ScoringFlowResponse, type ScoringFlowSample } from '@/lib/api';
import {
  AlgorithmHeader,
  DiagnosticsPanel,
  Funnel,
  MixList,
  PathPanel,
  SampleList,
  SummaryGrid,
} from './components';

const DEFAULT_HOURS = 48;

function selectedStageKey(sample?: ScoringFlowSample) {
  if (!sample) return undefined;
  if (sample.selected) return 'selected';
  if (sample.quality_factor <= 0.55) return 'quality';
  if (sample.risk_factor <= 0.55) return 'risk';
  if (sample.time_decay < 0.6) return 'freshness';
  if (sample.diversity_factor < 0.85) return 'diversity';
  return 'candidates';
}

export default function AlgorithmPage() {
  const [hours, setHours] = useState(DEFAULT_HOURS);
  const [data, setData] = useState<ScoringFlowResponse | null>(null);
  const [selected, setSelected] = useState<ScoringFlowSample | undefined>();
  const [loading, setLoading] = useState(true);
  const [feedbacking, setFeedbacking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fallbackNotice, setFallbackNotice] = useState<string | null>(null);
  const requestSeqRef = useRef(0);
  const initialFallbackRef = useRef(false);

  const fetchFlow = useCallback(async () => {
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    setLoading(true);
    setError(null);
    try {
      const result = await contentsApi.scoringFlow({ hours, limit: 160 });
      if (requestSeq !== requestSeqRef.current) return;
      const recommendedHours = result.diagnostics?.recommended_hours;
      if (
        !initialFallbackRef.current &&
        hours === DEFAULT_HOURS &&
        result.diagnostics?.empty_reason === 'no_content_in_window' &&
        recommendedHours &&
        recommendedHours !== hours
      ) {
        initialFallbackRef.current = true;
        requestSeqRef.current = requestSeq + 1;
        setFallbackNotice(`默认 48 小时窗口暂无样本，已自动切到 ${recommendedHours >= 168 ? `${recommendedHours / 24} 天` : `${recommendedHours} 小时`} 调试窗口。`);
        setHours(recommendedHours);
        return;
      }
      setData(result);
      setSelected((prev) => result.samples.find((s) => s.id === prev?.id) || result.samples[0]);
    } catch (err) {
      if (requestSeq !== requestSeqRef.current) return;
      setError(err instanceof Error ? err.message : '算法流程加载失败');
    } finally {
      if (requestSeq === requestSeqRef.current) setLoading(false);
    }
  }, [hours]);

  useEffect(() => { void fetchFlow(); }, [fetchFlow]);

  const handleHoursChange = useCallback((nextHours: number) => {
    initialFallbackRef.current = true;
    setFallbackNotice(null);
    setHours(nextHours);
  }, []);

  const handleFeedback = useCallback(async (sample: ScoringFlowSample, type: FeedbackType) => {
    setFeedbacking(true);
    setError(null);
    try {
      await feedbackApi.submit(sample.id, type, 'algorithm-flow');
      await fetchFlow();
    } catch (err) {
      setError(err instanceof Error ? err.message : '反馈提交失败');
    } finally {
      setFeedbacking(false);
    }
  }, [fetchFlow]);

  const selectedKey = useMemo(() => selectedStageKey(selected), [selected]);

  return (
    <div className="fade-in h-full overflow-y-auto bg-page px-6 py-6 lg:px-10 lg:py-8">
      <div className="mx-auto max-w-[1480px]">
        <AlgorithmHeader
          hours={hours}
          loading={loading}
          onHoursChange={handleHoursChange}
          onRefresh={() => void fetchFlow()}
        />

        {error && (
          <div className="mb-4 rounded-sm border border-red/20 bg-red-light px-4 py-3 text-sm text-red">
            {error}
          </div>
        )}

        {fallbackNotice && (
          <div className="mb-4 rounded-sm border border-amber/20 bg-amber-light px-4 py-3 text-sm font-bold text-amber">
            {fallbackNotice}
          </div>
        )}

        {loading && !data ? (
          <div className="rounded-lg border border-gray-200 bg-white px-6 py-12 text-center text-sm text-gray-400">
            加载算法流程...
          </div>
        ) : data ? (
          <>
            <SummaryGrid data={data} />
            <DiagnosticsPanel data={data} onHoursChange={handleHoursChange} />
            <Funnel data={data} selectedKey={selectedKey} />

            <div className="mt-4 grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[280px_minmax(560px,1fr)_380px]">
              <div className="order-3 min-w-0 space-y-4 lg:col-start-1 lg:row-start-2 2xl:order-none 2xl:col-start-1 2xl:row-start-1">
                <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-1">
                  <MixList title="类别混排压力" items={data.category_mix} tone="purple" />
                  <MixList title="来源混排压力" items={data.source_mix} tone="teal" />
                </div>
              </div>
              <div className="order-1 min-w-0 lg:col-start-1 lg:row-start-1 2xl:order-none 2xl:col-start-2 2xl:row-start-1">
                <SampleList samples={data.samples} selectedId={selected?.id} onSelect={setSelected} />
              </div>
              <div className="order-2 min-w-0 lg:sticky lg:top-4 lg:col-start-2 lg:row-span-2 lg:row-start-1 2xl:order-none 2xl:col-start-3 2xl:row-start-1">
                <PathPanel sample={selected} onFeedback={handleFeedback} feedbacking={feedbacking} />
              </div>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
