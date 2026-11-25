const number = (v) => (v === null || v === undefined || v === '' ? null : Number(v));
const plain = (v, digits = 0) => d3.format(`,.${digits}f`)(v);
const signed = (v, digits = 0) => (Math.abs(v) < 0.5 * 10 ** -digits ? '0' : d3.format(`+,.${digits}f`)(v));
const armStyle = (arm) => ({
  color: arm === 'B' || arm === 'C' ? dash.colors[1] : 'var(--color-fg-muted)',
  dash: arm === 'A0' || arm === 'B' ? '5 4' : null,
});
const ARM_NAMES = {A: 'A 没有新线', A0: 'A0 冻结', B: 'B 新线，冻结', C: 'C 新线，变化'};
const OPENS = 24.5;

function wait(el) {
  el.replaceChildren();
  el.textContent = '—';
}

function textWidth(svg, strings, cls) {
  const t = svg.append('text').attr('class', cls || 'ld-tick').style('visibility', 'hidden');
  let width = 0;
  strings.forEach((s) => {
    t.text(s);
    width = Math.max(width, t.node().getComputedTextLength());
  });
  t.remove();
  return Math.ceil(width);
}

function newSvg(el, width, height) {
  el.replaceChildren();
  return d3.select(el).append('svg').attr('width', '100%').attr('height', height).attr('viewBox', `0 0 ${width} ${height}`);
}

function makeTip(el) {
  const tip = document.createElement('div');
  tip.className = 'ld-tip';
  el.append(tip);
  return tip;
}

function showTip(el, tip, x, y, head, lines) {
  const headEl = document.createElement('div');
  headEl.className = 'ld-tip-head';
  headEl.textContent = head;
  const rows = lines.map((line) => {
    const row = document.createElement('div');
    row.className = 'ld-tip-line';
    if (line.color) {
      const dot = document.createElement('span');
      dot.className = 'ld-dot';
      dot.style.background = line.color;
      row.append(dot);
    }
    const text = document.createElement('span');
    text.textContent = line.text;
    row.append(text);
    return row;
  });
  tip.replaceChildren(headEl, ...rows);
  tip.style.opacity = 1;
  const room = el.clientWidth - tip.offsetWidth;
  tip.style.left = `${Math.max(0, Math.min(room, x + 12))}px`;
  tip.style.top = `${Math.max(0, y - tip.offsetHeight - 8)}px`;
}

function hideTip(tip) {
  tip.style.opacity = 0;
}

// one figure in a sentence
dash.draw('v', (el) => {
  const {source, field, where, f} = el.dataset;
  const got = dash.data(source);
  if (got.status !== 'ok') {
    el.textContent = '—';
    return;
  }
  const pairs = [...new URLSearchParams(where || '')];
  const row = got.data.find((r) => pairs.every(([k, v]) => String(r[k]) === v));
  el.textContent = row ? plain(number(row[field]), Number(f || 0)) : '—';
});

dash.draw('arm-swatch', (el) => {
  el.replaceChildren();
  const style = armStyle(el.dataset.arm);
  const line = d3.select(el).append('svg').attr('width', 30).attr('height', 10).attr('viewBox', '0 0 30 10').append('line')
    .attr('x1', 1).attr('x2', 29).attr('y1', 5).attr('y2', 5).attr('stroke-width', 2).attr('stroke-linecap', style.dash ? 'butt' : 'round').style('stroke', style.color);
  if (style.dash) line.attr('stroke-dasharray', style.dash);
});

dash.draw('timeline', (el) => {
  const got = dash.data('levels');
  if (got.status !== 'ok') return wait(el);
  const level = (key) => number(got.data.find((r) => r.key === key).value);
  const months = level('months');
  const opens = level('opens');
  const window_ = level('tail');
  const width = el.clientWidth || 320;
  const svg = newSvg(el, width, 62);
  const x = d3.scaleLinear([0, months], [1, width - 1]);
  const y = 28;
  svg.append('rect').attr('x', x(0)).attr('width', x(months) - x(0)).attr('y', y).attr('height', 10).attr('rx', 2).style('fill', 'var(--cds-chart-grid)');
  svg.append('rect').attr('x', x(months - window_)).attr('width', x(months) - x(months - window_)).attr('y', y).attr('height', 10).attr('rx', 2).style('fill', dash.colors[1]);
  svg.append('line').attr('x1', x(opens - 0.5)).attr('x2', x(opens - 0.5)).attr('y1', y - 6).attr('y2', y + 16).attr('stroke-width', 2).style('stroke', 'var(--color-fg)');
  svg.append('text').attr('class', 'ld-label').attr('x', x(opens - 0.5)).attr('y', y - 11).attr('text-anchor', 'middle').text(`第 ${opens} 月：新线开通，冻结开始`);
  svg.append('text').attr('class', 'ld-tick').attr('x', x(0)).attr('y', y + 28).text('第 1 月');
  svg.append('text').attr('class', 'ld-tick').attr('x', x(months)).attr('y', y + 28).attr('text-anchor', 'end').text(`第 ${months - window_ + 1}–${months} 月：统计窗口`);
});

// ----- monthly paths -----
let monthlyFrom = null;
let monthlyAt = {};
function monthlySeries(metric, arm) {
  const got = dash.data('monthly');
  if (got.status !== 'ok') return null;
  if (monthlyFrom !== got.data) {
    monthlyFrom = got.data;
    monthlyAt = d3.group(got.data, (r) => `${r.metric}|${r.arm}`);
  }
  return (monthlyAt.get(`${metric}|${arm}`) || []).map((r) => ({month: number(r.month), mean: number(r.mean), half: number(r.half)})).sort((a, b) => a.month - b.month);
}

function frame(svg, x, m, width, height, opts) {
  const top = m.t;
  const bottom = height - m.b;
  svg.append('rect').attr('x', x(48)).attr('width', x(60) - x(48)).attr('y', top).attr('height', bottom - top).attr('fill-opacity', 0.45).style('fill', 'var(--cds-chart-grid)');
  svg.append('line').attr('x1', x(OPENS)).attr('x2', x(OPENS)).attr('y1', top).attr('y2', bottom).attr('stroke-width', 1).style('stroke', 'var(--cds-chart-reference)');
  if (width > 280) {
    svg.append('text').attr('class', 'ld-tick').attr('x', x(OPENS)).attr('y', top - 6).attr('text-anchor', 'middle').text('开通');
    svg.append('text').attr('class', 'ld-tick').attr('x', x(60)).attr('y', top - 6).attr('text-anchor', 'end').text('统计窗口');
  }
  svg.append('line').attr('x1', m.l).attr('x2', width - m.r).attr('y1', bottom).attr('y2', bottom).attr('stroke-width', 1).style('stroke', 'var(--cds-chart-axis)');
  [12, 24, 36, 48, 60].forEach((tick) => {
    svg.append('text').attr('class', 'ld-tick').attr('x', x(tick)).attr('y', bottom + 16).attr('text-anchor', tick === 60 ? 'end' : 'middle').text(tick === 60 ? '60 月' : tick);
  });
  opts.yTicks.forEach((tick) => {
    svg.append('line').attr('x1', m.l).attr('x2', width - m.r).attr('y1', opts.y(tick)).attr('y2', opts.y(tick)).attr('stroke-width', 1).style('stroke', 'var(--cds-chart-grid)');
    svg.append('text').attr('class', 'ld-tick').attr('x', m.l - 6).attr('y', opts.y(tick) + 4).attr('text-anchor', 'end').text(opts.yFormat(tick));
  });
}

dash.draw('path', (el) => {
  const metric = el.dataset.metric;
  const digits = Number(el.dataset.digits || 1);
  const arms = (el.dataset.arms || 'A0,B,A,C').split(',');
  const series = arms.map((arm) => ({arm, points: monthlySeries(metric, arm), style: armStyle(arm)}));
  if (series.some((s) => !s.points || !s.points.length)) return wait(el);
  const width = el.clientWidth || 320;
  const height = 230;
  const svg = newSvg(el, width, height);
  const shown = series.flatMap((s) => s.points.filter((p) => p.month > 0 || metric !== 'inq_in'));
  const y = d3.scaleLinear([d3.min(shown, (p) => p.mean - p.half), d3.max(shown, (p) => p.mean + p.half)], [height - 26, 22]).nice(4);
  const yTicks = y.ticks(4);
  const yFormat = (v) => plain(v, yTicks.some((t) => !Number.isInteger(t)) ? 1 : 0);
  const endLabels = ['C', 'A'].filter((a) => arms.includes(a));
  const last = (arm) => series.find((s) => s.arm === arm).points.at(-1).mean;
  const right = textWidth(svg, endLabels.map((a) => plain(last(a), digits))) + 8;
  const m = {l: textWidth(svg, yTicks.map(yFormat)) + 8, r: right, t: 22, b: 26};
  const x = d3.scaleLinear([0, 60], [m.l, width - m.r]);
  frame(svg, x, m, width, height, {y, yTicks, yFormat});
  const drawable = (p) => p.month > 0 || metric !== 'inq_in';
  series.filter((s) => s.arm === 'A' || s.arm === 'C').forEach((s) => {
    const area = d3.area().defined(drawable).x((p) => x(p.month)).y0((p) => y(p.mean - p.half)).y1((p) => y(p.mean + p.half));
    svg.append('path').attr('d', area(s.points)).attr('fill-opacity', 0.1).style('fill', s.style.color);
  });
  series.forEach((s) => {
    const line = d3.line().defined(drawable).x((p) => x(p.month)).y((p) => y(p.mean));
    const mark = svg.append('path').attr('d', line(s.points)).attr('fill', 'none').attr('stroke-width', 2).attr('stroke-linejoin', 'round').attr('stroke-linecap', s.style.dash ? 'butt' : 'round').style('stroke', s.style.color);
    if (s.style.dash) mark.attr('stroke-dasharray', s.style.dash);
  });
  const ends = endLabels.map((a) => ({arm: a, y: y(last(a)), text: plain(last(a), digits)}));
  ends.forEach((e, i) => {
    if (i > 0 && Math.abs(e.y - ends[0].y) < 14) return;
    svg.append('text').attr('class', 'ld-label').attr('x', width - m.r + 5).attr('y', e.y + 4).text(e.text);
  });
  const tip = makeTip(el);
  const rule = svg.append('line').attr('y1', m.t).attr('y2', height - m.b).attr('stroke-width', 1).attr('opacity', 0).style('stroke', 'var(--cds-chart-reference)');
  svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', width - m.l - m.r).attr('height', height - m.t - m.b).attr('fill', 'transparent')
    .on('pointermove', (event) => {
      const [px, py] = d3.pointer(event);
      const month = Math.max(0, Math.min(60, Math.round(x.invert(px))));
      rule.attr('x1', x(month)).attr('x2', x(month)).attr('opacity', 1);
      const lines = [...series].reverse().map((s) => ({color: s.style.color, text: `${ARM_NAMES[s.arm]}  ${plain(s.points[month].mean, digits)}`}));
      showTip(el, tip, px, py, `第 ${month} 个月`, lines);
    })
    .on('pointerleave', () => {
      rule.attr('opacity', 0);
      hideTip(tip);
    });
});

dash.draw('gap', (el) => {
  const got = dash.data('effect_by_month');
  if (got.status !== 'ok') return wait(el);
  const digits = Number(el.dataset.digits || 2);
  const points = got.data.filter((r) => r.metric === el.dataset.metric && r.effect === el.dataset.effect)
    .map((r) => ({month: number(r.month), value: number(r.value), half: number(r.half)})).sort((a, b) => a.month - b.month);
  if (!points.length) return wait(el);
  const width = el.clientWidth || 320;
  const height = 230;
  const svg = newSvg(el, width, height);
  const y = d3.scaleLinear([Math.min(-0.2, d3.min(points, (p) => p.value - p.half)), d3.max(points, (p) => p.value + p.half)], [height - 26, 22]).nice(4);
  const yTicks = y.ticks(4);
  const yFormat = (v) => signed(v, yTicks.some((t) => !Number.isInteger(t)) ? 1 : 0);
  const endText = signed(points.at(-1).value, digits);
  const m = {l: textWidth(svg, yTicks.map(yFormat)) + 8, r: textWidth(svg, [endText]) + 8, t: 22, b: 26};
  const x = d3.scaleLinear([0, 60], [m.l, width - m.r]);
  frame(svg, x, m, width, height, {y, yTicks, yFormat});
  svg.append('line').attr('x1', m.l).attr('x2', width - m.r).attr('y1', y(0)).attr('y2', y(0)).attr('stroke-width', 1).style('stroke', 'var(--cds-chart-reference)');
  const after = points.filter((p) => p.month >= 25);
  const color = dash.colors[1];
  svg.append('path').attr('d', d3.area().x((p) => x(p.month)).y0((p) => y(p.value - p.half)).y1((p) => y(p.value + p.half))(after)).attr('fill-opacity', 0.14).style('fill', color);
  svg.append('path').attr('d', d3.line().x((p) => x(p.month)).y((p) => y(p.value))(after)).attr('fill', 'none').attr('stroke-width', 2).attr('stroke-linejoin', 'round').attr('stroke-linecap', 'round').style('stroke', color);
  svg.append('text').attr('class', 'ld-label').attr('x', width - m.r + 5).attr('y', y(points.at(-1).value) + 4).text(endText);
  const tip = makeTip(el);
  svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', width - m.l - m.r).attr('height', height - m.t - m.b).attr('fill', 'transparent')
    .on('pointermove', (event) => {
      const [px, py] = d3.pointer(event);
      const month = Math.max(25, Math.min(60, Math.round(x.invert(px))));
      const p = points.find((v) => v.month === month);
      showTip(el, tip, px, py, `第 ${month} 个月`, [{color, text: `${signed(p.value, digits)} ±${plain(p.half, digits)}`}]);
    })
    .on('pointerleave', () => hideTip(tip));
});

// ----- effects, one row per metric -----
const EFFECT_ROWS = [
  ['watch_commute', '受益区租客通勤（分钟）'], ['commute', '全体通勤（分钟）'], ['low_commute', '低收入者通勤（分钟）'], ['mode_in_subway', '受益区地铁占比（百分点）'],
  ['watch_rent', '受益区租金指数（点）'], ['other_rent', '其他区域租金指数（点）'], ['rev_in', '受益区房东每间月收入（元）'], ['low_cash', '低收入者月租加通勤费（元）'],
  ['cum_in', '累计搬入受益区（人）'], ['cum_moves', '累计搬家（次）'], ['cum_left', '累计离开（人）'], ['cum_blocked', '低收入者累计被挡（次）'],
];

function whisker(cell, value, half, scale) {
  const width = Math.max(60, cell.clientWidth || 90);
  const clear = Math.abs(value) > half && half > 0;
  const color = clear ? 'var(--color-fg)' : 'var(--cds-chart-muted)';
  const svg = d3.select(cell).append('svg').attr('class', 'ld-whisk').attr('viewBox', `0 0 ${width} 16`).attr('preserveAspectRatio', 'none');
  const x = d3.scaleLinear([-scale, scale], [5, width - 5]);
  svg.append('line').attr('x1', x(0)).attr('x2', x(0)).attr('y1', 1).attr('y2', 15).attr('stroke-width', 1).style('stroke', 'var(--cds-chart-reference)');
  svg.append('line').attr('x1', x(value - half)).attr('x2', x(value + half)).attr('y1', 8).attr('y2', 8).attr('stroke-width', 2).attr('stroke-linecap', 'round').style('stroke', color);
  svg.append('circle').attr('cx', x(value)).attr('cy', 8).attr('r', 4).style('fill', color);
}

dash.draw('effects', (el) => {
  const got = dash.data('effects');
  if (got.status !== 'ok') return wait(el);
  el.replaceChildren();
  EFFECT_ROWS.forEach(([metric, label]) => {
    const rows = got.data.filter((r) => r.metric === metric);
    if (!rows.length) return;
    const scale = Math.max(...rows.map((r) => Math.abs(number(r.value)) + number(r.half))) * 1.05 || 1;
    const row = document.createElement('div');
    row.className = 'ld-eff-row';
    const name = document.createElement('div');
    name.textContent = label;
    row.append(name);
    el.append(row);
    ['direct', 'total', 'interaction'].forEach((effect) => {
      const r = rows.find((v) => v.effect === effect);
      const value = number(r.value);
      const half = number(r.half);
      const digits = number(r.digits);
      const cell = document.createElement('div');
      const text = document.createElement('div');
      text.className = 'ld-eff-num';
      const big = document.createElement('b');
      big.textContent = signed(value, digits);
      const pm = document.createElement('span');
      pm.className = 'ld-pm';
      pm.textContent = half > 0 ? `±${plain(half, digits < 2 ? digits + 1 : digits)}` : '';
      text.append(big, pm);
      cell.append(text);
      row.append(cell);
      whisker(cell, value, half, scale);
    });
  });
});

// ----- tables -----
function fillRows(tbody, rows, cells, highlight) {
  tbody.replaceChildren();
  rows.forEach((r) => {
    const tr = document.createElement('tr');
    tr.dataset.key = cells.key(r);
    if (highlight && highlight(r)) tr.className = 'ld-hl';
    cells.values.forEach((value) => {
      const td = document.createElement('td');
      td.textContent = value(r);
      tr.append(td);
    });
    tbody.append(tr);
  });
}

dash.draw('ledger', (el) => {
  const got = dash.data('ledger');
  if (got.status !== 'ok') return el.replaceChildren();
  const pair = (r, key, digits) => (number(r[key]) === null ? '' : `${signed(number(r[key]), digits)} ±${plain(number(r[`${key}_h`]), digits)}`);
  fillRows(el, got.data, {
    key: (r) => r.row,
    values: [(r) => `${r.where} · ${r.who}`, (r) => (number(r.n) === null ? '' : plain(number(r.n))), (r) => pair(r, 'commute', 1), (r) => pair(r, 'rent', 0), (r) => pair(r, 'fare', 0)],
  }, (r) => r.where === '受益区');
});

dash.draw('lowcost', (el) => {
  const got = dash.data('assumptions');
  if (got.status !== 'ok') return el.replaceChildren();
  const rows = ['base', 'low-cost rooms -30%', 'low-cost rooms -60%'].map((v) => got.data.find((r) => r.variant === v)).filter(Boolean);
  fillRows(el, rows, {
    key: (r) => r.variant,
    values: [(r) => r.label, (r) => plain(number(r.seated)), (r) => plain(number(r.low_over30)), (r) => plain(number(r.left), 1), (r) => plain(number(r.blocked_low), 1)],
  });
});

dash.draw('rules', (el) => {
  const got = dash.data('landlord_rules');
  if (got.status !== 'ok') return el.replaceChildren();
  fillRows(el, got.data, {
    key: (r) => r.k,
    values: [(r) => r.label, (r) => signed(number(r.express), 2), (r) => plain(number(r.express_h), 2), (r) => signed(number(r.replay), 2), (r) => plain(number(r.replay_h), 2)],
  });
});

dash.draw('baseline', (el) => {
  const got = dash.data('baseline');
  if (got.status !== 'ok') return el.replaceChildren();
  fillRows(el, got.data, {key: (r) => r.metric, values: [(r) => r.metric, (r) => plain(number(r.model), Number.isInteger(number(r.model)) ? 0 : 1), (r) => r.real]});
});

// ----- zones -----
dash.draw('zones', (el) => {
  const got = dash.data('zones');
  if (got.status !== 'ok') return wait(el);
  const rows = got.data.map((r) => ({...r, treated: r.treated === true || r.treated === 'true', vac: number(r.vac), rent: number(r.rent), rent_h: number(r.rent_h), commute: number(r.commute), commute_h: number(r.commute_h), subway: number(r.subway), tenants: number(r.tenants), n: number(r.n), n_h: number(r.n_h), whole: number(r.whole)}));
  const width = Math.max(el.clientWidth || 560, 480);
  const rowH = 21;
  const top = 34;
  const height = top + rowH * rows.length + 26;
  const svg = newSvg(el, width, height);
  const names = rows.map((r) => `${r.name} ${r.subway} 分`);
  const nameW = textWidth(svg, names, 'ld-label-strong') + 12;
  const gap = 18;
  const panel = (width - nameW - gap * 2) / 3;
  const panels = [nameW, nameW + panel + gap, nameW + 2 * (panel + gap)];
  const vacX = d3.scaleLinear([0, d3.max(rows, (r) => r.vac)], [panels[0], panels[0] + panel - 36]);
  const rentMax = d3.max(rows, (r) => Math.abs(r.rent) + r.rent_h) * 1.05;
  const rentX = d3.scaleLinear([-rentMax, rentMax], [panels[1] + 4, panels[1] + panel - 4]);
  const cmtX = d3.scaleLinear([d3.min(rows, (r) => r.commute - r.commute_h) * 1.05, d3.max(rows, (r) => Math.max(1, r.commute + r.commute_h)) * 1.05], [panels[2] + 4, panels[2] + panel - 4]);
  [['空置率（%）', panels[0]], ['租金差（指数点）', panels[1]], ['通勤差（分钟）', panels[2]]].forEach(([t, px]) => svg.append('text').attr('class', 'ld-tick').attr('x', px).attr('y', 14).text(t));
  const yAt = (i) => top + rowH * i + rowH / 2;
  const axisY = top + rowH * rows.length + 4;
  [rentX, cmtX].forEach((scale) => {
    svg.append('line').attr('x1', scale(0)).attr('x2', scale(0)).attr('y1', top - 6).attr('y2', axisY).attr('stroke-width', 1).style('stroke', 'var(--cds-chart-reference)');
    scale.ticks(4).forEach((tick) => {
      svg.append('text').attr('class', 'ld-tick').attr('x', scale(tick)).attr('y', axisY + 15).attr('text-anchor', 'middle').text(signed(tick, Number.isInteger(tick) ? 0 : 1));
    });
  });
  const accent = dash.colors[1];
  rows.forEach((r, i) => {
    const yc = yAt(i);
    if (r.treated) svg.append('rect').attr('x', 0).attr('y', yc - rowH / 2).attr('width', width).attr('height', rowH).attr('fill-opacity', 0.6).style('fill', 'var(--cds-chart-grid)');
    svg.append('text').attr('class', r.treated ? 'ld-label-strong' : 'ld-label').attr('x', 2).attr('y', yc + 4).text(`${r.name} ${r.subway} 分`);
    const mark = r.treated ? accent : 'var(--cds-chart-muted)';
    svg.append('rect').attr('x', vacX(0)).attr('y', yc - 5).attr('width', Math.max(1, vacX(r.vac) - vacX(0))).attr('height', 10).attr('rx', 2).style('fill', mark);
    svg.append('text').attr('class', 'ld-tick').attr('x', vacX(r.vac) + 5).attr('y', yc + 4).text(plain(r.vac, 1));
    [[rentX, r.rent, r.rent_h], [cmtX, r.commute, r.commute_h]].forEach(([scale, value, half]) => {
      svg.append('line').attr('x1', scale(value - half)).attr('x2', scale(value + half)).attr('y1', yc).attr('y2', yc).attr('stroke-width', 2).attr('stroke-linecap', 'round').style('stroke', mark);
      svg.append('circle').attr('cx', scale(value)).attr('cy', yc).attr('r', 4).style('fill', mark);
    });
  });
  const tip = makeTip(el);
  svg.append('rect').attr('x', 0).attr('y', top).attr('width', width).attr('height', rowH * rows.length).attr('fill', 'transparent')
    .on('pointermove', (event) => {
      const [px, py] = d3.pointer(event);
      const r = rows[Math.max(0, Math.min(rows.length - 1, Math.floor((py - top) / rowH)))];
      showTip(el, tip, px, py, `${r.name}（${r.dir}·${r.ring}）`, [
        {text: `空置率 ${plain(r.vac, 1)}%`}, {text: `租金差 ${signed(r.rent, 2)} ±${plain(r.rent_h, 2)}`}, {text: `通勤差 ${signed(r.commute, 2)} ±${plain(r.commute_h, 2)} 分钟`},
        {text: `住户数差 ${signed(r.n, 2)} ±${plain(r.n_h, 2)}`}, {text: `整租起始价 ${plain(r.whole)} 元`},
      ]);
    })
    .on('pointerleave', () => hideTip(tip));
});

// ----- whisker lists -----
function whiskerList(el, rows, {labelOf, valueOf, loOf, hiOf, textOf, groupOf, colorOf}) {
  const width = el.clientWidth || 320;
  const rowH = 24;
  const groups = groupOf ? [...new Set(rows.map(groupOf))] : [null];
  const height = 26 + rows.length * rowH + groups.length * (groupOf ? 26 : 0);
  const svg = newSvg(el, width, height);
  const left = textWidth(svg, rows.map(labelOf), 'ld-label') + 10;
  const right = textWidth(svg, rows.map(textOf), 'ld-label') + 8;
  const lo = d3.min(rows, loOf);
  const hi = d3.max(rows, hiOf);
  const x = d3.scaleLinear([Math.min(0, lo), Math.max(0, hi)], [left, width - right]).nice(4);
  const bottom = height - 22;
  x.ticks(4).forEach((tick) => {
    svg.append('line').attr('x1', x(tick)).attr('x2', x(tick)).attr('y1', 4).attr('y2', bottom).attr('stroke-width', 1).style('stroke', tick === 0 ? 'var(--cds-chart-reference)' : 'var(--cds-chart-grid)');
    svg.append('text').attr('class', 'ld-tick').attr('x', x(tick)).attr('y', bottom + 16).attr('text-anchor', 'middle').text(signed(tick, 0));
  });
  let y = 6;
  groups.forEach((group) => {
    if (group) {
      y += 18;
      svg.append('text').attr('class', 'ld-label-strong').attr('x', 0).attr('y', y).text(group);
      y += 8;
    }
    rows.filter((r) => !group || groupOf(r) === group).forEach((r) => {
      const yc = y + rowH / 2;
      const color = colorOf(r);
      svg.append('text').attr('class', 'ld-label').attr('x', 0).attr('y', yc + 4).text(labelOf(r));
      svg.append('line').attr('x1', x(loOf(r))).attr('x2', x(hiOf(r))).attr('y1', yc).attr('y2', yc).attr('stroke-width', 2).attr('stroke-linecap', 'round').style('stroke', color);
      svg.append('circle').attr('cx', x(valueOf(r))).attr('cy', yc).attr('r', 4).style('fill', color);
      svg.append('text').attr('class', 'ld-label').attr('x', width - right + 8).attr('y', yc + 4).text(textOf(r));
      y += rowH;
    });
  });
}

dash.draw('forest', (el) => {
  const got = dash.data('real_vs_rule');
  if (got.status !== 'ok') return wait(el);
  const rows = got.data.map((r) => ({...r, value: number(r.value), lo: number(r.lo), hi: number(r.hi)}));
  whiskerList(el, rows, {
    labelOf: (r) => r.label, valueOf: (r) => r.value, loOf: (r) => r.lo, hiOf: (r) => r.hi, textOf: (r) => signed(r.value, r.group.startsWith('规则') ? 2 : 1), groupOf: (r) => r.group,
    colorOf: (r) => (r.group.startsWith('规则') ? dash.colors[1] : dash.colors[0]),
  });
});

dash.draw('assume', (el) => {
  const got = dash.data('assumptions');
  if (got.status !== 'ok') return wait(el);
  const rows = got.data.map((r) => ({...r, premium: number(r.premium), premium_h: number(r.premium_h)}));
  whiskerList(el, rows, {
    labelOf: (r) => r.label, valueOf: (r) => r.premium, loOf: (r) => r.premium - r.premium_h, hiOf: (r) => r.premium + r.premium_h, textOf: (r) => signed(r.premium, 2),
    colorOf: (r) => (r.variant === 'base' ? dash.colors[1] : 'var(--cds-chart-muted)'),
  });
});
