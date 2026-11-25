const parseCell = (v) => (typeof v === 'string' ? JSON.parse(v) : v);
const yes = (v) => v === true || v === 'true';
const MODE_NAMES = ['地铁', '骑车接地铁', '公交', '公交换乘', '电动车', '自行车', '步行', '私家车', '打车'];
const MODE_CLASS = ['subway', 'subway', 'bus', 'bus', 'bike', 'bike', 'bike', 'car', 'car'];
const GROUP_NAMES = ['较低收入', '中等收入', '较高收入'];
const COMMUTE_RANGE = [20, 110];
const RENT_RANGE = 0.1;
const STEP_MS = 850;
const quiet = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const S = {arm: 'C', frame: 25, mode: 'commute', playing: false, data: null, frames: {}, map: null, W: 0, H: 0, dpr: 1, base: null, pal: null, anim: null, raf: 0, hover: null, stats: new Set(), feeds: new Set(), legends: new Set()};

function loadData() {
  const ids = ['replay', 'replay_rooms', 'replay_people', 'zones', 'metro', 'map', 'levels'];
  const got = ids.map((id) => dash.data(id));
  if (got.some((g) => g.status !== 'ok')) return null;
  if (S.data) return S.data;
  const [replay, rooms, people, zones, metro, map, levels] = got.map((g) => g.data);
  const zoneList = zones.map((z) => ({id: z.zone, name: z.name, x: Number(z.x), y: Number(z.y), r: Number(z.r), lx: Number(z.lx), ly: Number(z.ly), major: yes(z.major), treated: yes(z.treated), rooms: Number(z.rooms)}));
  const zoneById = new Map(zoneList.map((z) => [z.id, z]));
  const roomList = rooms.map((r) => ({i: Number(r.room), zone: zoneById.get(r.zone), start: Number(r.start), x: Number(r.x), y: Number(r.y)})).sort((a, b) => a.i - b.i);
  S.data = {
    replay,
    rooms: roomList,
    people: new Map(people.map((p) => [p.arm, parseCell(p.people)])),
    zones: zoneList,
    metro: metro.map((l) => parseCell(l.points)),
    width: Number(map[0].width),
    height: Number(map[0].height),
    cbd: [Number(map[0].cbd_x), Number(map[0].cbd_y)],
    opens: Number(levels.find((r) => r.key === 'opens').value),
    last: Number(levels.find((r) => r.key === 'months').value),
  };
  return S.data;
}

function framesOf(arm) {
  if (S.frames[arm]) return S.frames[arm];
  const d = S.data;
  const n = d.rooms.length;
  const who = new Int16Array(n).fill(-1);
  const rent = new Int32Array(n);
  const mode = new Int8Array(n).fill(-1);
  const mins = new Int16Array(n);
  const rows = d.replay.filter((r) => r.arm === arm).sort((a, b) => Number(a.month) - Number(b.month));
  S.frames[arm] = rows.map((r) => {
    parseCell(r.rooms).forEach(([i, t, money, way, minutes]) => {
      who[i] = t;
      rent[i] = money;
      mode[i] = way;
      mins[i] = minutes;
    });
    return {who: who.slice(), rent: rent.slice(), mode: mode.slice(), mins: mins.slice(), events: parseCell(r.events), renew: parseCell(r.renew)};
  });
  return S.frames[arm];
}

// ----- colours: the canvas cannot read tokens, so resolve them through a hidden element -----
function readPalette() {
  const probe = S.map.probe;
  const css = (value) => {
    probe.style.color = '';
    probe.style.color = value;
    return getComputedStyle(probe).color;
  };
  const channels = css('var(--color-bg)').match(/[\d.]+/g) || ['255', '255', '255'];
  const scale = channels.slice(0, 3).every((v) => Number(v) <= 1) ? 255 : 1;
  const light = 0.2126 * channels[0] * scale + 0.7152 * channels[1] * scale + 0.0722 * channels[2] * scale;
  const dark = light < 128;
  S.pal = {
    dark,
    fg: css('var(--color-fg)'),
    muted: css('var(--color-fg-muted)'),
    grid: css('var(--cds-chart-grid)'),
    axis: css('var(--cds-chart-axis)'),
    disc: css('var(--color-bg)'),
    panel: css('var(--color-panel)'),
    bad: css('var(--cds-chart-status-critical)'),
    series: [0, 1, 2].map((i) => css(dash.colors[i])),
    grey: css('var(--cds-chart-muted)'),
    commute: d3.interpolateRgb(dark ? '#184f95' : '#b7d3f6', dark ? '#cde2fb' : '#0d366b'),
    rentDown: d3.interpolateRgb(dark ? '#55544f' : '#d9d8d2', dark ? '#3987e5' : '#2a78d6'),
    rentUp: d3.interpolateRgb(dark ? '#55544f' : '#d9d8d2', dark ? '#e66767' : '#e34948'),
    family: getComputedStyle(S.map.box).fontFamily,
  };
}

function colourOf(frame, i) {
  const p = S.pal;
  if (frame.who[i] < 0) return p.muted;
  if (S.mode === 'commute') {
    const t = (frame.mins[i] - COMMUTE_RANGE[0]) / (COMMUTE_RANGE[1] - COMMUTE_RANGE[0]);
    return p.commute(Math.max(0, Math.min(1, t)));
  }
  if (S.mode === 'rent') {
    const change = frame.rent[i] / S.data.rooms[i].start - 1;
    const t = Math.min(1, Math.abs(change) / RENT_RANGE);
    return change < 0 ? p.rentDown(t) : p.rentUp(t);
  }
  if (S.mode === 'income') {
    const person = S.data.people.get(S.arm)[frame.who[i]];
    return p.series[person ? person[0] : 0];
  }
  const cls = MODE_CLASS[frame.mode[i]];
  return cls === 'subway' ? p.series[0] : cls === 'bus' ? p.series[2] : cls === 'bike' ? p.series[1] : p.grey;
}

// ----- base layer: lines, zone discs, names -----
function drawBase() {
  const d = S.data;
  const p = S.pal;
  const k = S.W / d.width;
  const ctx = S.base.getContext('2d');
  ctx.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
  ctx.clearRect(0, 0, S.W, S.H);
  ctx.strokeStyle = p.axis;
  ctx.lineWidth = 1;
  ctx.lineJoin = 'round';
  d.metro.forEach((points) => {
    ctx.beginPath();
    points.forEach(([x, y], i) => (i ? ctx.lineTo(x * k, y * k) : ctx.moveTo(x * k, y * k)));
    ctx.stroke();
  });
  d.zones.forEach((z) => {
    ctx.beginPath();
    ctx.arc(z.x * k, z.y * k, z.r * k, 0, Math.PI * 2);
    ctx.fillStyle = p.disc;
    ctx.fill();
    ctx.lineWidth = z.treated ? 2 : 1;
    ctx.strokeStyle = z.treated ? p.series[1] : p.grid;
    ctx.stroke();
  });
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  d.zones.forEach((z) => {
    if (S.W < 640 && !z.major) return;
    ctx.font = `${z.treated ? '600 ' : ''}12px ${p.family}`;
    ctx.fillStyle = z.treated ? p.fg : p.muted;
    ctx.fillText(z.name, z.lx * k, z.ly * k);
  });
}

function lineIsOpen() {
  return (S.arm === 'B' || S.arm === 'C') && S.frame >= S.data.opens;
}

function paint(t) {
  const d = S.data;
  const p = S.pal;
  const ctx = S.map.ctx;
  const k = S.W / d.width;
  const frame = framesOf(S.arm)[S.frame];
  const anim = S.anim;
  const radius = Math.max(1.3, 3.5 * k);
  ctx.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
  ctx.clearRect(0, 0, S.W, S.H);
  ctx.drawImage(S.base, 0, 0, S.W, S.H);
  if (lineIsOpen()) {
    const [a, b] = ['Z05', 'Z11'].map((id) => d.zones.find((z) => z.id === id));
    ctx.save();
    ctx.setLineDash([7, 5]);
    ctx.lineWidth = 2;
    ctx.strokeStyle = p.series[1];
    ctx.beginPath();
    ctx.moveTo(d.cbd[0] * k, d.cbd[1] * k);
    ctx.lineTo(a.x * k, a.y * k);
    ctx.lineTo(b.x * k, b.y * k);
    ctx.stroke();
    ctx.restore();
  }
  const waiting = anim && t < 0.9 ? anim.landing : null;
  d.rooms.forEach((room, i) => {
    ctx.beginPath();
    ctx.arc(room.x * k, room.y * k, radius, 0, Math.PI * 2);
    if (frame.who[i] < 0 || (waiting && waiting.has(i))) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = p.muted;
      ctx.stroke();
    } else {
      ctx.fillStyle = colourOf(frame, i);
      ctx.fill();
    }
  });
  if (anim) {
    anim.movers.forEach((m) => {
      const eased = t < 0.5 ? 2 * t * t : 1 - 2 * (1 - t) * (1 - t);
      const x = (m.x0 + (m.x1 - m.x0) * eased) * k;
      const y = (m.y0 + (m.y1 - m.y0) * eased - Math.sin(eased * Math.PI) * m.lift) * k;
      ctx.globalAlpha = m.fade === 'out' ? 1 - t : m.fade === 'in' ? Math.min(1, t * 2.5) : 1;
      ctx.beginPath();
      ctx.arc(x, y, radius + 0.8, 0, Math.PI * 2);
      ctx.fillStyle = m.colour;
      ctx.fill();
      ctx.globalAlpha = 1;
    });
  }
  const cx = d.cbd[0] * k;
  const cy = d.cbd[1] * k;
  const size = Math.max(4, 7 * k);
  ctx.beginPath();
  ctx.moveTo(cx, cy - size);
  ctx.lineTo(cx + size, cy);
  ctx.lineTo(cx, cy + size);
  ctx.lineTo(cx - size, cy);
  ctx.closePath();
  ctx.fillStyle = p.fg;
  ctx.fill();
  if (S.W >= 640) {
    ctx.font = `600 11px ${p.family}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = p.fg;
    ctx.fillText('CBD', cx, cy + size + 9);
  }
}

function makeAnim(fromIndex, toIndex) {
  const d = S.data;
  const frames = framesOf(S.arm);
  const before = frames[fromIndex];
  const after = frames[toIndex];
  const movers = [];
  const landing = new Set();
  if (!quiet()) {
    const outward = (room, dist) => {
      const dx = room.x - d.cbd[0];
      const dy = room.y - d.cbd[1];
      const len = Math.hypot(dx, dy) || 1;
      return [room.x + (dx / len) * dist, room.y + (dy / len) * dist];
    };
    after.events.forEach((e) => {
      if (e[0] === 'move') {
        const a = d.rooms[e[2]];
        const b = d.rooms[e[3]];
        movers.push({x0: a.x, y0: a.y, x1: b.x, y1: b.y, lift: Math.min(60, Math.hypot(b.x - a.x, b.y - a.y) * 0.2), colour: colourOf(after, e[3])});
        landing.add(e[3]);
      } else if (e[0] === 'arrive') {
        const room = d.rooms[e[2]];
        const [x0, y0] = outward(room, 70);
        movers.push({x0, y0, x1: room.x, y1: room.y, lift: 0, fade: 'in', colour: colourOf(after, e[2])});
        landing.add(e[2]);
      } else if (e[0] === 'exits' || e[0] === 'left') {
        const room = d.rooms[e[2]];
        const [x1, y1] = outward(room, e[0] === 'left' ? 110 : 70);
        movers.push({x0: room.x, y0: room.y, x1, y1, lift: 0, fade: 'out', colour: e[0] === 'left' ? S.pal.bad : colourOf(before, e[2])});
      }
    });
  }
  return {movers, landing, start: performance.now(), dur: STEP_MS};
}

function schedule() {
  if (!S.raf) S.raf = requestAnimationFrame(tick);
}

function tick(now) {
  S.raf = 0;
  if (!S.map || !S.data) return;
  if (S.anim) {
    const t = Math.min(1, Math.max(0, (now - S.anim.start) / S.anim.dur));
    paint(t);
    if (t >= 1) {
      S.anim = null;
      if (S.playing) {
        if (S.frame < S.data.last) stepForward();
        else setPlaying(false);
      }
    }
  }
  if (S.anim) schedule();
}

function stepForward() {
  const from = S.frame;
  S.frame = from + 1;
  S.anim = makeAnim(from, S.frame);
  refresh();
  schedule();
}

function setPlaying(on) {
  S.playing = on;
  if (on && S.data) {
    if (S.frame >= S.data.last) S.frame = 0;
    if (!S.anim) stepForward();
  }
  refresh();
}

// ----- panels -----
function statValues() {
  const d = S.data;
  const frame = framesOf(S.arm)[S.frame];
  const part = (wanted) => {
    let count = 0;
    let vacant = 0;
    let mins = 0;
    let rent = 0;
    d.rooms.forEach((room, i) => {
      if (room.zone.treated !== wanted) return;
      count += 1;
      rent += frame.rent[i] / room.start;
      if (frame.who[i] < 0) vacant += 1;
      else mins += frame.mins[i];
    });
    return {count, vacant, mins: mins / Math.max(1, count - vacant), rent: (100 * rent) / Math.max(1, count)};
  };
  const inside = part(true);
  const outside = part(false);
  const tally = {move: 0, left: 0, blocked: 0};
  frame.events.forEach((e) => {
    if (e[0] in tally) tally[e[0]] += 1;
  });
  return {
    month: `${S.frame}`,
    commute_in: inside.mins.toFixed(1),
    commute_out: outside.mins.toFixed(1),
    rent_in: inside.rent.toFixed(1),
    rent_out: outside.rent.toFixed(1),
    vacant_in: `${inside.vacant} / ${inside.count}`,
    vacant_out: `${outside.vacant} / ${outside.count}`,
    renewals: S.frame ? `${frame.renew[0]}` : '—',
    moves: S.frame ? `${tally.move}` : '—',
    left: S.frame ? `${tally.left}` : '—',
    blocked: S.frame ? `${tally.blocked}` : '—',
  };
}

function eventText(e) {
  const d = S.data;
  const people = d.people.get(S.arm);
  const who = (vid) => {
    const person = people[vid];
    return person ? `${GROUP_NAMES[person[0]]}，月入 ${d3.format(',')(person[1])}` : '';
  };
  if (e[0] === 'move') {
    const from = d.rooms[e[2]].zone;
    const to = d.rooms[e[3]].zone;
    return `${who(e[1])}：续租报价 ${e[5]}（现租 ${e[4]}），${from === to ? `在${from.name}换了一间` : `从${from.name}搬到${to.name}`}，房租 ${e[6]}，${MODE_NAMES[e[9]]} ${e[10]} 分钟`;
  }
  if (e[0] === 'left') return `${who(e[1])}：续租报价 ${e[4]}（现租 ${e[3]}），找不到负担得起的房间，离开${d.rooms[e[2]].zone.name}`;
  if (e[0] === 'blocked') return `新来者（${GROUP_NAMES[e[1]]}，月入 ${d3.format(',')(e[2])}）看房 3 次，没有负担得起的房间`;
  if (e[0] === 'arrive') return `新租客（${who(e[1])}）住进${d.rooms[e[2]].zone.name}，房租 ${e[3]}，${MODE_NAMES[e[4]]} ${e[5]} 分钟`;
  return '';
}

function feedLines() {
  const d = S.data;
  const events = framesOf(S.arm)[S.frame].events;
  if (!S.frame) return ['起始状态：所有租客入住，房东还没有调价。'];
  const touches = (e) => e[0] === 'move' && (d.rooms[e[2]].zone.treated || d.rooms[e[3]].zone.treated);
  const pick = [
    ...events.filter((e) => e[0] === 'left'),
    ...events.filter(touches),
    ...events.filter((e) => e[0] === 'move' && !touches(e)).slice(0, 3),
    ...events.filter((e) => e[0] === 'blocked').slice(0, 1),
    ...events.filter((e) => e[0] === 'arrive' && d.rooms[e[2]].zone.treated).slice(0, 1),
    ...events.filter((e) => e[0] === 'arrive').slice(0, 1),
  ];
  return [...new Set(pick)].slice(0, 6).map(eventText);
}

function legendItems() {
  const p = S.pal;
  const dot = (colour, text) => ({colour, text});
  const items = S.mode === 'income'
    ? GROUP_NAMES.map((name, i) => dot(p.series[i], name))
    : S.mode === 'way'
      ? [dot(p.series[0], '地铁（含骑车接地铁）'), dot(p.series[2], '公交'), dot(p.series[1], '电动车、自行车、步行'), dot(p.grey, '私家车、打车')]
      : [];
  return items;
}

function drawLegend(el) {
  el.replaceChildren();
  if (!S.data || !S.pal) return;
  const add = (node, text) => {
    const item = document.createElement('span');
    if (node) item.append(node);
    item.append(document.createTextNode(text));
    el.append(item);
  };
  const p = S.pal;
  if (S.mode === 'commute' || S.mode === 'rent') {
    const ramp = document.createElement('i');
    ramp.className = 'ld-ramp';
    ramp.style.background = S.mode === 'commute'
      ? `linear-gradient(90deg, ${p.commute(0)}, ${p.commute(1)})`
      : `linear-gradient(90deg, ${p.rentDown(1)}, ${p.rentDown(0)}, ${p.rentUp(1)})`;
    add(ramp, S.mode === 'commute' ? `单程通勤 ${COMMUTE_RANGE[0]} 到 ${COMMUTE_RANGE[1]} 分钟及以上` : `房租比起始价低 ${RENT_RANGE * 100}% 到高 ${RENT_RANGE * 100}%`);
  }
  legendItems().forEach((item) => {
    const mark = document.createElement('i');
    mark.className = 'ld-dot';
    mark.style.background = item.colour;
    add(mark, item.text);
  });
  const hollow = document.createElement('i');
  hollow.className = 'ld-dot';
  hollow.style.border = `1px solid ${p.muted}`;
  add(hollow, '空房');
  const ring = document.createElement('i');
  ring.className = 'ld-dot';
  ring.style.border = `2px solid ${p.series[1]}`;
  add(ring, '受益区');
  if (S.arm === 'B' || S.arm === 'C') {
    const dash_ = document.createElement('i');
    dash_.className = 'ld-ramp';
    dash_.style.height = '0';
    dash_.style.width = '26px';
    dash_.style.borderRadius = '0';
    dash_.style.borderTop = `2px dashed ${p.series[1]}`;
    add(dash_, '假想东向快线（开通后）');
  }
}

function refresh() {
  document.querySelectorAll('[data-ld-arm]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.ldArm === S.arm)));
  document.querySelectorAll('[data-ld-mode]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.ldMode === S.mode)));
  document.querySelectorAll('.ld-when-paused').forEach((n) => { n.hidden = S.playing; });
  document.querySelectorAll('.ld-when-playing').forEach((n) => { n.hidden = !S.playing; });
  document.querySelectorAll('.ld-month-input').forEach((n) => {
    n.value = String(S.frame);
    n.setAttribute('aria-valuetext', `第 ${S.frame} 个月`);
  });
  const hasLine = S.arm === 'B' || S.arm === 'C';
  const opened = S.data ? S.frame >= S.data.opens : false;
  document.querySelectorAll('.ld-show-before').forEach((n) => { n.hidden = !(hasLine && !opened); });
  document.querySelectorAll('.ld-show-open').forEach((n) => { n.hidden = !(hasLine && opened); });
  document.querySelectorAll('.ld-show-none').forEach((n) => { n.hidden = hasLine; });
  document.querySelectorAll('.ld-show-frozen').forEach((n) => { n.hidden = !((S.arm === 'A0' || S.arm === 'B') && opened); });
  if (!S.data) return;
  const values = statValues();
  S.stats.forEach((el) => { el.textContent = values[el.dataset.stat] ?? '—'; });
  const lines = feedLines();
  S.feeds.forEach((el) => {
    el.replaceChildren(...lines.map((text) => {
      const li = document.createElement('li');
      li.textContent = text;
      return li;
    }));
  });
  S.legends.forEach(drawLegend);
  if (S.hover && S.map) showZone(S.hover);
}

function repaint() {
  if (!S.data || !S.map || !S.base) return;
  S.anim = null;
  paint(1);
}

function showZone(zone) {
  const d = S.data;
  const frame = framesOf(S.arm)[S.frame];
  let lived = 0;
  let rent = 0;
  let mins = 0;
  d.rooms.forEach((room, i) => {
    if (room.zone !== zone || frame.who[i] < 0) return;
    lived += 1;
    rent += frame.rent[i];
    mins += frame.mins[i];
  });
  const tip = S.map.tip;
  const head = document.createElement('div');
  head.className = 'ld-tip-head';
  head.textContent = zone.treated ? `${zone.name}（受益区）` : zone.name;
  const lines = [`有人住 ${lived} / ${zone.rooms} 间`, `平均房租 ${d3.format(',')(Math.round(rent / Math.max(1, lived)))} 元`, `平均通勤 ${(mins / Math.max(1, lived)).toFixed(1)} 分钟`].map((text) => {
    const row = document.createElement('div');
    row.className = 'ld-tip-line';
    row.textContent = text;
    return row;
  });
  tip.replaceChildren(head, ...lines);
  tip.style.opacity = 1;
  const k = S.W / d.width;
  tip.style.left = `${Math.max(0, Math.min(S.W - tip.offsetWidth, zone.x * k + zone.r * k + 6))}px`;
  tip.style.top = `${Math.max(0, zone.y * k - tip.offsetHeight / 2)}px`;
}

function fitCanvas() {
  const d = S.data;
  const box = S.map.box;
  const W = Math.round(box.clientWidth || 320);
  const H = Math.round((W * d.height) / d.width);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  if (W === S.W && H === S.H && dpr === S.dpr && S.base) return;
  S.W = W;
  S.H = H;
  S.dpr = dpr;
  S.map.canvas.width = W * dpr;
  S.map.canvas.height = H * dpr;
  S.map.canvas.style.height = `${H}px`;
  S.base = document.createElement('canvas');
  S.base.width = W * dpr;
  S.base.height = H * dpr;
  drawBase();
}

function retheme() {
  if (!S.map || !S.data) return;
  readPalette();
  if (S.base) drawBase();
  refresh();
  repaint();
}

dash.draw('replay-map', {
  mount(el) {
    const wrap = document.createElement('div');
    wrap.className = 'ld-canvas-box';
    const canvas = document.createElement('canvas');
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', '北京地图上的房间点阵回放，以 CBD 为中心，每个点是一间房。数值见右侧面板。');
    const tip = document.createElement('div');
    tip.className = 'ld-tip';
    const probe = document.createElement('span');
    probe.className = 'ld-probe';
    const pending = document.createElement('span');
    pending.textContent = '—';
    el.append(wrap, pending);
    wrap.append(canvas, tip, probe);
    S.map = {box: wrap, canvas, tip, probe, pending, ctx: canvas.getContext('2d')};
    const onMove = (event) => {
      if (!S.data) return;
      const rect = canvas.getBoundingClientRect();
      const k = S.W / S.data.width;
      const x = (event.clientX - rect.left) / k;
      const y = (event.clientY - rect.top) / k;
      const zone = S.data.zones.find((z) => Math.hypot(z.x - x, z.y - y) <= z.r);
      S.hover = zone || null;
      if (zone) showZone(zone);
      else tip.style.opacity = 0;
    };
    const onLeave = () => {
      S.hover = null;
      tip.style.opacity = 0;
    };
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerleave', onLeave);
    const themeWatch = new MutationObserver(retheme);
    themeWatch.observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', retheme);
    return {themeWatch, media};
  },
  update() {
    const ready = loadData();
    S.map.pending.hidden = Boolean(ready);
    S.map.box.hidden = !ready;
    if (!ready) return;
    readPalette();
    S.base = S.W && S.base ? S.base : null;
    fitCanvas();
    drawBase();
    refresh();
    if (!S.anim) paint(1);
    else schedule();
  },
  unmount(el, made) {
    made.themeWatch.disconnect();
    made.media.removeEventListener('change', retheme);
    if (S.raf) cancelAnimationFrame(S.raf);
    S.raf = 0;
    S.anim = null;
    S.playing = false;
    S.map = null;
  },
});

dash.draw('replay-stat', {
  mount(el) {
    S.stats.add(el);
    el.textContent = '—';
  },
  update(el) {
    if (S.data && S.map) el.textContent = statValues()[el.dataset.stat] ?? '—';
  },
  unmount(el) {
    S.stats.delete(el);
  },
});

dash.draw('replay-feed', {
  mount(el) {
    S.feeds.add(el);
  },
  update() {
    if (S.data && S.map) refresh();
  },
  unmount(el) {
    S.feeds.delete(el);
  },
});

dash.draw('replay-legend', {
  mount(el) {
    S.legends.add(el);
  },
  update(el) {
    drawLegend(el);
  },
  unmount(el) {
    S.legends.delete(el);
  },
});

document.querySelectorAll('[data-ld-arm]').forEach((button) => {
  button.addEventListener('click', () => {
    S.arm = button.dataset.ldArm;
    S.anim = null;
    if (!S.data) return;
    refresh();
    repaint();
    if (S.playing) stepForward();
  });
});
document.querySelectorAll('[data-ld-mode]').forEach((button) => {
  button.addEventListener('click', () => {
    S.mode = button.dataset.ldMode;
    if (!S.data) return;
    refresh();
    if (!S.anim) paint(1);
  });
});
document.querySelectorAll('.ld-play').forEach((button) => {
  button.addEventListener('click', () => setPlaying(!S.playing));
});
document.querySelectorAll('.ld-month-input').forEach((input) => {
  input.addEventListener('input', () => {
    S.frame = Number(input.value);
    S.anim = null;
    S.playing = false;
    if (!S.data) return;
    refresh();
    repaint();
  });
});
