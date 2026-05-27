'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { T } from '@/lib/design-tokens';
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
    <div className="fade-in" style={{ padding: '28px 32px', height: '100%', overflowY: 'auto', background: T.bg }}>
      <AlgorithmHeader
        hours={hours}
        loading={loading}
        onHoursChange={setHours}
        onRefresh={() => void fetchFlow()}
      />

      {error && (
        <div style={{ background: T.redLight, color: T.red, border: `1px solid ${T.red}22`, borderRadius: T.radiusSm, padding: 14, marginBottom: 18, fontSize: 13 }}>
          {error}
        </div>
      )}

      {loading && !data ? (
        <div style={{ color: T.gray400, fontSize: 13 }}>加载算法流程...</div>
      ) : data ? (
        <>
          <SummaryGrid data={data} />
          <div style={{ marginBottom: 14 }}>
            <Funnel data={data} selectedKey={selectedKey} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 0.95fr) minmax(420px, 1.25fr) minmax(340px, 0.95fr)', gap: 14, alignItems: 'start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <MixList title="类别混排压力" items={data.category_mix} color={T.purple} />
              <MixList title="来源混排压力" items={data.source_mix} color={T.teal} />
            </div>
            <SampleList samples={data.samples} selectedId={selected?.id} onSelect={setSelected} />
            <PathPanel sample={selected} onFeedback={handleFeedback} feedbacking={feedbacking} />
          </div>
        </>
      ) : null}
    </div>
  );
}
