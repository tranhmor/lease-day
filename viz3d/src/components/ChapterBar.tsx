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
          <div className="meta-row kicker" style={{ fontSize: 12.5, gap: 10 }}>
            <span style={{ color: 'var(--cool)', fontWeight: 600 }}>{lang === 'zh' ? '北京' : 'BEIJING'}</span>
            <span className="sep" />
            <span>{lang === 'zh' ? 'LLM 多智能体租赁市场实验' : 'An LLM multi-agent rental market experiment'}</span>
          </div>
          <h1
            className="serif"
            style={{
              fontSize: 'clamp(40px, 4.6vw, 68px)',
              fontWeight: 600,
              lineHeight: 1.18,
              letterSpacing: '0.02em',
              marginTop: 16,
            }}
          >
            {lang === 'zh' ? '一条还没开通的地铁，' : 'A metro line that has not opened yet'}
            <br />
            {lang === 'zh' ? '会不会先抬高房租？' : 'Does it raise rents first?'}
          </h1>
          <p className="serif" style={{ fontSize: 17.5, color: 'var(--text-soft)', marginTop: 22, lineHeight: 1.75, maxWidth: 620 }}>
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
              style={{ padding: '9px 22px', fontSize: 14, color: 'var(--on-text)', background: 'var(--text)', borderColor: 'var(--text)' }}
              onClick={() => onSelectChapter(1)}
            >
              {lang === 'zh' ? '开始演示 →' : 'Start →'}
            </button>
            <button type="button" className="btn-hud ghost" style={{ padding: '9px 6px', fontSize: 13.5 }} onClick={onExitPresentation}>
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
      className="hud-panel amber"
      style={{
        width: '100%',
        padding: '8px 13px',
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
          style={{ padding: '2px 6px', opacity: chapterIndex <= 0 ? 0.35 : 1 }}
        >
          <ChevronLeft size={13} />
        </button>

        <div style={{ display: 'flex', gap: 4, flex: 1, justifyContent: 'center', flexWrap: 'wrap', minWidth: 0 }}>
          {CHAPTERS.map((c) => {
            const on = c.id === chapterIndex;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => onSelectChapter(c.id)}
                className="num"
                style={{
                  border: `1px solid ${on ? 'var(--announce)' : 'var(--line)'}`,
                  background: on ? 'color-mix(in srgb, var(--announce) 20%, transparent)' : 'var(--btn-bg)',
                  color: on ? 'var(--announce)' : 'var(--sub)',
                  boxShadow: on ? '0 0 10px color-mix(in srgb, var(--announce) 26%, transparent)' : 'none',
                  borderRadius: 5,
                  minWidth: 24,
                  padding: '2px 7px',
                  fontSize: 11,
                  fontWeight: on ? 600 : 400,
                  lineHeight: 1.25,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
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
          style={{ padding: '2px 6px', opacity: chapterIndex >= CHAPTERS.length - 1 ? 0.35 : 1 }}
        >
          <ChevronRight size={13} />
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
        <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 5, whiteSpace: 'nowrap', flexShrink: 0 }}>
          <span className="tag-id" style={{ fontSize: 12, color: 'var(--announce)' }}>
            {ch.code}
          </span>
          <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--announce)' }}>
            {ch.title}
          </span>
        </span>
        <span style={{ fontSize: 12, color: 'var(--text)', lineHeight: 1.45, minWidth: 0 }}>
          {ch.narration}
        </span>
      </div>
    </div>
  );
}
