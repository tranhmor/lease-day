import { useRef, useState } from 'react';
import { Camera, Download, Film, Square, X } from 'lucide-react';
import type { Lang, Scenario, ViewMode, VizMeta } from '@/types/viz';
import type { SceneHandle } from '@/scene/CityScene';
import { getDict } from '@/i18n';

interface ExportModalProps {
  meta: VizMeta;
  month: number;
  scenario: Scenario;
  viewMode: ViewMode;
  lang: Lang;
  sceneHandleRef: React.MutableRefObject<SceneHandle | null>;
  onClose: () => void;
}

export function ExportModal({ meta, month, scenario, viewMode, lang, sceneHandleRef, onClose }: ExportModalProps) {
  const t = getDict(lang);
  const [recording, setRecording] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const watermarkLines = () => {
    const lines: string[] = [];
    if (meta.is_illustrative) {
      lines.push(t.footer.illustrative);
    }
    lines.push(
      `Lease Day v${meta.version} · M${String(month).padStart(2, '0')}/36 · ${
        viewMode === 'split' ? 'Split S | P' : `Scenario ${scenario}`
      } · Seed #${meta.default_seed} · ${meta.source_label} · ${t.footer.schematic} · ${t.footer.hypothetical}`
    );
    return lines;
  };

  const triggerDownload = (dataUrl: string, filename: string) => {
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  const handleExportPNG = (w: number, h: number) => {
    const handle = sceneHandleRef.current;
    if (!handle) {
      setStatusMsg(lang === 'zh' ? '当前处于 2D 降级模式，请切回 3D 后导出 4K 静帧。' : 'Switch back to 3D mode for 4K WebGL PNG export.');
      return;
    }
    const url = handle.exportPNG(w, h, watermarkLines());
    if (url) {
      const tag = viewMode === 'split' ? 'split_SP' : scenario;
      triggerDownload(url, `lease_day_v07_M${String(month).padStart(2, '0')}_${tag}_${w}x${h}.png`);
      setStatusMsg(`${lang === 'zh' ? '已导出' : 'Saved'} ${w}×${h} PNG`);
    }
  };

  const toggleRecording = () => {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    const canvas = sceneHandleRef.current?.getCanvas();
    if (!canvas || typeof MediaRecorder === 'undefined') {
      setStatusMsg(lang === 'zh' ? '浏览器不支持 canvas 录制。' : 'MediaRecorder unavailable on this canvas.');
      return;
    }
    const stream = canvas.captureStream(30);
    const mime = MediaRecorder.isTypeSupported('video/webm;codecs=vp9') ? 'video/webm;codecs=vp9' : 'video/webm';
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8_000_000 });
    chunksRef.current = [];
    rec.ondataavailable = (ev) => {
      if (ev.data.size > 0) chunksRef.current.push(ev.data);
    };
    rec.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mime });
      const url = URL.createObjectURL(blob);
      triggerDownload(url, `lease_day_v07_replay_${scenario}.webm`);
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      setStatusMsg(lang === 'zh' ? '已保存录屏 WebM（可直接插入 PPT 或转 MP4）' : 'Saved WebM capture');
    };
    rec.start();
    recorderRef.current = rec;
    setRecording(true);
    setStatusMsg(t.export.recording);
  };

  return (
    <div
      className="hud-panel amber"
      style={{
        position: 'absolute',
        right: 18,
        top: 152,
        width: 340,
        padding: '14px 16px',
        zIndex: 55,
        background: 'rgba(10, 16, 28, 0.96)',
        boxShadow: '0 16px 42px rgba(0,0,0,0.65)',
      }}
    >
      <div className="panel-header">
        <span>{t.modes.export}</span>
        <button type="button" className="btn-hud" style={{ padding: 3 }} onClick={onClose}>
          <X size={13} />
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button type="button" className="btn-hud amber-active" style={{ justifyContent: 'center', padding: '8px 12px' }} onClick={() => handleExportPNG(3840, 2160)}>
          <Camera size={13} /> {t.export.png4k} (3840 × 2160)
        </button>

        <button type="button" className="btn-hud" style={{ justifyContent: 'center', padding: '7px 12px' }} onClick={() => handleExportPNG(1920, 1080)}>
          <Download size={13} /> {t.export.pngScreen} (1920 × 1080)
        </button>

        <button
          type="button"
          className={`btn-hud ${recording ? 'amber-active' : ''}`}
          style={{ justifyContent: 'center', padding: '7px 12px' }}
          onClick={toggleRecording}
        >
          {recording ? <Square size={12} /> : <Film size={13} />}
          {recording ? t.export.stopRecord : t.export.record}
        </button>
      </div>

      <div style={{ fontSize: 10.5, color: 'var(--sub)', marginTop: 10, lineHeight: 1.5 }}>
        {lang === 'zh'
          ? '支持 URL 导出参数：?export=1&month=18&scen=P&chapter=4&w=3840&h=2160（导出静帧自动叠加来源与示意水印）'
          : 'URL export params supported: ?export=1&month=18&scen=P&chapter=4&w=3840&h=2160 (watermarks auto-embedded)'}
      </div>

      {statusMsg && (
        <div className="mono" style={{ fontSize: 11, color: 'var(--announce)', marginTop: 8 }}>
          ✓ {statusMsg}
        </div>
      )}
    </div>
  );
}
