import { useMemo } from 'react';
import { ArrowLeft, X } from 'lucide-react';
import type { IncomeGroup, Lang, Scenario, VizDataset } from '@/types/viz';
import { getDict } from '@/i18n';

interface TenantDetailCardProps {
  dataset: VizDataset;
  tenantId: number;
  scenario: Scenario;
  seed: number;
  lang: Lang;
  onBackToRoom: () => void;
  onClose: () => void;
  onSelectRoom: (roomId: number) => void;
}

const GROUP_COLORS: Record<IncomeGroup, string> = {
  low: 'var(--inc-low)',
  mid: 'var(--inc-mid)',
  high: 'var(--inc-high)',
};

export function TenantDetailCard({
  dataset,
  tenantId,
  scenario,
  seed,
  lang,
  onBackToRoom,
  onClose,
  onSelectRoom,
}: TenantDetailCardProps) {
  const t = getDict(lang);
  const run = dataset.runs[`${scenario}_${seed}`] ?? dataset.runs[`P_${dataset.meta.default_seed}`];

  const tenantDecisions = useMemo(
    () => run.decisions.decisions.filter((d) => d.agent_type === 'tenant' && d.agent_id === tenantId),
    [run, tenantId]
  );

  const tenantEvents = useMemo(
    () => run.events.filter((e) => e.tenant_id === tenantId),
    [run, tenantId]
  );

  const group: IncomeGroup = tenantDecisions[0]?.tenant_group ?? tenantEvents[0]?.income_group ?? 'mid';
  const income = tenantDecisions[0]?.tenant_income ?? tenantEvents[0]?.income ?? 0;

  return (
    <div
      className="hud-panel accent-cool"
      style={{
        width: '100%',
        maxWidth: 444,
        maxHeight: '100%',
        margin: '0 auto',
        padding: '15px 17px',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--panel-strong)',
        boxShadow: 'var(--shadow-strong), var(--glass-rim)',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button type="button" className="btn-hud" onClick={onBackToRoom}>
            <ArrowLeft size={12} /> {t.tenantCard.backToRoom}
          </button>
          <span className="serif" style={{ fontSize: 15.5, fontWeight: 600 }}>
            {t.tenantCard.title} <span className="num">#{tenantId}</span>
          </span>
        </div>
        <button type="button" className="btn-hud" style={{ padding: 4 }} onClick={onClose}>
          <X size={14} />
        </button>
      </div>

      {/* Tenant Summary Chips */}
      <div className="meta-row" style={{ gap: 10, marginTop: 11, fontSize: 12 }}>
        <span
          style={{
            padding: '2.5px 9px',
            borderRadius: 4,
            background: `color-mix(in srgb, ${GROUP_COLORS[group]} 15%, transparent)`,
            color: GROUP_COLORS[group],
            border: `1px solid color-mix(in srgb, ${GROUP_COLORS[group]} 42%, transparent)`,
            fontWeight: 600,
            fontSize: 11.5,
          }}
        >
          {t.tenantCard.groups[group]}
        </span>
        {income > 0 && (
          <span className="num" style={{ color: 'var(--text)', fontSize: 12.5 }}>
            <span style={{ color: 'var(--sub)', marginRight: 5, fontFamily: 'var(--font-sans)', fontSize: 11.5 }}>
              {t.tenantCard.income}
            </span>
            ¥{Math.round(income).toLocaleString()}
          </span>
        )}
      </div>

      <div style={{ height: 1, background: 'var(--line-soft)', margin: '11px 0' }} />

      <div style={{ fontSize: 11.5, color: 'var(--sub)', marginBottom: 7 }}>{t.tenantCard.decisionsTitle}</div>

      <div className="hud-scroll" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {tenantDecisions.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--sub)', padding: '12px 0' }}>{t.tenantCard.noDecisions}</div>
        ) : (
          tenantDecisions.map((d, idx) => (
            <div
              key={idx}
              style={{
                padding: '10px 12px',
                background: 'var(--inset)',
                border: '1px solid var(--line-soft)',
                borderRadius: 6,
                fontSize: 12,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 6 }}>
                <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 7 }}>
                  <span className="tag-id" style={{ color: 'var(--cool)' }}>
                    M{String(d.m).padStart(2, '0')}
                  </span>
                  <span className="mono" style={{ fontSize: 11, color: 'var(--sub)' }}>
                    {d.decision}
                  </span>
                </span>
                <span style={{ color: 'var(--announce)', fontSize: 11.5, fontWeight: 500 }}>
                  {t.tenantCard.action}: {d.action}
                </span>
              </div>

              {/* Candidate Rooms Evaluated — crisp spacing, zero middots */}
              {d.candidates && d.candidates.length > 0 && (
                <div style={{ marginBottom: 7 }}>
                  <div style={{ fontSize: 10.5, color: 'var(--sub)', marginBottom: 4 }}>{t.tenantCard.candidates}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {d.candidates.map((c, ci) => {
                      const applied = d.apply?.some((a) => a.room_id === c.room_id);
                      const z = c.zone ? dataset.zoneById[c.zone] : undefined;
                      return (
                        <button
                          key={ci}
                          type="button"
                          onClick={() => c.room_id !== undefined && onSelectRoom(c.room_id)}
                          style={{
                            display: 'inline-flex',
                            alignItems: 'baseline',
                            gap: 5,
                            border: `1px solid ${applied ? 'var(--announce)' : 'var(--line)'}`,
                            background: applied ? 'color-mix(in srgb, var(--announce) 14%, transparent)' : 'var(--panel-solid)',
                            color: applied ? 'var(--announce)' : 'var(--text-soft)',
                            borderRadius: 4,
                            padding: '2.5px 7px',
                            fontSize: 10.5,
                            cursor: 'pointer',
                          }}
                        >
                          <span className="num" style={{ opacity: 0.7 }}>
                            #{c.room_id}
                          </span>
                          <span>{z ? (lang === 'zh' ? z.name : z.name_en) : c.zone}</span>
                          <span className="num" style={{ fontWeight: 500 }}>
                            ¥{Math.round(c.rent ?? 0)}
                          </span>
                          {c.min != null && (
                            <span className="num" style={{ opacity: 0.75 }}>
                              {c.min}m
                            </span>
                          )}
                          {applied && <span>★</span>}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="serif" style={{ color: 'var(--text)', lineHeight: 1.62, fontSize: 13 }}>
                “{d.reason}”
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
