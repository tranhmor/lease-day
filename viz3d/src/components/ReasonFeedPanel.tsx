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
      className="hud-panel amber"
      style={{
        width: '100%',
        flex: 1,
        minHeight: 0,
        padding: '11px 14px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header + mandatory §9.4 disclaimer */}
      <div className="panel-header" style={{ marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>{t.feed.title}</span>
          {filterZone && zoneById[filterZone] && (
            <span
              style={{
                fontSize: 10,
                padding: '1px 6px',
                borderRadius: 3,
                background: 'rgba(95, 180, 255, 0.16)',
                color: 'var(--cool)',
              }}
            >
              {lang === 'zh' ? zoneById[filterZone].name : zoneById[filterZone].name_en}
            </span>
          )}
        </div>
        <button type="button" className="btn-hud" style={{ padding: '2px 7px' }} onClick={onToggleExpand}>
          {expanded ? <Minimize2 size={11} /> : <Maximize2 size={11} />}
          {expanded ? t.feed.collapse : t.feed.expand}
        </button>
      </div>

      {/* §9.4 Mandatory Academic Integrity Note */}
      <div style={{ fontSize: 10, color: 'var(--sub)', marginBottom: 8, opacity: 0.9 }}>
        {t.feed.disclaimer}
      </div>

      {/* Full-denominator mention rate progress bar (§9.2) */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--sub)', marginBottom: 4 }}>
          <span>{t.feed.mentionLabel}</span>
          <span className="mono" style={{ color: trPct > 0 ? 'var(--announce)' : 'var(--sub)' }}>
            {t.feed.mentionTreated} {trPct}% ({stat.treated_mentions}/{stat.treated_total}) · {t.feed.mentionAll} {allPct}%
          </span>
        </div>
        <div style={{ height: 5, background: '#1A2740', borderRadius: 3, overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${trPct}%`,
              background: 'linear-gradient(90deg, #FF8A6B, #FFB02E)',
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
            padding: '8px 10px',
            background: 'rgba(11, 17, 28, 0.55)',
            border: '1px solid var(--line)',
            borderRadius: 4,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--sub)', marginBottom: 4 }}>
            <span>{lang === 'zh' ? '36 个月“提到新线”比例走势（全部定价决策）' : '36-Month New-Line Mention Share (All Pricing Quotes)'}</span>
            <span className="mono">
              <span style={{ color: 'var(--announce)' }}>■ {t.feed.mentionTreated}</span>{' '}
              <span style={{ color: 'var(--cool)', marginLeft: 8 }}>■ {t.feed.mentionAll}</span>
            </span>
          </div>
          <svg viewBox="0 0 420 64" style={{ width: '100%', height: 64 }}>
            <rect x={6 + (408 * 12) / 35} y={4} width={(408 * 12) / 35} height={54} fill="#FFB02E" fillOpacity={0.07} />
            <path d={mentionCurvePath.all} fill="none" stroke="#5FB4FF" strokeWidth={1.3} strokeOpacity={0.65} />
            <path d={mentionCurvePath.treated} fill="none" stroke="#FFB02E" strokeWidth={2.0} />
            <line x1={mentionCurvePath.curX} x2={mentionCurvePath.curX} y1={2} y2={60} stroke="#fff" strokeOpacity={0.45} />
            <circle cx={mentionCurvePath.curX} cy={mentionCurvePath.curY} r={3.5} fill="#FFB02E" stroke="#fff" strokeWidth={1.2} />
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
              gap: expanded ? 10 : 0,
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
                    padding: expanded ? '10px 11px' : '9px 4px',
                    borderBottom: expanded ? undefined : '1px solid rgba(125, 138, 163, 0.14)',
                    border: expanded
                      ? `1px solid ${d.mentions_line ? 'rgba(255,176,46,0.45)' : 'var(--line)'}`
                      : undefined,
                    borderRadius: expanded ? 4 : 3,
                    background: expanded
                      ? d.mentions_line
                        ? 'rgba(255, 176, 46, 0.06)'
                        : 'rgba(11, 17, 28, 0.45)'
                      : 'transparent',
                    cursor: 'pointer',
                    animationDelay: `${idx * 0.04}s`,
                  }}
                >
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 11, color: 'var(--sub)', flexWrap: 'wrap' }}>
                    <span style={{ color: isTreated ? 'var(--announce)' : '#9FD3FF', fontWeight: 600 }}>
                      {zInfo ? (lang === 'zh' ? zInfo.name : zInfo.name_en) : d.zone}
                    </span>
                    <span>
                      {llKind}·{llRisk}
                    </span>
                    <span style={{ opacity: 0.78 }}>{decLabel}</span>
                    {d.vacant_for ? (
                      <span style={{ fontSize: 10, color: '#9ab0cf' }}>{fmt(t.feed.vacMonths, { n: d.vacant_for })}</span>
                    ) : null}
                    <span
                      className="mono"
                      style={{
                        marginLeft: 'auto',
                        fontWeight: 500,
                        color: diff > 1 ? 'var(--up)' : diff < -1 ? 'var(--down)' : 'var(--text)',
                      }}
                    >
                      ¥{Math.round(rb)}→{Math.round(ra)}
                    </span>
                  </div>
                  <div
                    style={{
                      fontSize: expanded ? 12.5 : 12,
                      color: d.mentions_line ? '#F3F6FC' : '#CFD7E6',
                      marginTop: 3,
                      lineHeight: 1.5,
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
      <div style={{ fontSize: 9.5, color: 'var(--sub)', marginTop: 6, opacity: 0.75, borderTop: '1px solid rgba(36,50,74,0.6)', paddingTop: 4 }}>
        {t.feed.sampledNote}
      </div>
    </div>
  );
}
