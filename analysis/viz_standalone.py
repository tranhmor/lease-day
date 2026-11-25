"""Pack the results page into one HTML file that runs anywhere: same page, same scripts, data and d3 included.

The online page gets its data, drawing calls and colours from the dashboard it lives in. Here a small stand-in provides them.
Writes rental_game/lease_day_v06_visuals.html.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = os.path.join(HERE, "viz_dash")
OUT = os.path.join(HERE, "..", "lease_day_v06_visuals.html")
NAMES = ["levels", "effects", "monthly", "effect_by_month", "zones", "ledger", "assumptions", "landlord_rules", "real_vs_rule", "baseline", "map", "metro", "replay_rooms", "replay", "replay_people"]
read = lambda *parts: open(os.path.join(*parts), encoding="utf-8").read()

data = {n: json.loads(read(DASH, n + ".json")) for n in NAMES}
page = read(DASH, "page", "index.html")
page = re.sub(r'<meta name="dash-one-writer">\s*', "", page)
page = re.sub(r'<script src="[^"]+"></script>\s*', "", page)
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
assert "</script" not in blob

TOKENS = """
:root {
  --font-anthropic-sans: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif;
  --font-anthropic-serif: "Songti SC", "STSong", "SimSun", "Noto Serif CJK SC", serif;
  --cds-font-size-caption: 13px; --cds-font-size-body: 15px; --cds-font-size-heading: 19px; --cds-font-size-title: 30px; --cds-font-weight-medium: 600;
  --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 16px; --cds-gap-lg: 24px; --cds-gap-xl: 40px;
  --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 18px; --cds-radius: 8px;
  --color-fg: #1b1f24; --color-fg-muted: #636a73; --color-bg: #f7f8f9; --color-panel: #ffffff; --color-border-line: #e1e4e8;
  --color-ok: #006300; --color-warn: #8a5a00; --color-bad: #c03030;
  --cds-chart-grid: #e8eaed; --cds-chart-axis: #c3c7cc; --cds-chart-reference: #9a9ea4; --cds-chart-muted: #aab0b6; --cds-chart-status-critical: #d03b3b;
  --cds-surface-popover: #ffffff; --cds-border: #d5d8dc; --cds-shadow-popover: 0 2px 10px rgba(0, 0, 0, .14); --cds-text-secondary: #636a73;
}
@media (prefers-color-scheme: dark) {
  :root {
    color-scheme: dark;
    --color-fg: #eceef0; --color-fg-muted: #a4aab1; --color-bg: #15181c; --color-panel: #1d2126; --color-border-line: #33383e;
    --color-ok: #0ca30c; --color-warn: #fab219; --color-bad: #e66767;
    --cds-chart-grid: #2c3137; --cds-chart-axis: #4a5057; --cds-chart-reference: #6b7178; --cds-chart-muted: #6b7178; --cds-chart-status-critical: #e66767;
    --cds-surface-popover: #262b31; --cds-border: #3d434a; --cds-shadow-popover: 0 2px 10px rgba(0, 0, 0, .5); --cds-text-secondary: #a4aab1;
  }
}
html, body { margin: 0; background: var(--color-bg); color: var(--color-fg); }
[hidden] { display: none !important; }
#dash-root { max-width: 1240px; margin: 0 auto; padding: 28px clamp(16px, 3vw, 32px) 48px; }
"""

SHIM = """
window.dash = (() => {
  const DATA = window.LD_DATA;
  const drawings = [];
  const api = {
    colors: ['#2a78d6', '#d95926', '#1baf7a', '#c98500', '#d55181', '#008300', '#6250d6', '#e34948'],
    data: (id) => (DATA[id] ? {status: 'ok', data: DATA[id], meta: []} : {status: 'missing', data: [], meta: []}),
    draw: (name, spec) => { drawings.push({name, spec}); },
    start() {
      const live = [];
      drawings.forEach(({name, spec}) => document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => {
        const entry = {el, spec, made: null, width: -1};
        if (typeof spec !== 'function') {
          el.replaceChildren();
          entry.made = spec.mount(el);
        }
        live.push(entry);
      }));
      const run = (entry) => {
        entry.width = entry.el.clientWidth;
        if (typeof entry.spec === 'function') entry.spec(entry.el);
        else entry.spec.update(entry.el, entry.made);
      };
      live.forEach(run);
      const watch = new ResizeObserver(() => live.forEach((entry) => { if (entry.el.clientWidth !== entry.width) run(entry); }));
      live.forEach((entry) => watch.observe(entry.el));
    },
  };
  return api;
})();
"""


def wrapped(name):
    """Each script gets its own scope, as it does on the online page."""
    return "<script>(function () {\n" + read(DASH, "page", name) + "\n})();</script>"


html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>《到期日》实验可视化</title>
<style>{TOKENS}</style>
</head>
<body>
<div id="dash-root">
{page}
</div>
<script>{read(DASH, "vendor", "d3-7.9.0.min.js")}</script>
<script>window.LD_DATA = {blob};</script>
<script>{SHIM}</script>
{wrapped("charts.js")}
{wrapped("replay.js")}
<script>window.dash.start();</script>
</body>
</html>
"""
open(OUT, "w", encoding="utf-8").write(html)
print("wrote", os.path.relpath(OUT, HERE), os.path.getsize(OUT) // 1024, "KB")
