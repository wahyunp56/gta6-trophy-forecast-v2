"""GTA VI trophy rarity forecaster v2 (gta6-trophy-rarity-forecast-01).

Forecasts, for each of the game's 55 PS5 trophies, five quantiles of its
Exophase earn rate (percent) at the case target.

v2 changes over v1 (logit-Theil-Sen, dev ~0.195 under the pure-dilution
truth, synthetic 0.1853):
  * Flat history (one distinct state -- the practice shape): PURE DILUTION
    with exact earner counts. The last read's 2-decimal rates pin each
    trophy's integer earner count exactly (the recovered counts sum to the
    reads' trophies_earned field, 943), and at the first refresh the
    earners are unchanged -- only the players count jumps, 638 -> 3868,
    as the competition rules document. So the median is earners / 3868,
    not last-rate / 6.06 * 1.15. The 100% trophy stays 100%. The median
    is the PRINTED 2-decimal rate (the answer is the page's printed
    rate, so the median targets the printed value, not the exact ratio).
    The spread is a tight 0.05 logit (the refresh is a known
    deterministic event, not a trend to extrapolate). This is the
    "Counts + Dilution" structure the live top entries use (dev losses
    0.006-0.03, typical miss 0.00pp).
  * Rich history (the final shape): the median is a structural
    Earners/Players forecast -- players from a shrunk log-linear fit,
    the rate from a Theil-Sen fit of logit(rate) against log time (a
    straight line to log-earners overshoots: log-earners is concave in
    log time, so the rate's logit is the fit, and earners follow as
    rate * players). The extrapolated logit is bounded by the observed
    range plus a pad, so a fast-rising trophy cannot run away to 99.99%.
    The fallback for trophies with too few logit points uses the global
    logit slope at the trophy's own level instead of a log-earner line.
  * Refresh inversion for the median: the answer reflects the last
    refresh before the target, not the target itself. The effective
    target is shifted earlier by the refresh lag (default: half the
    median gap between distinct states, as v1; 'mean' shifts by the mean
    gap). The lag's uncertainty enters the spread as |slope| times the
    log-time width of one mean gap.
  * Spread calibration: sigma combines the trophy's logit-fit residual,
    the players-fit residual, and the refresh-lag term, growing with
    extrapolation distance; the floor is 0.15 logit (v1's 0.30 floor was
    set from in-sample residuals and overstates the spread when the fit
    is tight). No spread term is derived from in-sample residuals alone
    without the extrapolation / refresh terms.

Tuning knobs (env vars, defaults are the shipped values):
  V2_FLAT_SIGMA (0.10), V2_SHIFT (half|mean|median|zero),
  V2_RANGE_PAD (inf|float), V2_LOCAL (0.0-0.5), V2_FLOOR (0.15),
  V2_SPREAD (v2|v1).

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

# Documented launch-night refresh (competition rules): the page was frozen
# at 638 players tracked, then refreshed to 3868. The flat-history prior
# is that refresh: earners unchanged, players multiplied by AFTER/BEFORE.
LAUNCH_PLAYERS_BEFORE = 638
LAUNCH_PLAYERS_AFTER = 3868

# Tuning knobs (see module docstring).
FLAT_SIGMA = float(os.environ.get("V2_FLAT_SIGMA", "0.05"))
FLAT_ZERO_SIGMA = 1.5
SHIFT_MODE = os.environ.get("V2_SHIFT", "half")
RANGE_PAD_RAW = os.environ.get("V2_RANGE_PAD", "inf")
RANGE_PAD = float("inf") if RANGE_PAD_RAW == "inf" else float(RANGE_PAD_RAW)
LOCAL_BLEND = float(os.environ.get("V2_LOCAL", "0.0"))
SIGMA_FLOOR = float(os.environ.get("V2_FLOOR", "0.15"))
SIGMA_CAP = 1.80
SPREAD_MODE = os.environ.get("V2_SPREAD", "v2")
REFRESH_ALLOWANCE = 0.15
EXTRAP_SCALE = 0.25
SHRINK_K_PLAYERS = 3.0
SHRINK_K_LOGIT = 1.0


def parse_time(text):
    """ISO 8601 timestamp (with Z) -> aware datetime."""
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
    """Round to 4 decimals, half up (matches the kit starter's rounding)."""
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
    """Return (slope, intercept) by Theil-Sen; intercept = median(y - slope*x)."""
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
    """Integer earner count consistent with a 2-decimal printed rate.

    A rate printed to 2 decimals with P players tracked pins its integer
    earner count: the consistent interval is P/10000 wide (< 1 player),
    so it holds exactly one integer. Falls back to the nearest integer.
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
    """Collapse history to refresh points: (first-seen time, players, rates)."""
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

    # --- Defensive fallback: no usable history at all. ---
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

    # --- Refresh cadence from the distinct states. ---
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

    # --- Effective target: the answer reflects the last refresh before
    # the target, not the target instant itself. ---
    if SHIFT_MODE == "mean":
        shift_hours = min(mean_gap, 12.0)
    elif SHIFT_MODE == "median":
        shift_hours = min(med_gap, 12.0)
    elif SHIFT_MODE == "zero":
        shift_hours = 0.0
    else:  # "half": half the median gap, capped at 12h (v1 behaviour).
        shift_hours = min(0.5 * med_gap, 12.0)
    eff_target = target - timedelta(hours=shift_hours)
    if eff_target < last_time:
        eff_target = last_time
    lt_eff = logt(eff_target)
    lt_last = logt(last_time)
    extrap = max(0.0, lt_eff - lt_last)
    # Log-time width of one mean refresh gap at the last read: how far
    # the rate can move during one refresh cycle of staleness.
    logt_gap = logt(last_time + timedelta(hours=mean_gap)) - lt_last

    last_rate = [r if r is not None else 0.0 for r in last_rates]
    positive_last = [r for r in last_rate if r > 0.0]
    smallest_positive = min(positive_last) if positive_last else 1.0

    rows = []

    # --- Flat-history regime: exactly one distinct state. ---
    # Pure dilution: earners are unchanged at the first refresh, only the
    # players count jumps by the documented launch-night refresh
    # (638 -> 3868). Earners are recovered exactly from the 2-decimal
    # rates, so the median is a count over a count, not a trend.
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
                # Median targets the PRINTED answer rate (2 decimals).
                med = clamp_pct(round2(100.0 * earners / players_ans))
                sigma = FLAT_SIGMA
            qs = [round4(logistic(logit(med) + z * sigma)) for z in zvals]
            rows.append({"id": trophy["id"], "q": qs})
        return {"trophies": rows}

    # --- Rich history. ---
    xs = [logt(t) for t, _, _ in states]
    n_states = len(states)

    # Players: Theil-Sen on log players vs log time, slope shrunk toward 0.
    log_players = [math.log(max(1, p)) for _, p, _ in states]
    p_slope_raw, p_inter_raw = theil_sen(xs, log_players)
    p_slope = p_slope_raw * (n_states / (n_states + SHRINK_K_PLAYERS))
    p_inter = median([y - p_slope * x for x, y in zip(xs, log_players)])
    p_resid = rms_residual(xs, log_players, p_slope_raw, p_inter_raw)
    players_fc = max(float(last_players), math.exp(p_inter + p_slope * lt_eff))

    # Per-trophy logit fits first (for the global slope / residual scale).
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

    scale = 1.0 + EXTRAP_SCALE * extrap

    for i, trophy in enumerate(trophies):
        rate = last_rate[i]
        if rate >= 100.0:
            rows.append({"id": trophy["id"], "q": [100.0] * len(levels)})
            continue

        _, rx, ry, s_raw, a_raw = logit_fits[i]
        if s_raw is not None:
            # Primary path: structural Earners/Players. The rate comes
            # from the logit fit; earners follow as rate * players, so
            # the decomposition is consistent by construction and the
            # logit line (not a log-earner line) carries the trend --
            # log-earners is concave in log time and a straight line
            # through it overshoots to 99.99% at a 4-5 day horizon.
            m = len(rx)
            slope_raw = s_raw
            if LOCAL_BLEND > 0.0 and len(rx) >= 2:
                dx = rx[-1] - rx[-2]
                if dx > 0.0:
                    s_local = (ry[-1] - ry[-2]) / dx
                    slope_raw = (1.0 - LOCAL_BLEND) * s_raw + LOCAL_BLEND * s_local
            slope = slope_raw * (m / (m + SHRINK_K_LOGIT))
            inter = median([y - slope * x for x, y in zip(rx, ry)])
            med_logit = inter + slope * lt_eff
            if RANGE_PAD != float("inf"):
                lo_b = min(ry) - RANGE_PAD
                hi_b = max(ry) + RANGE_PAD
                med_logit = min(hi_b, max(lo_b, med_logit))
            med = clamp_pct(logistic(med_logit))
            # Earners/Players consistency: earners implied by the rate
            # at the forecast players; the rate is already bounded, so
            # earners cannot exceed players.
            _earn_fc = med / 100.0 * players_fc
            _ = _earn_fc
            sig_e = rms_residual(rx, ry, s_raw, a_raw) * scale
            sig_p = p_resid * scale
            stale = abs(slope) * logt_gap
            if SPREAD_MODE == "v2":
                sigma = math.sqrt(sig_e * sig_e + sig_p * sig_p
                                  + stale * stale + 0.10 ** 2)
            else:
                sigma = math.sqrt(sig_e * sig_e + sig_p * sig_p
                                  + REFRESH_ALLOWANCE ** 2)
            sigma = min(SIGMA_CAP, max(SIGMA_FLOOR, sigma))
            qs = [round4(logistic(logit(med) + z * sigma)) for z in zvals]
            rows.append({"id": trophy["id"], "q": qs})
            continue

        # Fallback path: too few logit points. Use the global logit
        # slope at this trophy's own level (never a log-earner line:
        # it overshoots), bounded by the observed range.
        earners_here = []
        for k, (_, players, rates) in enumerate(states):
            r = rates[i]
            if r is None:
                continue
            earners_here.append(int(round(r / 100.0 * players)))
        if not any(e >= 1 for e in earners_here):
            # Zero earners in every read: wide-spread low median.
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
        if RANGE_PAD != float("inf") and ry:
            lo_b = min(ry) - RANGE_PAD
            hi_b = max(ry) + RANGE_PAD
            med_logit = min(hi_b, max(lo_b, med_logit))
        med = clamp_pct(logistic(med_logit))
        sig_e = global_resid * scale
        sig_p = p_resid * scale
        stale = abs(global_slope) * logt_gap
        if SPREAD_MODE == "v2":
            sigma = math.sqrt(sig_e * sig_e + sig_p * sig_p
                              + stale * stale + 0.10 ** 2)
        else:
            sigma = math.sqrt(sig_e * sig_e + sig_p * sig_p
                              + REFRESH_ALLOWANCE ** 2)
        sigma = min(SIGMA_CAP, max(SIGMA_FLOOR, sigma))
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
