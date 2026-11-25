import { useMemo } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';
import type { DecisionRecord, DecisionsPayload, Lang, ZoneInfo } from '@/types/viz';
import { fmt, getDict } from '@/i18n';

interface ReasonFeedPanelProps {
  decisionsPayload: DecisionsPayload;
  month: number;
  mentionKeywords: string[];
  zoneById: Record<string, ZoneInfo>;
  filterZone: string | null;
  expanded: boolean;
  lang: Lang;
  onToggleExpand: () => void;
  onSelectDecisionRoom: (roomId: number, zoneId: string) => void;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function renderHighlightedReason(text: string, keywords: string[]) {
  if (!text || !keywords.length) return text;
  const regex = new RegExp(`(${keywords.map(escapeRegExp).join('|')})`, 'g');
  const parts = text.split(regex);
  return parts.map((part, idx) =>
    keywords.includes(part) ? (
      <mark key={idx} className="kw-mark">
        {part}
      </mark>
    ) : (
      <span key={idx}>{part}</span>
    )
  );
}

export function ReasonFeedPanel({
  decisionsPayload,
  month,
  mentionKeywords,
  zoneById,
  filterZone,
  expanded,
  lang,
  onToggleExpand,
  onSelectDecisionRoom,
}: ReasonFeedPanelProps) {
  const t = getDict(lang);
  const mKey = String(month);
  const stat = decisionsPayload.mention_stats[mKey] ?? {
    total: 0,
    mentions: 0,
    rate: 0,
    treated_total: 0,
    treated_mentions: 0,
    treated_rate: 0,
  };

  // Non-cherry-picked stratified feed sample (§9.2), or filtered by user-selected zone
  const items: DecisionRecord[] = useMemo(() => {
    if (filterZone) {
      return decisionsPayload.decisions
        .filter(
          (d) =>
            d.m === month &&
            d.agent_type === 'landlord' &&
            (d.decision === 'price_vacant' || d.decision === 'renewal_offer') &&
            d.zone === filterZone
        )
        .slice(0, expanded ? 18 : 10);
    }
    const sampleIdxs = decisionsPayload.feed_sample_by_month[mKey] ?? [];
    return sampleIdxs.map((i) => decisionsPayload.decisions[i]).filter(Boolean);
  }, [decisionsPayload, month, mKey, filterZone, expanded]);

  // Mention-rate 36-month curve for expanded Chapter 4 view (§3 Ch4)
  const mentionCurvePath = useMemo(() => {
    if (!expanded) return { treated: '', all: '', curX: 0, curY: 0 };
    const W = 420;
    const H = 64;
    const x = (m: number) => 6 + ((W - 12) * (m - 1)) / 35;
    const y = (rate: number) => H - 8 - Math.min(1, rate) * (H - 16);
    let dTr = '';
    let dAll = '';
    for (let m = 1; m <= 36; m++) {
      const s = decisionsPayload.mention_stats[String(m)];
      const tr = s?.treated_rate ?? 0;
      const al = s?.rate ?? 0;
      dTr += (m === 1 ? 'M' : 'L') + `${x(m).toFixed(1)},${y(tr).toFixed(1)}`;
      dAll += (m === 1 ? 'M' : 'L') + `${x(m).toFixed(1)},${y(al).toFixed(1)}`;
    }
    return {
      treated: dTr,
      all: dAll,
      curX: x(month),
      curY: y(stat.treated_rate),
    };
  }, [expanded, decisionsPayload.mention_stats, month, stat.treated_rate]);

  const trPct = Math.round(stat.treated_rate * 100);
  const allPct = Math.round(stat.rate * 100);

  return (
    <div
      className="hud-panel"
      style={{
        width: '100%',
        flex: 1,
        minHeight: 0,
        padding: '14px 16px 10px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header + mandatory §9.4 disclaimer */}
      <div className="panel-header" style={{ marginBottom: 6 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>{t.feed.title}</span>
          {filterZone && zoneById[filterZone] && (
            <span
              style={{
                fontFamily: 'var(--font-sans)',
                fontSize: 11,
                fontWeight: 400,
                color: 'var(--sub)',
              }}
            >
              {lang === 'zh' ? zoneById[filterZone].name : zoneById[filterZone].name_en}
            </span>
          )}
        </div>
        <button type="button" className="btn-hud" style={{ padding: '2px 4px', border: 'none', fontWeight: 400 }} onClick={onToggleExpand}>
          {expanded ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
          {expanded ? t.feed.collapse : t.feed.expand}
        </button>
      </div>

      {/* §9.4 Mandatory Academic Integrity Note */}
      <div style={{ fontSize: 11.5, color: 'var(--sub)', marginBottom: 10 }}>
        {t.feed.disclaimer}
      </div>

      {/* Full-denominator mention rate progress bar (§9.2) */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--sub)', marginBottom: 5 }}>
          <span>{t.feed.mentionLabel}</span>
          <span className="num" style={{ color: 'var(--text)' }}>
            {t.feed.mentionTreated} {trPct}% ({stat.treated_mentions}/{stat.treated_total}) · {t.feed.mentionAll} {allPct}%
          </span>
        </div>
        <div style={{ height: 2, background: '#2A2E35', overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${trPct}%`,
              background: 'var(--accent)',
              transition: 'width 0.4s ease',
            }}
          />
        </div>
      </div>

      {/* Chapter 4 Expanded 36-month Mention-Rate Sparkline */}
      {expanded && (
        <div
          style={{
            marginBottom: 10,
            padding: '8px 0',
            borderTop: '1px solid var(--line-soft)',
            borderBottom: '1px solid var(--line-soft)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--sub)', marginBottom: 4 }}>
            <span>{lang === 'zh' ? '36 个月“提到新线”比例走势（全部定价决策）' : '36-Month New-Line Mention Share (All Pricing Quotes)'}</span>
            <span>
              <span style={{ color: 'var(--accent)' }}>— {t.feed.mentionTreated}</span>{' '}
              <span style={{ color: 'var(--sub)', marginLeft: 8 }}>— {t.feed.mentionAll}</span>
            </span>
          </div>
          <svg viewBox="0 0 420 64" style={{ width: '100%', height: 64 }}>
            <rect x={6 + (408 * 12) / 35} y={4} width={(408 * 12) / 35} height={54} fill="#E8E4DC" fillOpacity={0.04} />
            <path d={mentionCurvePath.all} fill="none" stroke="#8A8F98" strokeWidth={1.1} />
            <path d={mentionCurvePath.treated} fill="none" stroke="#E4572E" strokeWidth={1.6} />
            <line x1={mentionCurvePath.curX} x2={mentionCurvePath.curX} y1={2} y2={60} stroke="#E8E4DC" strokeOpacity={0.35} />
            <circle cx={mentionCurvePath.curX} cy={mentionCurvePath.curY} r={3} fill="#E4572E" />
          </svg>
        </div>
      )}

      {/* Stratified Landlord Reason Stream */}
      <div className="hud-scroll" style={{ flex: 1, paddingRight: 4 }}>
        {items.length === 0 ? (
          <div style={{ color: 'var(--sub)', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>{t.feed.empty}</div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: expanded ? 'repeat(2, minmax(0, 1fr))' : '1fr',
              columnGap: expanded ? 24 : 0,
            }}
          >
            {items.map((d, idx) => {
              const zInfo = d.zone ? zoneById[d.zone] : undefined;
              const isTreated = Boolean(zInfo?.treated);
              const rb = d.rent_before ?? 0;
              const ra = d.rent_after ?? rb;
              const diff = ra - rb;
              const decLabel =
                d.decision === 'renewal_offer'
                  ? t.feed.renewal
                  : d.decision === 'price_vacant'
                  ? t.feed.vacant
                  : d.decision === 'answer_counter'
                  ? t.feed.counter
                  : t.feed.pick;
              const llKind = (d.ll_kind && (t.landlordKinds as Record<string, string>)[d.ll_kind]) || d.ll_kind || '';
              const llRisk = (d.ll_risk && (t.landlordKinds as Record<string, string>)[d.ll_risk]) || d.ll_risk || '';

              return (
                <div
                  key={`${d.m}_${d.agent_id}_${d.room_id}_${idx}`}
                  className="feed-item"
                  onClick={() => {
                    if (d.room_id !== null && d.zone) {
                      onSelectDecisionRoom(d.room_id, d.zone);
                    }
                  }}
                  style={{
                    padding: '11px 0 11px 12px',
                    borderBottom: '1px solid var(--line-soft)',
                    borderLeft: `2px solid ${d.mentions_line ? 'var(--accent)' : 'transparent'}`,
                    cursor: 'pointer',
                    animationDelay: `${idx * 0.04}s`,
                  }}
                >
                  <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', fontSize: 11.5, color: 'var(--sub)', flexWrap: 'wrap' }}>
                    <span style={{ color: 'var(--text)', fontWeight: 600 }}>
                      {zInfo ? (lang === 'zh' ? zInfo.name : zInfo.name_en) : d.zone}
                    </span>
                    <span>
                      {llKind}·{llRisk}
                    </span>
                    <span>· {decLabel}</span>
                    {d.vacant_for ? (
                      <span>· {fmt(t.feed.vacMonths, { n: d.vacant_for })}</span>
                    ) : null}
                    <span
                      className="num"
                      style={{
                        marginLeft: 'auto',
                        fontWeight: 500,
                        color: diff > 1 ? 'var(--text)' : 'var(--sub)',
                      }}
                    >
                      ¥{Math.round(rb)} → {Math.round(ra)}
                    </span>
                  </div>
                  <div
                    className="serif"
                    style={{
                      fontSize: expanded ? 14 : 13.5,
                      color: d.mentions_line ? '#F2EFE9' : '#C2C0BB',
                      marginTop: 5,
                      lineHeight: 1.65,
                    }}
                  >
                    “{renderHighlightedReason(d.reason, mentionKeywords)}”
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* §9.2 Stratified random sampling note */}
      <div style={{ fontSize: 11, color: 'var(--faint)', marginTop: 6, paddingTop: 6 }}>
        {t.feed.sampledNote}
      </div>
    </div>
  );
}
