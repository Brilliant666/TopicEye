'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { contentsApi, feedbackApi, type FeedbackType, type ScoringFlowResponse, type ScoringFlowSample } from '@/lib/api';
import {
  AlgorithmHeader,
  Funnel,
  MixList,
  PathPanel,
  SampleList,
  SummaryGrid,
} from './components';

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
  const [hours, setHours] = useState(48);
  const [data, setData] = useState<ScoringFlowResponse | null>(null);
  const [selected, setSelected] = useState<ScoringFlowSample | undefined>();
  const [loading, setLoading] = useState(true);
  const [feedbacking, setFeedbacking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFlow = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await contentsApi.scoringFlow({ hours, limit: 160 });
      setData(result);
      setSelected((prev) => result.samples.find((s) => s.id === prev?.id) || result.samples[0]);
    } catch (err) {
      setError(err instanceof Error ? err.message : '算法流程加载失败');
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => { void fetchFlow(); }, [fetchFlow]);

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
          onHoursChange={setHours}
          onRefresh={() => void fetchFlow()}
        />

        {error && (
          <div className="mb-4 rounded-sm border border-red/20 bg-red-light px-4 py-3 text-sm text-red">
            {error}
          </div>
        )}

        {loading && !data ? (
          <div className="rounded-lg border border-gray-200 bg-white px-6 py-12 text-center text-sm text-gray-400">
            加载算法流程...
          </div>
        ) : data ? (
          <>
            <SummaryGrid data={data} />
            <Funnel data={data} selectedKey={selectedKey} />

            <div className="mt-4 grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_340px] 2xl:grid-cols-[minmax(0,1fr)_380px]">
              <div className="min-w-0 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <MixList title="类别混排压力" items={data.category_mix} tone="purple" />
                  <MixList title="来源混排压力" items={data.source_mix} tone="teal" />
                </div>
                <SampleList samples={data.samples} selectedId={selected?.id} onSelect={setSelected} />
              </div>
              <PathPanel sample={selected} onFeedback={handleFeedback} feedbacking={feedbacking} />
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
