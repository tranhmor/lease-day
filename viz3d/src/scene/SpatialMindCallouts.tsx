import { useScenePalette } from '@/theme';
import { useMemo } from 'react';
import { Html } from '@react-three/drei';
import type { DecisionRecord, Lang, RoomStatic, ZoneInfo } from '@/types/viz';

interface SpatialMindCalloutsProps {
  month: number;
  decisions: DecisionRecord[];
  rooms: RoomStatic[];
  zoneById: Record<string, ZoneInfo>;
  mentionKeywords: string[];
  lang: Lang;
  visible: boolean;
  onSelectRoom?: (roomId: number) => void;
}

function summarizeSnippet(reason: string, keywords: string[]): string {
  if (!reason) return '';
  // Prefer a short clause containing a matched transit keyword
  const clauses = reason.split(/[，。；、,.;]/).map((s) => s.trim()).filter(Boolean);
  const hit = clauses.find((c) => keywords.some((kw) => c.includes(kw)));
  const pick = hit || clauses[0] || reason;
  return pick.length > 18 ? pick.slice(0, 17) + '…' : pick;
}

/**
 * Visual Style 1 (Combo D): Floating Spatial Mind Callouts anchored with delicate gossamer stems
 * directly above rooms whose LLM landlord cited the new East Express Line (max 3 per month, zero clutter).
 */
export function SpatialMindCallouts({
  month,
  decisions,
  rooms,
  zoneById,
  mentionKeywords,
  lang,
  visible,
  onSelectRoom,
}: SpatialMindCalloutsProps) {
  const pal = useScenePalette();
  const callouts = useMemo(() => {
    if (!visible) return [];
    const cand = decisions.filter(
      (d) =>
        d.m === month &&
        d.agent_type === 'landlord' &&
        d.room_id !== null &&
        (d.decision === 'renewal_offer' || d.decision === 'price_vacant') &&
        d.mentions_line
    );
    // Keep at most 3 spatially spaced callouts (prioritizing treated zones Z05 / Z11)
    const sorted = [...cand].sort((a, b) => {
      const ta = a.zone === 'Z05' || a.zone === 'Z11' ? 0 : 1;
      const tb = b.zone === 'Z05' || b.zone === 'Z11' ? 0 : 1;
      return ta - tb;
    });
    const picked: Array<{
      roomId: number;
      x: number;
      z: number;
      y: number;
      zoneName: string;
      deltaPct: string;
      snippet: string;
    }> = [];

    for (const d of sorted) {
      if (picked.length >= 3) break;
      const room = rooms[d.room_id!];
      if (!room) continue;
      // Avoid stacking two callouts on top of each other in 3D space
      const tooClose = picked.some(
        (p) => Math.hypot(p.x - room.layout_xy[0], p.z - room.layout_xy[1]) < 2.2
      );
      if (tooClose) continue;
      const rb = d.rent_before ?? room.start_rent;
      const ra = d.rent_after ?? rb;
      const pct = rb > 0 ? ((ra - rb) / rb) * 100 : 0;
      const zInfo = d.zone ? zoneById[d.zone] : undefined;
      picked.push({
        roomId: room.id,
        x: room.layout_xy[0],
        z: room.layout_xy[1],
        y: 2.3 + picked.length * 0.75,
        zoneName: zInfo ? (lang === 'zh' ? zInfo.name : zInfo.name_en) : d.zone || '',
        deltaPct: `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`,
        snippet: summarizeSnippet(d.reason, mentionKeywords),
      });
    }
    return picked;
  }, [visible, decisions, month, rooms, zoneById, mentionKeywords, lang]);

  if (!visible || callouts.length === 0) return null;

  return (
    <group name="Style1_spatial_mind_callouts">
      {callouts.map((c) => (
        <group key={c.roomId}>
          {/* Ultra-thin vertical gossamer stem from room up to floating thought tag */}
          <mesh position={[c.x, c.y / 2, c.z]}>
            <cylinderGeometry args={[0.008, 0.008, c.y, 4]} />
            <meshBasicMaterial color={pal.announce} transparent opacity={0.55} />
          </mesh>
          <Html position={[c.x, c.y + 0.15, c.z]} center zIndexRange={[7, 0]}>
            <div
              onClick={(e) => {
                e.stopPropagation();
                onSelectRoom?.(c.roomId);
              }}
              style={{
                pointerEvents: 'auto',
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                background: 'var(--panel-strong)',
                backdropFilter: 'blur(8px)',
                border: '1px solid color-mix(in srgb, var(--accent) 45%, transparent)',
                borderRadius: 6,
                boxShadow: '0 0 12px color-mix(in srgb, var(--accent) 30%, transparent)',
                padding: '4px 10px',
                maxWidth: 260,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                transform: 'translateY(-100%)',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 12,
              }}
            >
              <span style={{ color: 'var(--text)', fontWeight: 600 }}>{c.zoneName}</span>
              <span className="num" style={{ color: 'var(--sub)', fontSize: 11 }}>
                {c.deltaPct}
              </span>
              <span className="serif" style={{ color: 'var(--text-soft)', overflow: 'hidden', textOverflow: 'ellipsis' }}>“{c.snippet}”</span>
            </div>
          </Html>
        </group>
      ))}
    </group>
  );
}
