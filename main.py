"""GTA VI trophy rarity forecaster v3 (gta6-trophy-rarity-forecast-01).

For each of the game's 55 PS5 trophies, forecasts five quantiles of its
Exophase earn rate (percent) at the case target.

v3 changes over v2 (shipped, live loss 0.163 / coverage 0.436):
  * ANCHORED MEDIAN. v2 projected the median from the Theil-Sen
    intercept (median of y - slope*x over all reads). Trophy earn curves
    saturate in log time, so a line fitted through early steep reads
    overshoots the level at the horizon. v3 anchors the median at the
    LAST observed logit and extrapolates only the remaining distance:
    med = last_logit + slope * (lt_eff - lt_last). On the 14-scenario
    final-shaped synthetic suite this alone cuts mean pinball
    0.1789 -> 0.1693 (holdout 0.1692 -> 0.1594).
  * LOCAL-SLOPE BLEND. The Theil-Sen slope averages the whole history;
    near launch the recent trend matters more. v3 blends 25% of the
    last-two-states slope into the robust slope before shrinking.
    With anchoring: suite 0.1693 -> 0.1676, holdout 0.1594 -> 0.1565.
  * DETRENDED REFRESH-JUMP SPREAD. The live board shows v2 covering
    only 0.436 of answers: real refreshes move earners in per-trophy
    jumps, and v2's spread (fit residuals only) misses them. v3
    measures the refresh shock directly -- the RMS refresh-to-refresh
    logit change MINUS the trend-expected change (own slope x dlogt),
    pooled as a median over trophies -- and adds (0.5 * J)^2 to the
    spread in quadrature. Raw (undetrended) jumps double-count trend
    drift and hurt; detrended jumps cost only ~0.0007 on the smooth
    synthetic suite while insuring coverage against real refresh
    shocks. Final v3: suite 0.1683, holdout 0.1569, coverage 0.98/0.96.
  * KEPT FROM v2: pure-dilution flat-history prior (exact integer
    earners over the documented 638 -> 3868 refresh, median = the
    printed 2-decimal rate, sigma 0.05 logit); half-median-gap refresh
    shift of the effective target; players forecast by shrunk
    Theil-Sen on log players; sigma floor 0.15 / cap 1.80 logit.

What did NOT survive the ladder (all worse than v2 on both suites):
renewal-process shift, raw jump spread, residual spread term,
quadratic or linear log-earner E/P paths, per-class/global slope
shrink targets. v3 is the structural median fix plus the refresh
spread -- nothing tuned to the synthetic answers.

Python 3.13, standard library only. Deterministic, no network.
"""

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Documented launch-night refresh: page frozen at 638 players tracked,
# then refreshed to 3868. Flat-history prior: earners unchanged.
LAUNCH_PLAYERS_BEFORE = 638
LAUNCH_PLAYERS_AFTER = 3868

# v3 constants (ladder winners; see docstring).
LOCAL_BLEND = 0.25      # weight of the last-two-states slope
JUMP_SCALE = 0.5        # weight of the detrended refresh-jump spread
FLAT_SIGMA = 0.05       # flat-history spread (deterministic refresh)
FLAT_ZERO_SIGMA = 1.5   # flat history, zero earners
SIGMA_FLOOR = 0.15
SIGMA_CAP = 1.80
EXTRAP_SCALE = 0.25     # residual growth with extrapolation distance
SHRINK_K_PLAYERS = 3.0
SHRINK_K_LOGIT = 1.0


def parse_time(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def clamp_pct(x):
    return min(99.99, max(0.01, x))


def logit(pct):
    p = clamp_pct(pct) / 100.0
    return math.log(p / (1.0 - p))


def logistic(x):
    if x >= 0:
        return 100.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return 100.0 * e / (1.0 + e)


def round4(x):
    """Round to 4 decimals, half up (matches the kit starter)."""
    scaled = x * 10000.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000.0
    return int(value) if float(value).is_integer() else value


def round2(x):
    """Round to 2 decimals, half up (the page prints 2 decimals)."""
    scaled = x * 100.0
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    return whole / 100.0


def median(values):
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2:
        return vals[mid]
    return 0.5 * (vals[mid - 1] + vals[mid])


def theil_sen(xs, ys):
    """Robust line: slope = median pairwise slope, intercept = median residual."""
    n = len(xs)
    if n < 2:
        return 0.0, (ys[0] if ys else 0.0)
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            if dx != 0.0:
                slopes.append((ys[j] - ys[i]) / dx)
    slope = median(slopes) if slopes else 0.0
    intercept = median([y - slope * x for x, y in zip(xs, ys)])
    return slope, intercept


def rms_residual(xs, ys, slope, intercept):
    if len(xs) < 2:
        return 0.0
    sq = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    return math.sqrt(sq / len(xs))


def exact_earners(rate, players):
    """Integer earner count pinned by a 2-decimal printed rate.

    The consistent interval is players/10000 wide (< 1 player), so it
    holds exactly one integer; falls back to the nearest integer.
    """
    est = rate * players / 100.0
    lo = (rate - 0.005) * players / 100.0
    hi = (rate + 0.005) * players / 100.0
    cands = [n for n in range(int(math.floor(lo)), int(math.ceil(hi)) + 1)
             if lo <= n < hi]
    if len(cands) == 1:
        return cands[0]
    return int(round(est))


def distinct_states(case):
    """Collapse history to refresh points: (time, players, rates)."""
    states = []
    prev_players = None
    prev_rates = None
    for read in case.get("history", []):
        players = read.get("players_tracked")
        rates = read.get("rates")
        if players is None or rates is None:
            continue
        if prev_players is not None and players == prev_players and rates == prev_rates:
            continue
        states.append((parse_time(read["at"]), players, list(rates)))
        prev_players = players
        prev_rates = list(rates)
    return states


def forecast_case(case):
    trophies = case["trophies"]
    n_troph = len(trophies)
    levels = case.get("levels") or LEVELS
    zvals = [Z[LEVELS.index(lv)] if lv in LEVELS else 0.0 for lv in levels]
    target = parse_time(case["target"])
    states = distinct_states(case)

    if not states:
        return {"trophies": [
            {"id": t["id"], "q": [round4(logistic(logit(1.0) + z * 1.5)) for z in zvals]}
            for t in trophies
        ]}

    last_time, last_players, last_rates = states[-1]
    first_time = states[0][0]

    def logt(when):
        hours = (when - first_time).total_seconds() / 3600.0
        return math.log(1.0 + max(0.0, hours))

    if len(states) > 1:
        gaps = [
            (states[i + 1][0] - states[i][0]).total_seconds() / 3600.0
            for i in range(len(states) - 1)
        ]
        med_gap = median(gaps)
        mean_gap = sum(gaps) / len(gaps)
    else:
        med_gap = 5.0
        mean_gap = 5.0

    # The answer reflects the last refresh before the target: shift the
    # effective target earlier by half the median refresh gap (cap 12h).
    shift_hours = min(0.5 * med_gap, 12.0)
    eff_target = target - timedelta(hours=shift_hours)
    if eff_target < last_time:
        eff_target = last_time
    lt_eff = logt(eff_target)
    lt_last = logt(last_time)
    extrap = max(0.0, lt_eff - lt_last)
    logt_gap = logt(last_time + timedelta(hours=mean_gap)) - lt_last

    last_rate = [r if r is not None else 0.0 for r in last_rates]
    positive_last = [r for r in last_rate if r > 0.0]
    smallest_positive = min(positive_last) if positive_last else 1.0

    rows = []

    # --- Flat history: one distinct state. Pure dilution. ---
    if len(states) == 1:
        players_ans = last_players * (LAUNCH_PLAYERS_AFTER / LAUNCH_PLAYERS_BEFORE)
        for i, trophy in enumerate(trophies):
            rate = last_rate[i]
            if rate >= 100.0:
                rows.append({"id": trophy["id"], "q": [100.0] * len(levels)})
                continue
            earners = exact_earners(rate, last_players) if rate > 0.0 else 0
            if earners <= 0:
                med = 0.01
                sigma = FLAT_ZERO_SIGMA
            else:
                med = clamp_pct(round2(100.0 * earners / players_ans))
                sigma = FLAT_SIGMA
            qs = [round4(logistic(logit(med) + z * sigma)) for z in zvals]
            rows.append({"id": trophy["id"], "q": qs})
        return {"trophies": rows}

    # --- Rich history. ---
    xs = [logt(t) for t, _, _ in states]
    n_states = len(states)

    # Players: shrunk Theil-Sen on log players vs log time.
    log_players = [math.log(max(1, p)) for _, p, _ in states]
    p_slope_raw, p_inter_raw = theil_sen(xs, log_players)
    p_slope = p_slope_raw * (n_states / (n_states + SHRINK_K_PLAYERS))
    p_inter = median([y - p_slope * x for x, y in zip(xs, log_players)])
    p_resid = rms_residual(xs, log_players, p_slope_raw, p_inter_raw)
    players_fc = max(float(last_players), math.exp(p_inter + p_slope * lt_eff))

    # Per-trophy logit fits.
    logit_fits = []
    for i in range(n_troph):
        rx, ry = [], []
        for k, (_, _, rates) in enumerate(states):
            r = rates[i]
            if r is not None and 0.0 < r < 100.0:
                rx.append(xs[k])
                ry.append(logit(r))
        if len(rx) >= 2:
            s_raw, a_raw = theil_sen(rx, ry)
            logit_fits.append((i, rx, ry, s_raw, a_raw))
        else:
            logit_fits.append((i, rx, ry, None, None))
    raw_slopes = [s for (_, _, _, s, _) in logit_fits if s is not None]
    global_slope = median(raw_slopes) if raw_slopes else 0.0
    _res = []
    for (_, rx, ry, s_raw, a_raw) in logit_fits:
        if s_raw is not None and len(rx) >= 2:
            _res.append(rms_residual(rx, ry, s_raw, a_raw))
    global_resid = median(_res) if _res else 0.15

    # Detrended refresh-jump scale J: for each trophy, the RMS of
    # (refresh-to-refresh logit change minus trend-expected change),
    # pooled as the median over trophies. This is the refresh shock
    # the residuals cannot see.
    per_trophy_jump = []
    for (_, rx, ry, s_raw, _) in logit_fits:
        if s_raw is None or len(rx) < 2:
            continue
        dd = [(ry[k + 1] - ry[k]) - s_raw * (rx[k + 1] - rx[k])
              for k in range(len(rx) - 1)]
        if dd:
            per_trophy_jump.append(math.sqrt(sum(d * d for d in dd) / len(dd)))
    jump_scale = median(per_trophy_jump) if per_trophy_jump else 0.0

    scale = 1.0 + EXTRAP_SCALE * extrap

    def spread(sig_e, sig_p, slope_mag):
        """Quadrature spread: fit residuals + refresh staleness +
        detrended jump shock + a small base term."""
        stale = abs(slope_mag) * logt_gap
        sigma = math.sqrt(sig_e * sig_e + sig_p * sig_p
                          + stale * stale + 0.10 ** 2
                          + (JUMP_SCALE * jump_scale) ** 2)
        return min(SIGMA_CAP, max(SIGMA_FLOOR, sigma))

    for i, trophy in enumerate(trophies):
        rate = last_rate[i]
        if rate >= 100.0:
            rows.append({"id": trophy["id"], "q": [100.0] * len(levels)})
            continue

        _, rx, ry, s_raw, a_raw = logit_fits[i]
        if s_raw is not None:
            m = len(rx)
            # Local-slope blend: 25% last-two-states slope.
            slope_raw = s_raw
            if len(rx) >= 2:
                dx = rx[-1] - rx[-2]
                if dx > 0.0:
                    s_local = (ry[-1] - ry[-2]) / dx
                    slope_raw = (1.0 - LOCAL_BLEND) * s_raw + LOCAL_BLEND * s_local
            # Shrink toward zero (no class/global target survived).
            slope = slope_raw * (m / (m + SHRINK_K_LOGIT))
            # ANCHORED median: extrapolate from the last observed logit,
            # not from the fit intercept.
            med_logit = ry[-1] + slope * (lt_eff - rx[-1])
            med = clamp_pct(logistic(med_logit))
            sig_e = rms_residual(rx, ry, s_raw, a_raw) * scale
            sig_p = p_resid * scale
            sigma = spread(sig_e, sig_p, slope)
            qs = [round4(logistic(logit(med) + z * sigma)) for z in zvals]
            rows.append({"id": trophy["id"], "q": qs})
            continue

        # Fallback: too few logit points -- global slope at own level.
        earners_here = []
        for k, (_, players, rates) in enumerate(states):
            r = rates[i]
            if r is None:
                continue
            earners_here.append(int(round(r / 100.0 * players)))
        if not any(e >= 1 for e in earners_here):
            med = clamp_pct(0.5 * smallest_positive)
            qs = [round4(logistic(logit(med) + z * 1.5)) for z in zvals]
            rows.append({"id": trophy["id"], "q": qs})
            continue
        if ry:
            last_logit = ry[-1]
            last_x = rx[-1]
        else:
            last_logit = logit(rate) if 0.0 < rate < 100.0 else logit(1.0)
            last_x = lt_last
        med_logit = last_logit + global_slope * (lt_eff - last_x)
        med = clamp_pct(logistic(med_logit))
        sig_e = global_resid * scale
        sig_p = p_resid * scale
        sigma = spread(sig_e, sig_p, global_slope)
        qs = [round4(logistic(logit(med) + z * sigma)) for z in zvals]
        rows.append({"id": trophy["id"], "q": qs})

    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case)
        out = OUTPUT_DIR / (path.stem + ".out")
        out.write_text(json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
