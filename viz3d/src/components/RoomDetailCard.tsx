import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, X } from 'lucide-react';
import type { IncomeGroup, Lang, Scenario, VizDataset } from '@/types/viz';
import { readRoomState } from '@/data/loader';
import { fmt, getDict } from '@/i18n';

interface RoomDetailCardProps {
  dataset: VizDataset;
  roomId: number;
  scenario: Scenario;
  seed: number;
  month: number;
  lang: Lang;
  onClose: () => void;
  onOpenTenant: (tenantId: number) => void;
}

const GROUP_COLORS: Record<IncomeGroup, string> = {
  low: '#2DD4BF',
  mid: '#A78BFA',
  high: '#F472B6',
};

export function RoomDetailCard({
  dataset,
  roomId,
  scenario,
  seed,
  month,
  lang,
  onClose,
  onOpenTenant,
}: RoomDetailCardProps) {
  const t = getDict(lang);
  const room = dataset.rooms[roomId];
  const zone = dataset.zoneById[room.zone];
  const landlord = dataset.landlordById[room.landlord_id];

  const runActive = dataset.runs[`${scenario}_${seed}`] ?? dataset.runs[`P_${dataset.meta.default_seed}`];
  const runP = dataset.runs[`P_${seed}`] ?? runActive;
  const runS = dataset.runs[`S_${seed}`] ?? runActive;

  const [showInputs, setShowInputs] = useState(false);

  // Extract 36-month P & S rent history + active scenario tenant ribbon
  const { rentsP, rentsS, activeStates, minR, maxR } = useMemo(() => {
    const rP: number[] = [];
    const rS: number[] = [];
    const act = [];
    let lo = Infinity;
    let hi = -Infinity;
    for (let m = 1; m <= 36; m++) {
      const stP = readRoomState(runP.roomStatesBuffer, m, roomId, dataset.rooms.length);
      const stS = readRoomState(runS.roomStatesBuffer, m, roomId, dataset.rooms.length);
      const stA = readRoomState(runActive.roomStatesBuffer, m, roomId, dataset.rooms.length);
      rP.push(stP.rent);
      rS.push(stS.rent);
      act.push(stA);
      lo = Math.min(lo, stP.rent, stS.rent);
      hi = Math.max(hi, stP.rent, stS.rent);
    }
    const pad = Math.max(80, (hi - lo) * 0.2);
    return { rentsP: rP, rentsS: rS, activeStates: act, minR: Math.max(0, lo - pad), maxR: hi + pad };
  }, [runP, runS, runActive, roomId, dataset.rooms.length]);

  // All landlord pricing decisions for this room in active scenario
  const roomDecisions = useMemo(
    () =>
      runActive.decisions.decisions.filter(
        (d) => d.agent_type === 'landlord' && d.room_id === roomId
      ),
    [runActive, roomId]
  );

  // Default to the latest decision <= current month
  const defaultIdx = useMemo(() => {
    let idx = 0;
    for (let i = 0; i < roomDecisions.length; i++) {
      if (roomDecisions[i].m <= month) idx = i;
    }
    return idx;
  }, [roomDecisions, month]);

  const [decIdx, setDecIdx] = useState(defaultIdx);
  useEffect(() => {
    setDecIdx(defaultIdx);
    setShowInputs(false);
  }, [roomId, defaultIdx]);

  const curDec = roomDecisions[decIdx];

  // Build SVG paths for P solid vs S dashed
  const W = 380;
  const H = 90;
  const x = (m: number) => 8 + ((W - 16) * (m - 1)) / 35;
  const y = (v: number) => H - 10 - ((v - minR) / Math.max(1, maxR - minR)) * (H - 22);
  const pathP = rentsP.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i + 1).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const pathS = rentsS.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i + 1).toFixed(1)},${y(v).toFixed(1)}`).join('');

  // Group consecutive months of the same tenant for clickable lease blocks
  const tenantSpans = useMemo(() => {
    const spans: Array<{ startM: number; endM: number; tenantId: number; group: IncomeGroup | null; income: number }> = [];
    for (let m = 1; m <= 36; m++) {
      const st = activeStates[m - 1];
      const prev = spans[spans.length - 1];
      if (prev && prev.tenantId === st.tenantId) {
        prev.endM = m;
      } else {
        spans.push({ startM: m, endM: m, tenantId: st.tenantId, group: st.group, income: st.income });
      }
    }
    return spans;
  }, [activeStates]);

  const roomKindLabel = (t.roomKinds as Record<string, string>)[room.kind] ?? room.kind;
  const llKind = landlord ? (t.landlordKinds as Record<string, string>)[landlord.kind] ?? landlord.kind : '';
  const llRisk = landlord ? (t.landlordKinds as Record<string, string>)[landlord.risk] ?? landlord.risk : '';

  return (
    <div
      className="hud-panel amber"
      style={{
        width: '100%',
        maxWidth: 440,
        maxHeight: '100%',
        margin: '0 auto',
        padding: '13px 15px',
        display: 'flex',
        flexDirection: 'column',
        background: 'rgba(10, 16, 28, 0.95)',
        boxShadow: '0 16px 48px rgba(0, 0, 0, 0.65)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>
            {t.roomCard.room} #{room.id} · {lang === 'zh' ? zone.name : zone.name_en} ({room.zone}) ·{' '}
            <span style={{ color: 'var(--cool)' }}>{roomKindLabel}</span>
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--sub)', marginTop: 3 }}>
            {t.roomCard.landlord} #{room.landlord_id} · {llKind} · {llRisk} ·{' '}
            {fmt(t.roomCard.manages, { n: landlord?.n_rooms ?? 6 })} · {fmt(t.roomCard.stationDist, { m: room.station_dist_m })}
          </div>
        </div>
        <button type="button" className="btn-hud" style={{ padding: 4 }} onClick={onClose}>
          <X size={14} />
        </button>
      </div>

      <div style={{ height: 1, background: 'var(--line)', margin: '10px 0' }} />

      {/* 36-month P vs S Rent Trajectory */}
      <div style={{ fontSize: 10.5, color: 'var(--sub)', marginBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
        <span>{t.roomCard.rentChartTitle}</span>
        <span className="mono">
          ¥{Math.round(minR)}–{Math.round(maxR)}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 90, background: 'rgba(16,24,38,0.55)', borderRadius: 4 }}>
        <line x1={x(13)} x2={x(13)} y1={4} y2={H - 4} stroke="#FFB02E" strokeOpacity={0.45} strokeDasharray="3 2" />
        <line x1={x(25)} x2={x(25)} y1={4} y2={H - 4} stroke="#5FB4FF" strokeOpacity={0.45} strokeDasharray="3 2" />
        <text x={x(13) + 3} y={12} fontSize={8.5} fill="#FFB02E" fontFamily="monospace">
          M13
        </text>
        <text x={x(25) + 3} y={12} fontSize={8.5} fill="#5FB4FF" fontFamily="monospace">
          M25
        </text>
        <path d={pathS} fill="none" stroke="#4EA8FF" strokeWidth={1.6} strokeDasharray="4 3" />
        <path d={pathP} fill="none" stroke="#FF6B57" strokeWidth={2.0} />
        <line x1={x(month)} x2={x(month)} y1={2} y2={H - 2} stroke="#fff" strokeOpacity={0.45} />
        <circle cx={x(month)} cy={y(rentsP[month - 1])} r={3.5} fill="#FF6B57" stroke="#fff" strokeWidth={1} />
      </svg>

      {/* Tenant Occupancy Ribbon (clickable -> Tenant Card!) */}
      <div style={{ fontSize: 10.5, color: 'var(--sub)', marginTop: 10, marginBottom: 4 }}>
        {t.roomCard.tenantBarTitle}
      </div>
      <div style={{ display: 'flex', height: 22, gap: 2, borderRadius: 3, overflow: 'hidden', background: '#111A2B' }}>
        {tenantSpans.map((sp, i) => {
          const widthPct = ((sp.endM - sp.startM + 1) / 36) * 100;
          const isVac = sp.tenantId < 0;
          const bg = isVac ? '#1F2C44' : GROUP_COLORS[sp.group ?? 'mid'];
          const tooltip = isVac
            ? `M${sp.startM}–M${sp.endM}: ${t.roomCard.vacant}`
            : `M${sp.startM}–M${sp.endM}: Tenant #${sp.tenantId} (${sp.group}, ¥${Math.round(sp.income)}/m)`;
          return (
            <button
              key={i}
              type="button"
              title={tooltip}
              disabled={isVac}
              onClick={() => !isVac && onOpenTenant(sp.tenantId)}
              style={{
                width: `${widthPct}%`,
                height: '100%',
                border: 'none',
                background: bg,
                opacity: isVac ? 0.55 : 0.88,
                cursor: isVac ? 'default' : 'pointer',
                color: '#0B111C',
                fontSize: 9.5,
                fontWeight: 700,
                fontFamily: 'var(--font-mono)',
                overflow: 'hidden',
                whiteSpace: 'nowrap',
                padding: '0 2px',
              }}
            >
              {isVac ? '' : `#${sp.tenantId}`}
            </button>
          );
        })}
      </div>

      <div style={{ height: 1, background: 'var(--line)', margin: '10px 0' }} />

      {/* Decision Stepper & Verbatim LLM Reasoning */}
      <div className="hud-scroll" style={{ flex: 1 }}>
        {curDec ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
              <span className="mono" style={{ color: 'var(--announce)', fontWeight: 600 }}>
                M{String(curDec.m).padStart(2, '0')} ·{' '}
                {curDec.decision === 'renewal_offer' ? t.feed.renewal : t.feed.vacant}
              </span>
              <span className="mono" style={{ color: 'var(--text)' }}>
                ¥{Math.round(curDec.rent_before ?? 0)} → <b>¥{Math.round(curDec.rent_after ?? 0)}</b>
              </span>
              {curDec.vacant_for ? (
                <span style={{ fontSize: 10.5, color: 'var(--sub)' }}>{fmt(t.roomCard.vacantFor, { n: curDec.vacant_for })}</span>
              ) : null}
            </div>

            <div
              style={{
                padding: '9px 11px',
                background: 'rgba(22, 35, 58, 0.72)',
                borderLeft: `2.5px solid ${curDec.mentions_line ? 'var(--announce)' : 'var(--cool)'}`,
                borderRadius: '0 4px 4px 0',
                fontSize: 12.5,
                lineHeight: 1.55,
                color: '#E6ECF5',
              }}
            >
              “{curDec.reason}”
            </div>

            {/* Collapsible Raw JSON LLM Input Inspector */}
            <div style={{ marginTop: 8 }}>
              <button
                type="button"
                className="btn-hud"
                onClick={() => setShowInputs((v) => !v)}
                style={{ width: '100%', justifyContent: 'space-between' }}
              >
                <span>{showInputs ? t.roomCard.hideInputs : t.roomCard.showInputs}</span>
                {showInputs ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
              </button>
              {showInputs && curDec.inputs && (
                <pre
                  className="mono hud-scroll"
                  style={{
                    marginTop: 6,
                    padding: 8,
                    maxHeight: 165,
                    background: '#080D16',
                    border: '1px solid var(--line)',
                    borderRadius: 4,
                    fontSize: 10,
                    color: '#9EC5FF',
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-all',
                  }}
                >
                  {JSON.stringify(curDec.inputs, null, 2)}
                </pre>
              )}
            </div>

            {/* Prev / Next decision buttons */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 9 }}>
              <button
                type="button"
                className="btn-hud"
                disabled={decIdx <= 0}
                onClick={() => setDecIdx((i) => Math.max(0, i - 1))}
                style={{ opacity: decIdx <= 0 ? 0.4 : 1 }}
              >
                <ChevronLeft size={12} /> {t.roomCard.prevDec}
              </button>
              <span className="mono" style={{ fontSize: 10.5, color: 'var(--sub)' }}>
                {decIdx + 1} / {roomDecisions.length}
              </span>
              <button
                type="button"
                className="btn-hud"
                disabled={decIdx >= roomDecisions.length - 1}
                onClick={() => setDecIdx((i) => Math.min(roomDecisions.length - 1, i + 1))}
                style={{ opacity: decIdx >= roomDecisions.length - 1 ? 0.4 : 1 }}
              >
                {t.roomCard.nextDec} <ChevronRight size={12} />
              </button>
            </div>
          </>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--sub)', padding: '12px 0' }}>{t.roomCard.noDecisions}</div>
        )}
      </div>
    </div>
  );
}
