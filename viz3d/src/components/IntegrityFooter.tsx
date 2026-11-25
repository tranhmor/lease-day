import type { Lang, MonthlyCIData, VizMeta } from '@/types/viz';
import { fmt, getDict } from '@/i18n';

interface IntegrityFooterProps {
  meta: VizMeta;
  monthlyCI: MonthlyCIData;
  lang: Lang;
  autoDegradedNotice: boolean;
  onRestoreQuality: () => void;
}

/**
 * §9 Academic Integrity Persistent Footer & Watermark Bar (clean 1px hairline separators, zero middots).
 */
export function IntegrityFooter({
  meta,
  monthlyCI,
  lang,
  autoDegradedNotice,
  onRestoreQuality,
}: IntegrityFooterProps) {
  const t = getDict(lang);
  const psStr = `${monthlyCI.median_seed_m24_ps >= 0 ? '+' : '−'}${Math.abs(monthlyCI.median_seed_m24_ps).toFixed(2)}`;

  return (
    <>
      {autoDegradedNotice && (
        <button
          type="button"
          onClick={onRestoreQuality}
          style={{
            position: 'absolute',
            right: 24,
            bottom: 32,
            zIndex: 50,
            background: 'var(--panel-solid)',
            border: '1px solid var(--announce)',
            color: 'var(--announce)',
            fontSize: 11,
            padding: '4px 10px',
            borderRadius: 6,
            cursor: 'pointer',
          }}
        >
          {t.export.autoDegraded}
        </button>
      )}

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: 26,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          fontSize: 11,
          letterSpacing: '0.015em',
          color: 'var(--sub)',
          background: 'var(--panel-solid)',
          borderTop: '1px solid var(--line)',
          pointerEvents: 'none',
          zIndex: 24,
          padding: '0 24px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {meta.is_illustrative && (
          <>
            <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{t.footer.illustrative}</span>
            <span className="sep" />
          </>
        )}
        <span>{t.footer.schematic}</span>
        <span className="sep" />
        <span>{t.footer.hypothetical}</span>
        <span className="sep" />
        <span className="num">{fmt(t.footer.medianSeed, { seed: meta.default_seed, val: psStr })}</span>
        <span className="sep" />
        <span>{fmt(t.footer.source, { src: meta.source_label })}</span>
      </div>
    </>
  );
}
