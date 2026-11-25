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
          alignItems: 'flex-start',
          justifyContent: 'center',
          paddingLeft: '8vw',
          pointerEvents: 'none',
          zIndex: 35,
          background: 'linear-gradient(90deg, var(--veil) 0%, var(--veil-mid) 48%, var(--veil-0) 100%)',
        }}
      >
        <div style={{ maxWidth: 760, padding: '0 32px', textAlign: 'left' }}>
          <div className="kicker" style={{ fontSize: 13, color: 'var(--sub)' }}>
            {lang === 'zh' ? '北京 · LLM 多智能体租赁市场实验' : 'Beijing · an LLM multi-agent rental market experiment'}
          </div>
          <h1
            className="serif"
            style={{
              fontSize: 'clamp(40px, 4.6vw, 68px)',
              fontWeight: 600,
              lineHeight: 1.15,
              marginTop: 14,
            }}
          >
            {lang === 'zh' ? '一条还没开通的地铁，' : 'A metro line that has not opened yet'}
            <br />
            {lang === 'zh' ? '会不会先抬高房租？' : 'Does it raise rents first?'}
          </h1>
          <p className="serif" style={{ fontSize: 18, color: 'var(--text-soft)', marginTop: 22, lineHeight: 1.7, maxWidth: 620 }}>
            {ch.narration}
          </p>
          <div
            style={{
              display: 'flex',
              gap: 18,
              marginTop: 32,
              paddingTop: 18,
              borderTop: '1px solid var(--line)',
              pointerEvents: 'auto',
              alignItems: 'center',
            }}
          >
            <button
              type="button"
              className="btn-hud"
              style={{ padding: '9px 20px', fontSize: 14, color: 'var(--on-text)', background: 'var(--text)', borderColor: 'var(--text)' }}
              onClick={() => onSelectChapter(1)}
            >
              {lang === 'zh' ? '开始演示 →' : 'Start →'}
            </button>
            <button type="button" className="btn-hud" style={{ padding: '9px 4px', fontSize: 14, border: 'none' }} onClick={onExitPresentation}>
              {lang === 'zh' ? '自由探索（Esc）' : 'Explore freely (Esc)'}
            </button>
          </div>
        </div>
      </div>
    );
  }
  if (mode !== 'presentation') return null;

  return (
    <div
      className="hud-panel"
      style={{
        width: '100%',
        padding: '10px 16px',
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
          style={{ padding: '2px 6px', border: 'none', opacity: chapterIndex <= 0 ? 0.3 : 1 }}
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
                  border: 'none',
                  borderBottom: `1.5px solid ${on ? 'var(--text)' : 'transparent'}`,
                  background: 'transparent',
                  color: on ? 'var(--text)' : 'var(--faint)',
                  padding: '1px 6px 3px',
                  fontSize: 12,
                  cursor: 'pointer',
                  fontFamily: 'var(--font-sans)',
                  fontVariantNumeric: 'tabular-nums',
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
          style={{ padding: '2px 6px', border: 'none', opacity: chapterIndex >= CHAPTERS.length - 1 ? 0.3 : 1 }}
        >
          <ChevronRight size={13} />
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span className="serif" style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)', whiteSpace: 'nowrap' }}>{ch.title}</span>
        <span className="serif" style={{ fontSize: 14, color: 'var(--text-soft)', lineHeight: 1.55 }}>{ch.narration}</span>
      </div>
    </div>
  );
}
