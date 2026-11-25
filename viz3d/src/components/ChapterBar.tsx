import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { AppMode, Lang } from '@/types/viz';
import { CHAPTERS } from '@/chapters/script';
import { getDict } from '@/i18n';

interface ChapterBarProps {
  mode: AppMode;
  chapterIndex: number;
  lang: Lang;
  onSelectChapter: (idx: number) => void;
  onExitPresentation: () => void;
}

export function ChapterBar({ mode, chapterIndex, lang, onSelectChapter, onExitPresentation }: ChapterBarProps) {
  const t = getDict(lang);
  const ch = t.chapters[chapterIndex] ?? t.chapters[0];

  // Chapter 0 Intro Title Card (§3 Ch0: Only show title over sweeping 3D city!)
  if (mode === 'presentation' && chapterIndex === 0) {
    return (
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
          zIndex: 35,
          background: 'radial-gradient(ellipse at center, rgba(11,17,28,0.12) 0%, rgba(11,17,28,0.65) 100%)',
        }}
      >
        <div
          style={{
            fontSize: 13,
            letterSpacing: '0.35em',
            color: 'var(--announce)',
            fontWeight: 600,
            marginBottom: 14,
          }}
        >
          BEIJING · LEASE DAY v0.7
        </div>
        <h1
          style={{
            fontSize: 'clamp(36px, 5vw, 66px)',
            fontWeight: 200,
            letterSpacing: '0.06em',
            textAlign: 'center',
            textShadow: '0 8px 36px rgba(0,0,0,0.85)',
          }}
        >
          {lang === 'zh' ? '到期日 · 租赁市场三维回放' : 'Lease Day · 3D Rental Market Replay'}
        </h1>
        <p style={{ fontSize: 18, color: '#C2D2E8', marginTop: 14, fontWeight: 300, textAlign: 'center' }}>
          {t.introSubtitle}
        </p>
        <p style={{ fontSize: 13, color: 'var(--sub)', marginTop: 28, maxWidth: 640, textAlign: 'center', lineHeight: 1.6 }}>
          {ch.narration}
        </p>
        <div style={{ display: 'flex', gap: 12, marginTop: 32, pointerEvents: 'auto' }}>
          <button
            type="button"
            className="btn-hud amber-active"
            style={{ padding: '9px 22px', fontSize: 13 }}
            onClick={() => onSelectChapter(1)}
          >
            {lang === 'zh' ? '开始演示（→）' : 'Start Presentation (→)'}
          </button>
          <button
            type="button"
            className="btn-hud"
            style={{ padding: '9px 18px', fontSize: 13 }}
            onClick={onExitPresentation}
          >
            {lang === 'zh' ? '自由探索（Esc）' : 'Explore Freely (Esc)'}
          </button>
        </div>
      </div>
    );
  }

  if (mode !== 'presentation') return null;

  return (
    <div
      className="hud-panel amber"
      style={{
        width: '100%',
        padding: '8px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 5,
        flexShrink: 0,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <button
          type="button"
          className="btn-hud"
          disabled={chapterIndex <= 0}
          onClick={() => onSelectChapter(Math.max(0, chapterIndex - 1))}
          style={{ padding: '2px 6px', opacity: chapterIndex <= 0 ? 0.4 : 1 }}
        >
          <ChevronLeft size={13} />
        </button>

        <div style={{ display: 'flex', gap: 4, flex: 1, justifyContent: 'center', flexWrap: 'wrap' }}>
          {CHAPTERS.map((c) => {
            const on = c.id === chapterIndex;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => onSelectChapter(c.id)}
                style={{
                  border: `1px solid ${on ? 'var(--announce)' : 'var(--line)'}`,
                  background: on ? 'rgba(255, 176, 46, 0.2)' : 'rgba(11, 17, 28, 0.6)',
                  color: on ? 'var(--announce)' : 'var(--sub)',
                  borderRadius: 3,
                  padding: '2px 7px',
                  fontSize: 10.5,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {c.id}
              </button>
            );
          })}
        </div>

        <button
          type="button"
          className="btn-hud"
          disabled={chapterIndex >= CHAPTERS.length - 1}
          onClick={() => onSelectChapter(Math.min(CHAPTERS.length - 1, chapterIndex + 1))}
          style={{ padding: '2px 6px', opacity: chapterIndex >= CHAPTERS.length - 1 ? 0.4 : 1 }}
        >
          <ChevronRight size={13} />
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--announce)', whiteSpace: 'nowrap' }}>{ch.title}</span>
        <span style={{ fontSize: 12, color: '#E2EAF7', lineHeight: 1.45 }}>{ch.narration}</span>
      </div>
    </div>
  );
}
