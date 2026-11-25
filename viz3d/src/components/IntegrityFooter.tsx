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
 * §9 Academic Integrity Persistent Footer & Watermark Bar:
 * - Illustrative watermark whenever is_illustrative = true (§9.1)
 * - Schematic intra-zone positions notice (§9.6)
 * - Hypothetical East Express notice (§9.5)
 * - Median seed identifier (§9.3) + data source
 */
export function IntegrityFooter({
  meta,
  monthlyCI,
  lang,
  autoDegradedNotice,
  onRestoreQuality,
}: IntegrityFooterProps) {
  const t = getDict(lang);
  const psStr = `${monthlyCI.median_seed_m24_ps >= 0 ? '+' : ''}${monthlyCI.median_seed_m24_ps.toFixed(2)}`;

  return (
    <>
      {autoDegradedNotice && (
        <button
          type="button"
          onClick={onRestoreQuality}
          style={{
            position: 'absolute',
            right: 24,
            bottom: 30,
            zIndex: 50,
            background: 'color-mix(in srgb, var(--announce) 16%, transparent)',
            border: '1px solid var(--announce)',
            color: 'var(--announce)',
            fontSize: 10.5,
            padding: '4px 10px',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          ⚡ {t.export.autoDegraded}
        </button>
      )}

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 5,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
          fontSize: 10.5,
          color: 'var(--footer-text)',
          pointerEvents: 'none',
          zIndex: 24,
          padding: '0 24px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {meta.is_illustrative && (
          <span
            style={{
              background: 'color-mix(in srgb, var(--announce) 18%, transparent)',
              border: '1px solid color-mix(in srgb, var(--announce) 60%, transparent)',
              color: 'var(--announce)',
              padding: '1px 7px',
              borderRadius: 3,
              fontWeight: 600,
            }}
          >
            ⚠ {t.footer.illustrative}
          </span>
        )}
        <span>{t.footer.schematic}</span>
        <span>·</span>
        <span>{t.footer.hypothetical}</span>
        <span>·</span>
        <span className="mono">{fmt(t.footer.medianSeed, { seed: meta.default_seed, val: psStr })}</span>
        <span>·</span>
        <span>{fmt(t.footer.source, { src: meta.source_label })}</span>
      </div>
    </>
  );
}
