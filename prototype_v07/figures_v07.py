"""Report figures for Lease Day v0.7 (F stage). Reads run directories only; never re-runs the model.

Usage (needs matplotlib; the engine itself does not):
    python3 -m prototype_v07.figures_v07 --runs runs_r --group R --out figs_r
    python3 -m prototype_v07.figures_v07 --runs runs_l --group L --baseline-runs runs_r --out figs_l

Figures:
    fig1_rent_index.png      monthly treated-zone rent index, N/S/P mean with 95% CI band, announcement/opening marks
    fig2_vacancy.png         monthly treated-zone vacancy, same layout
    fig3_paired_diffs.png    seed-paired S-N, P-N, P-S differences of the pre-registered rows (forest plot)
    fig4_quotes_P_vs_S.png   H1: treated-zone landlord quote changes M13-24 by month, P vs S (needs decisions.jsonl)
    fig5_movein_profile.png  H2: income / pre-move cash of treated-zone movers M13-24, P vs S (all seeds pooled)
    fig6_burden_by_kind.png  V1.2: rent/income by room kind x income group (N tail)
"""
import argparse
import json
from pathlib import Path
import statistics as st
from typing import Dict, List, Optional

from .analyze_v07 import PAIRED_ROWS, _load_monthly, _paired_seeds, ci95

TOKENS_PATH = Path(__file__).resolve().parent.parent / "tokens.json"


def load_tokens(theme: str = "light") -> Dict:
    data = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    return data[theme]


TOKENS_LIGHT = load_tokens("light")
SC_STYLE = {
    "N": (TOKENS_LIGHT["scenarios"]["N"], "N 无新线"),
    "S": (TOKENS_LIGHT["scenarios"]["S"], "S 突然开通"),
    "P": (TOKENS_LIGHT["scenarios"]["P"], "P 提前公告"),
}
ANNOUNCE_M, OPEN_M = 13, 25


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for name in ("Source Han Sans SC", "Noto Sans CJK SC", "PingFang SC", "Heiti SC", "STHeiti", "Songti SC", "SimHei", "Microsoft YaHei"):
        if any(name in f.name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 150
    plt.rcParams["figure.facecolor"] = TOKENS_LIGHT["bg"]
    plt.rcParams["axes.facecolor"] = TOKENS_LIGHT["bg"]
    plt.rcParams["axes.edgecolor"] = TOKENS_LIGHT["line"]
    plt.rcParams["axes.labelcolor"] = TOKENS_LIGHT["text"]
    plt.rcParams["xtick.color"] = TOKENS_LIGHT["sub"]
    plt.rcParams["ytick.color"] = TOKENS_LIGHT["sub"]
    plt.rcParams["text.color"] = TOKENS_LIGHT["text"]
    return plt


def _marks(ax) -> None:
    ann_c = TOKENS_LIGHT["announce"]
    ax.axvline(ANNOUNCE_M - 0.5, color=ann_c, ls=":", lw=1.2)
    ax.axvline(OPEN_M - 0.5, color=TOKENS_LIGHT["text"], ls="--", lw=1)
    tr = ax.get_xaxis_transform()  # x in data, y in axes fraction: labels sit just above the plot area
    ax.text(ANNOUNCE_M - 0.5, 1.01, "公告（仅 P）", transform=tr, ha="center", va="bottom", fontsize=8, color=ann_c)
    ax.text(OPEN_M - 0.5, 1.01, "开通（S、P）", transform=tr, ha="center", va="bottom", fontsize=8, color=TOKENS_LIGHT["text"])


def _band(plt, mon, seeds, key, scale, ylabel, title, path, group) -> None:
    fig, ax = plt.subplots(figsize=(7, 3.8))
    months = sorted(mon[("N", seeds[0])])
    same_ps = all(mon[("P", s)][m][key] == mon[("S", s)][m][key] for s in seeds for m in months)
    for sc in "NPS":  # S drawn last (dashed) so it stays visible when it coincides with P
        mean, lo, hi = [], [], []
        for m in months:
            m_, h = ci95([mon[(sc, s)][m][key] * scale for s in seeds])
            mean.append(m_), lo.append(m_ - h), hi.append(m_ + h)
        c, lab = SC_STYLE[sc]
        ax.plot(months, mean, color=c, lw=1.6 if sc != "S" else 1.2, label=lab, ls=(0, (4, 3)) if sc == "S" else "-", zorder=3 if sc == "S" else 2)
        ax.fill_between(months, lo, hi, color=c, alpha=0.15, lw=0)
    ax.set_xlabel("月份")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}（{group} 组，{len(seeds)} 个种子，阴影为 95% CI）", fontsize=10, pad=16)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    if same_ps:
        ax.text(0.99, 0.02, "P 与 S 逐月完全重合（规则主体不看公告）", transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="#555")
    _marks(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _paired_forest(plt, mon, summ, seeds, path, group) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 0.55 * len(PAIRED_ROWS) + 1.2))
    offs = {"S-N": -0.22, "P-N": 0.0, "P-S": 0.22}
    cols = TOKENS_LIGHT["diffs"]
    labels = []
    for i, (label, kind, key, months, scale) in enumerate(PAIRED_ROWS):
        labels.append(label)

        def v(sc, s):
            if kind == "m":
                return st.mean(mon[(sc, s)][m][key] for m in months) * scale
            return summ[(sc, s)][key] * scale
        n_level = abs(st.mean(v("N", s) for s in seeds)) or 1.0
        for d, (a, b) in (("S-N", ("S", "N")), ("P-N", ("P", "N")), ("P-S", ("P", "S"))):
            m_, h = ci95([v(a, s) - v(b, s) for s in seeds])
            y = i + offs[d]
            ax.errorbar(m_, y, xerr=h, fmt="o", ms=3.5, color=cols[d], capsize=2, lw=1,
                        label=d if i == 0 else None)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("配对差值（原单位）；横线为 95% CI")
    ax.set_title(f"预登记指标的配对差值（{group} 组，{len(seeds)} 个种子）", fontsize=10)
    ax.legend(fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _quotes(plt, runs: Path, group: str, seeds: List[int], path) -> bool:
    by = {sc: {m: [] for m in range(1, 37)} for sc in "SP"}
    for sc in "SP":
        for s in seeds:
            f = runs / f"{group}_{sc}_{s}" / "decisions.jsonl"
            if not f.exists():
                return False
            for line in f.open(encoding="utf-8"):
                r = json.loads(line)
                if r["agent_type"] != "landlord" or r["decision"] not in ("renewal_offer", "price_vacant"):
                    continue
                inp = r["inputs"]
                if inp.get("zone") in ("Z05", "Z11") and inp["current_rent"] > 0:
                    by[sc][r["month"]].append((r["output"]["rent"] - inp["current_rent"]) / inp["current_rent"] * 100)
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for sc in "SP":
        ms = [m for m in range(1, 37) if len(by[sc][m]) >= 2]
        mean = [st.mean(by[sc][m]) for m in ms]
        h = [ci95(by[sc][m])[1] for m in ms]
        c, lab = SC_STYLE[sc]
        ax.errorbar(ms, mean, yerr=h, fmt="o-", ms=3, lw=1, capsize=2, color=c, label=lab)
    ax.axhline(0, color=TOKENS_LIGHT["text"], lw=0.6)
    ax.axvspan(ANNOUNCE_M - 0.5, OPEN_M - 0.5, color=TOKENS_LIGHT["announce"], alpha=0.09)
    ax.set_xlabel("月份（阴影 = H1 检验窗口，第 13–24 月）")
    ax.set_ylabel("报价变动（%）")
    ax.set_title(f"受益区房东报价变动，P 对 S（{group} 组；误差线为报价层面 95% CI，未聚类）", fontsize=9, pad=16)
    ax.legend(fontsize=8, frameon=False, loc="upper left")
    _marks(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def _movers(plt, mon, seeds, path, group) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.6))
    for ax, key, lab in ((axes[0], "treated_move_in_incomes", "月收入（元）"), (axes[1], "treated_move_in_cash", "迁入前存款（元）")):
        data, names = [], []
        for sc in "NSP":
            vals = [v for s in seeds for m in range(13, 25) for v in mon[(sc, s)][m][key]]
            data.append(vals or [0])
            names.append(f"{sc}\n(n={len(vals)})")
        bp = ax.boxplot(data, showmeans=True, widths=0.55, patch_artist=True)
        for patch, sc in zip(bp["boxes"], "NSP"):
            patch.set_facecolor(SC_STYLE[sc][0])
            patch.set_alpha(0.35)
        ax.set_xticks([1, 2, 3])
        ax.set_xticklabels(names, fontsize=8)
        ax.set_ylabel(lab)
    fig.suptitle(f"第 13–24 月受益区迁入者构成（{group} 组，所有种子合并；三角为均值）", fontsize=10)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def _burden(plt, summ, seeds, path, group) -> bool:
    kinds = ("低价房", "便宜单间", "合租单间", "整租")
    groups = (("low", "低收入"), ("mid", "中收入"), ("high", "高收入"))
    acc = {(k, g): [0.0, 0] for k in kinds for g, _ in groups}
    for s in seeds:
        cells = summ[("N", s)].get("burden_cells")
        if cells is None:
            return False
        for key, (b, n) in cells.items():
            k, g = key.split("|")
            acc[(k, g)][0] += b * n
            acc[(k, g)][1] += n
    fig, ax = plt.subplots(figsize=(7, 3.6))
    w = 0.26
    for j, (g, gl) in enumerate(groups):
        xs, ys = [], []
        for i, k in enumerate(kinds):
            sv, n = acc[(k, g)]
            if n >= 30:
                xs.append(i + (j - 1) * w)
                ys.append(sv / n * 100)
        ax.bar(xs, ys, width=w, label=gl, color=TOKENS_LIGHT["incomeGroups"][g], alpha=0.85)
    ax.set_xticks(range(len(kinds)))
    ax.set_xticklabels(kinds)
    ax.set_ylabel("租金 / 收入（%）")
    ax.set_title(f"分房型租金负担（N 情景末 12 月，{group} 组 {len(seeds)} 个种子；不足 30 户·月不画）", fontsize=9)
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return True


def make_figures(runs: Path, group: str, out: Path, baseline_runs: Optional[Path] = None) -> List[str]:
    plt = _plt()
    out.mkdir(parents=True, exist_ok=True)
    seeds = _paired_seeds(runs, group)
    if not seeds:
        raise FileNotFoundError(f"No complete paired seeds for {group} in {runs}")
    mon = {(sc, s): _load_monthly(runs / f"{group}_{sc}_{s}") for sc in "NSP" for s in seeds}
    summ = {(sc, s): json.loads((runs / f"{group}_{sc}_{s}" / "summary.json").read_text(encoding="utf-8")) for sc in "NSP" for s in seeds}
    made = []
    _band(plt, mon, seeds, "rent_index_treated", 1.0, "租金指数（开局 = 100）", "受益区租金指数", out / "fig1_rent_index.png", group)
    made.append("fig1_rent_index.png")
    _band(plt, mon, seeds, "vacancy_treated", 100.0, "空置率（%）", "受益区空置率", out / "fig2_vacancy.png", group)
    made.append("fig2_vacancy.png")
    _paired_forest(plt, mon, summ, seeds, out / "fig3_paired_diffs.png", group)
    made.append("fig3_paired_diffs.png")
    if _quotes(plt, runs, group, seeds, out / "fig4_quotes_P_vs_S.png"):
        made.append("fig4_quotes_P_vs_S.png")
    _movers(plt, mon, seeds, out / "fig5_movein_profile.png", group)
    made.append("fig5_movein_profile.png")
    if _burden(plt, summ, seeds, out / "fig6_burden_by_kind.png", group):
        made.append("fig6_burden_by_kind.png")
    return made


def main() -> None:
    ap = argparse.ArgumentParser(description="Report figures for Lease Day v0.7")
    ap.add_argument("--runs", required=True)
    ap.add_argument("--group", choices=["R", "L", "M"], default="R")
    ap.add_argument("--out", required=True)
    ap.add_argument("--baseline-runs", default=None)
    a = ap.parse_args()
    made = make_figures(Path(a.runs), a.group, Path(a.out), Path(a.baseline_runs) if a.baseline_runs else None)
    print("wrote:", ", ".join(made), "->", a.out)


if __name__ == "__main__":
    main()
