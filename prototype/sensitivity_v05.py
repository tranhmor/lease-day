"""Uncertainty and assumption checks for Lease Day v0.5. Rule-only, no LLM."""
import math
import statistics as st

import lease_day_v05 as g

KEYS = ["commute", "low_commute", "low_cost", "revenue"]
POLICIES = ["renewal_cap", "subsidy", "subsidy_captured", "near_job_rooms", "free_fare"]
BASE_ROOMS = g.ROOMS
BASE_AFTER = g.MINUTES_AFTER
BASE_SHARE = g.JOB_SHARE_A
BASE_N = g.N_TENANTS


def runs(policy, seeds, landlord="stayer_discount"):
    return [g.Game(policy, landlord, s).run() for s in range(seeds)]


def ci(a, b, k):
    d = [x[k] - y[k] for x, y in zip(a, b)]
    return st.mean(d), 1.96 * st.stdev(d) / math.sqrt(len(d))


def reset():
    g.ROOMS, g.MINUTES_AFTER, g.JOB_SHARE_A, g.N_TENANTS = BASE_ROOMS, BASE_AFTER, BASE_SHARE, BASE_N


def part_one(seeds=300):
    base = runs("line_only", seeds)
    print(f"Differences against line_only, {seeds} paired seeds, mean and 95% interval")
    for name in ["no_line", "line_frozen"] + POLICIES:
        a = runs(name, seeds)
        cells = "  ".join(f"{k} {ci(a, base, k)[0]:+8.1f} +-{ci(a, base, k)[1]:5.1f}" for k in KEYS)
        print(f"{name:17} {cells}")


VARIANTS = {
    "base": {},
    "tight_market_122_rooms": {"rooms": {"A": {"low": (9, 700), "regular": (38, 3520)}, "B": {"low": (10, 700), "regular": (18, 2900)}, "C": {"low": (21, 700), "regular": (26, 2260)}}},
    "few_low_rooms": {"rooms": {"A": {"low": (5, 700), "regular": (45, 3520)}, "B": {"low": (6, 700), "regular": (24, 2900)}, "C": {"low": (14, 700), "regular": (36, 2260)}}},
    "more_tenants_128": {"n": 128},
    "jobs_A_60pct": {"share": 0.6},
    "small_line_saving": {"after": {"AA": 20, "BB": 20, "CC": 20, "AB": 40, "BC": 35, "AC": 63}},
    "large_line_saving": {"after": {"AA": 20, "BB": 20, "CC": 20, "AB": 30, "BC": 30, "AC": 45}},
}


def part_two(seeds=100):
    print(f"\nAssumption variants, {seeds} seeds each")
    for name, v in VARIANTS.items():
        reset()
        g.ROOMS = v.get("rooms", BASE_ROOMS)
        g.MINUTES_AFTER = v.get("after", BASE_AFTER)
        g.JOB_SHARE_A = v.get("share", BASE_SHARE)
        g.N_TENANTS = v.get("n", BASE_N)
        no = runs("no_line", seeds)
        line = runs("line_only", seeds)
        results = {p: runs(p, seeds) for p in POLICIES}
        mean = lambda rs, k: st.mean(r[k] for r in rs)
        order = sorted(POLICIES + ["line_only"], key=lambda p: mean(line if p == "line_only" else results[p], "low_cost"))
        print(f"\n{name}")
        print(f"  line effect: low commute {mean(line, 'low_commute') - mean(no, 'low_commute'):+.1f} min, low cost {mean(line, 'low_cost') - mean(no, 'low_cost'):+.0f}, "
              f"C regular {mean(line, 'after_C_regular') - mean(no, 'after_C_regular'):+.0f}, A regular {mean(line, 'after_A_regular') - mean(no, 'after_A_regular'):+.0f}, "
              f"C low {mean(line, 'after_C_low') - mean(no, 'after_C_low'):+.0f}")
        print(f"  left per run: no line {mean(no, 'left'):.1f}, line {mean(line, 'left'):.1f}; vacancy {mean(line, 'vacant'):.3f}; low share in C {mean(no, 'low_in_c'):.2f} to {mean(line, 'low_in_c'):.2f}; "
              f"A regular before line {mean(line, 'before_A_regular'):.0f}")
        print("  rank by low-income cost:", " > ".join(order))
        print(f"  near-job rooms: low commute {mean(results['near_job_rooms'], 'low_commute') - mean(line, 'low_commute'):+.1f}, revenue {mean(results['near_job_rooms'], 'revenue') - mean(line, 'revenue'):+.0f}")
    reset()


if __name__ == "__main__":
    part_one()
    part_two()
