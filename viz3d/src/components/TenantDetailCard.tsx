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

  const group: IncomeGroup =
    tenantDecisions[0]?.tenant_group ?? tenantEvents[0]?.income_group ?? 'mid';
  const income = tenantDecisions[0]?.tenant_income ?? tenantEvents[0]?.income ?? 0;

  return (
    <div
      className="hud-panel"
      style={{
        width: '100%',
        maxWidth: 440,
        maxHeight: '100%',
        margin: '0 auto',
        padding: '13px 15px',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--panel-strong)',
        boxShadow: 'var(--shadow-strong)',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button type="button" className="btn-hud" onClick={onBackToRoom}>
            <ArrowLeft size={12} /> {t.tenantCard.backToRoom}
          </button>
          <span style={{ fontSize: 15, fontWeight: 600 }}>
            {t.tenantCard.title} #{tenantId}
          </span>
        </div>
        <button type="button" className="btn-hud" style={{ padding: 4 }} onClick={onClose}>
          <X size={14} />
        </button>
      </div>

      {/* Tenant Summary Chips */}
      <div style={{ display: 'flex', gap: 10, marginTop: 10, fontSize: 12 }}>
        <span
          style={{
            padding: '3px 9px',
            borderRadius: 4,
            background: `color-mix(in srgb, ${GROUP_COLORS[group]} 13%, transparent)`,
            color: GROUP_COLORS[group],
            border: `1px solid color-mix(in srgb, ${GROUP_COLORS[group]} 40%, transparent)`,
            fontWeight: 600,
          }}
        >
          {t.tenantCard.groups[group]}
        </span>
        {income > 0 && (
          <span className="mono" style={{ padding: '3px 8px', color: 'var(--text)' }}>
            {t.tenantCard.income}: ¥{Math.round(income).toLocaleString()}
          </span>
        )}
      </div>

      <div style={{ height: 1, background: 'var(--line)', margin: '10px 0' }} />

      <div style={{ fontSize: 11.5, color: 'var(--sub)', marginBottom: 6 }}>{t.tenantCard.decisionsTitle}</div>

      <div className="hud-scroll" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {tenantDecisions.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--sub)', padding: '12px 0' }}>{t.tenantCard.noDecisions}</div>
        ) : (
          tenantDecisions.map((d, idx) => (
            <div
              key={idx}
              style={{
                padding: '10px 11px',
                background: 'var(--panel-inset)',
                border: '1px solid var(--line)',
                borderRadius: 4,
                fontSize: 12,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span className="mono" style={{ color: 'var(--cool)', fontWeight: 600 }}>
                  M{String(d.m).padStart(2, '0')} · {d.decision}
                </span>
                <span className="mono" style={{ color: 'var(--announce)' }}>
                  {t.tenantCard.action}: {d.action}
                </span>
              </div>

              {/* Candidate Rooms Evaluated */}
              {d.candidates && d.candidates.length > 0 && (
                <div style={{ marginBottom: 6 }}>
                  <div style={{ fontSize: 10, color: 'var(--sub)', marginBottom: 3 }}>{t.tenantCard.candidates}:</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {d.candidates.map((c, ci) => {
                      const applied = d.apply?.some((a) => a.room_id === c.room_id);
                      const z = c.zone ? dataset.zoneById[c.zone] : undefined;
                      return (
                        <button
                          key={ci}
                          type="button"
                          onClick={() => c.room_id !== undefined && onSelectRoom(c.room_id)}
                          style={{
                            border: `1px solid ${applied ? 'var(--announce)' : 'var(--line)'}`,
                            background: applied ? 'color-mix(in srgb, var(--announce) 16%, transparent)' : 'var(--panel-inset-2)',
                            color: applied ? 'var(--announce)' : 'var(--sub)',
                            borderRadius: 3,
                            padding: '2px 6px',
                            fontSize: 10,
                            cursor: 'pointer',
                          }}
                        >
                          #{c.room_id} {z ? (lang === 'zh' ? z.name : z.name_en) : c.zone} · ¥{Math.round(c.rent ?? 0)}
                          {c.min != null ? ` · ${c.min}m` : ''}
                          {applied ? ' ★' : ''}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div style={{ color: 'var(--text-soft)', lineHeight: 1.5 }}>“{d.reason}”</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
