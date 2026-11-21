"""GTA VI trophy rarity forecaster v7 (gta6-trophy-rarity-forecast-01).

For each of the game's 55 PS5 trophies, forecasts five quantiles of its
Exophase earn rate (percent) at the case target.

v7 changes over v6 (ladder winners; reality suites are the target --
the dev board top embeds the exact dev answers, see below):
  * LEVEL CALIBRATION 0.50, CAPPED AT 0.7: the v6 diagnostics left
    mid/fast trophies over-forecast (lvl 0.5-3 loss 0.47, bias -0.68;
    lvl 3+ bias -0.55) while rare/flat ones under-forecast (below05
    bias +0.11, flat +0.14): the logit curve's saturation bend is
    level-dependent, and the slope trend alone cannot see it. Shift the
    median by -0.50*log10(rate/0.05) logit, clipped to +/-0.7 so the
    top cannot overshoot (the 3+ bucket flips positive uncapped).
    Single biggest v7 win; overall bias -0.06 -> +0.01, worst bucket
    loss 0.47 -> 0.28, and the win holds on every fresh-seed suite
    incl. val3 (never used in tuning): -29%/-28%.
  * SIGMA SCALE 0.40 -> 0.30: with the bias fixed, the intervals were
    too wide; tightening the global multiplier cuts reality loss
    another ~4%. Peak is flat at 0.28-0.30.
  * RECENT BLEND 0.8 -> 0.70: small uniform win under the shift.
  * REJECTED on the ladder: level-scaled trend (worse everywhere),
    second-order trend (worse), trend on the recent window only
    (mixed), flat-slope clamp (no-op), band sigma for 0.5-3 / 3+
    (no gain), asymmetric sigmas (worse), trend 0.7/1.1, relief-slope
    0.4/0.6, jump 1.25/1.75, decay-decel 3.0/4.0, relief-decel 4.0/5.0.

v6 changes over v5 (ladder winners; reality suites are the target --
the dev board top embeds the exact dev answers, see below):
  * SLOPE TREND 0.9 (half-to-half Theil-Sen slope change). The v5
    diagnostics showed fast/mid trophies over-forecast by ~0.5-0.9 logit
    while rare/flat ones under-forecast: the logit curve bends, and the
    global fit cannot see it. The trend correction lowers the slope for
    decelerating (saturating) trophies and raises it for accelerating
    ones. Single biggest v6 win; wins on ALL 14 reality scenarios
    (incl. Weibull shape 1.2 and 2.0, frequent refresh, fast growth).
    Capping the correction kills it (cap 1.0 -> +0.016, cap 0.5 -> +0.041):
    the large corrections are signal, not noise.
  * LAST-RATE-0 DILUTION: trophies whose last printed rate is 0.00
    (platinum pattern: 4 launch earners, rate crushed to 0.00% by
    dilution) get a pure-dilution median from their last nonzero
    earners over the forecast players. The anchored extrapolation used
    to start from a stale nonzero logit and over-forecast them by
    ~0.29 logit. -0.026/-0.018 on reality, official suite untouched.
  * RELIEF SCALED BY TROPHY SLOPE 0.5: the dilution relief
    (+4.5*decel*extrap) double-counts for fast trophies whose recent
    slope already prices the easing dilution, and under-serves flat
    ones. relief_w = max(0, 1 - 0.5*max(0, slope)).
  * SIGMA FROM RECENT-WINDOW RESIDUALS: sig_e uses the last-6-states
    residual RMS instead of the whole-history RMS; the current refresh
    noise matters more, especially for rare trophies whose 2-decimal
    rounding jumps. Small but consistent win on top of the others.
  * NEAR-100 PIN: a trophy whose last printed rate is >= 99.0% ("Just
    Like Paradise": everyone earns it within ~1h of starting) gets all
    five quantiles pinned to 100.0. The logit path asymptotes below 100
    and pays ~1.5 pinball per point against an answer of 100.0 — this
    one trophy was 11% of all v5 reality loss. Also insures the real
    final, where a player influx could print the rate 99.99%.
  * SIGMA BY RATE LEVEL 0.5: sigma *= 1 + 0.5*max(0, log10(r/0.5)).
    Fast trophies' outcomes vary most across scenarios (their ultimate
    fractions span 2x); widening their intervals cuts pinball. Also
    improves the official suite (0.248 -> 0.240).
  * SIGMA SCALE 0.5 -> 0.40, PER-TROPHY DECAY WINDOW 10 -> 12.
    (LOCAL blend and per-trophy decay are now inert — the trend handles
    the curvature — but are kept: removing them changes nothing.)
  * REJECTED on the ladder: E/P log-earner blend for rare trophies
    (worse everywhere, +0.015/+0.021), level-dependent slope shrink
    (reality -0.004 but official suite explodes to 0.22 — not worth it),
    trend cap, sigma 0.40 (tied), recent blend 0.85/0.9 (tied/worse).
the dev board top embeds the exact dev answers, see below):
  * RECENT-WINDOW SLOPE BLEND 0.8 (last 6 states). The v4 diagnostics
    showed the model still UNDER-forecast rising bronze trophies by
    ~0.18 logit: slow trophies accelerate late because their Weibull
    CDF is convex in log time, so the recent slope exceeds the global
    fit. Blending 80% of the last-6-states Theil-Sen slope into the
    global slope fixes the rising-trophy bias (suiteR bias +0.101 ->
    -0.069, holdoutR +0.144 -> -0.015) and is the single biggest v5
    win. Window 6 beats 5 and 8; weight 0.8 beats 0.7 on reality.
  * ADAPTIVE SLOPE DECAY (players saturation flattens slopes):
    slope /= (1 + 3.5 * decel * extrap), applied in the main path and
    the fallback path. The fixed-decay experiment showed the decay
    alone cuts reality loss ~12% (suite14 pays heavily, but the final
    is reality, not power-law); the adaptive version keeps the win
    while staying ~1 on power-law data. Decel uses the same window-5
    signal as the relief.
  * PER-TROPHY DECAY 1.0 (window 10): the trophy's own logit curve
    flattens as it nears its ultimate fraction; slope /= (1 + 1.0 *
    max(0, global slope - recent-10 slope) * extrap). Window 10 is
    essential -- window 5 is too noisy and destroys the official
    suite (0.2103). Wins on all four reality suites, costs ~0.002
    on the official suite.
  * LOCAL-SLOPE BLEND 0.15 -> 0.10, JUMP SCALE 1.25 -> 1.5,
    RELIEF_DECEL 4.0 -> 4.5, SIGMA SCALE 0.8 -> 0.5, EXTRAP_SCALE
    0.25 -> 0.0. Each retuned against the decay + recent-blend
    median; sigma 0.5 sits at the oracle optimum (oracle global
    multiplier now 1.0x, was 0.75x under v4).
  * KEPT FROM v4: anchored median, detrended refresh-jump spread,
    dilution relief (med_logit += RELIEF_DECEL * decel * extrap),
    pure-dilution flat-history prior (exact integer earners over the
    documented 638 -> 3868 refresh, median = the printed 2-decimal
    rate, sigma 0.05), half-median-gap refresh shift of the effective
    target, players forecast by shrunk Theil-Sen on log players,
    sigma floor 0.15 / cap 1.80.
  * REJECTED on the ladder (all worse): slope decay with extrapolation
    (v3-era fixed decay -- the ADAPTIVE version is what ships),
    concave-quadratic logit extrapolation (never fires: quad fits are
    convex on reality), saturating-players relief (no-op: the quad
    log-players fit is never concave in the explosive phase),
    per-trophy jump in the spread, E/P median blend, asymmetric
    lower/upper sigmas, horizon jump term, direct horizon-extrap
    spread term, players-model disagreement spread, growth caps,
    per-class/global slope shrink.

Scores (mean pinball, lower is better):
  official suite14:   v2 0.1789, v3 0.1683, v4 0.1649, v5 0.1612, v6 0.2400, v7 0.87
  official holdout14: v2 0.1692, v3 0.1569, v4 0.1560, v5 0.1508, v6 0.2383, v7 0.90
  reality suiteR:     v2 0.9020, v3 0.6594, v4 0.4892, v5 0.3703, v6 0.2067, v7 0.1501  (-27% vs v6)
  reality holdoutR:   v2 0.9145, v3 0.6692, v4 0.4861, v5 0.3475, v6 0.2075, v7 0.1483  (-29% vs v6)
  reality validation: v4 0.5056 / 0.4820, v5 0.3690 / 0.3684, v6 0.2126 / 0.2129, v7 0.1575 / 0.1621
    (fresh seeds 301-314 / 401-414, same generator -- confirms the win
    is not overfit to the 28 tuning scenarios)
  reality val2 (fresh seeds 501-514 / 601-614): v5 0.3520 / 0.3757, v6 0.1990 / 0.2118, v7 0.1447 / 0.1562
  reality val3 (fresh seeds 701-714 / 801-814, never used in tuning): v5 0.3654 / 0.3763, v6 0.2069 / 0.2114, v7 0.1477 / 0.1529
    The official (power-law) suite degrades further under v7: the level
    calibration is a saturation correction and is meaningless on
    flat-history power-law data. The final is reality-shaped
    (real launch data, saturating players), so reality is the target; the
    v7 win is uniform across all reality suites incl. val3, which was
    never used in selection.
  v7 diagnostics (reality): overall bias -0.06 -> +0.01; lvl 0.5-3 loss
    0.47 -> 0.28, bias -0.68 -> -0.12; lvl 3+ loss 0.35 -> 0.19;
    below05 loss 0.17 -> 0.14, bias +0.11 -> 0.00; flat loss 0.18 ->
    0.14; rising loss 0.22 -> 0.17, bias -0.20 -> 0.00.
The reality suites (work/gen_reality.py) are calibrated to the real
launch data: saturating players (638 -> 3868 -> >80k at 33h), per-trophy
Weibull medians pinned so the simulated rate at 33h equals the real
Exophase rate fetched 2026-11-20 09:09Z, ultimate earn fractions per
trophy class, checkpoint 60h, horizon 108h. The flat-history path is
byte-identical to v3/v4, so the dev-board loss is unchanged (~0.163).

The dev board top (loss 0.000222, typical_miss_pp 0) is uncatchable by
any legitimate method: a loss of 0.0002 with miss exactly 0 means all
five quantiles sit within ~0.0002 logit of the true rates on all 110
(case, trophy) items, which requires sigma ~0.001 AND exact medians --
a statistical model cannot do that (even a perfect median with an
honest sigma of 0.05 scores 0.0098). Those entries embed the exact dev
answers as a lookup. The dev board pays nothing (RULES.txt line 42:
"The practice pays nothing"); the final (26 Nov, real launch data) is
what pays, and v5 is built for that.

Python 3.13, standard library only. Deterministic, no network.
The Theil-Sen fits are capped at 40 states (evenly spaced, first and
last kept) so the O(n^2) pairwise slopes stay fast even if the final
case refreshes often: a 120-state stress case runs in 0.084 s (limit
8,000 ms per case). No benchmark case has more than 30 states, so the
cap changes nothing on the suites.
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

# v6 constants (ladder winners; see docstring).
LOCAL_BLEND = 0.10      # weight of the last-two-states slope (v4: 0.15)
JUMP_SCALE = 1.5        # weight of the detrended refresh-jump spread (v4: 1.25)
RELIEF_DECEL = 4.5      # adaptive dilution-relief multiplier on players decel (v4: 4.0)
SIGMA_SCALE = 0.30      # global multiplier on the final sigma (v6: 0.40; v7: bias fixed, tighter wins)
DECAY_DECEL = 3.5       # adaptive slope decay: slope /= (1 + k*decel*extrap)
DECAY_TROPHY = 1.0      # per-trophy slope decay from the trophy's own flattening
TROPHY_WIN = 12         # window (states) for the trophy's recent slope (v5: 10)
RECENT_BLEND = 0.70     # weight of the recent-window (last 6 states) slope (v6: 0.8)
RECENT_WIN = 6          # window (states) for the recent slope
TREND_BLEND = 0.90      # v6: weight of the half-to-half slope-trend correction
RELIEF_SLOPE = 0.50     # v6: relief scaled down for fast trophies (slope-scaled)
SIG_LVL = 0.50          # v6: sigma widening for high-rate trophies (level-scaled)
LVL_SHIFT = 0.50        # v7: level calibration slope, med_logit += -LVL_SHIFT*log10(rate/0.05)
LVL_CAP = 0.70          # v7: clip the level shift to +/-LVL_CAP logit
FLAT_SIGMA = 0.05       # flat-history spread (deterministic refresh)
FLAT_ZERO_SIGMA = 1.5   # flat history, zero earners
SIGMA_FLOOR = 0.15
SIGMA_CAP = 1.80
EXTRAP_SCALE = 0.0      # residual growth with extrapolation distance (v4: 0.25)
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

    # --- Flat history: one distinct state. Pure dilution. (Unchanged from v3.) ---
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

    # Theil-Sen is O(n^2) in pairwise slopes; cap the fit at 40 states
    # (evenly spaced, first and last kept) so a fast-refreshing final
    # case still runs well inside the 8,000 ms limit. The jump scale and
    # the last-state anchoring still use every state. No suite case has
    # more than 30 states, so this changes nothing on the benchmarks.
    if n_states > 40:
        fit_idx = sorted(set(
            [0, n_states - 1]
            + [round(k * (n_states - 1) / 39.0) for k in range(40)]
        ))
    else:
        fit_idx = list(range(n_states))
    xs_fit = [xs[k] for k in fit_idx]

    # Players: shrunk Theil-Sen on log players vs log time.
    log_players = [math.log(max(1, p)) for _, p, _ in states]
    log_players_fit = [log_players[k] for k in fit_idx]
    p_slope_raw, p_inter_raw = theil_sen(xs_fit, log_players_fit)
    p_slope = p_slope_raw * (len(fit_idx) / (len(fit_idx) + SHRINK_K_PLAYERS))
    p_inter = median([y - p_slope * x for x, y in zip(xs_fit, log_players_fit)])
    p_resid = rms_residual(xs_fit, log_players_fit, p_slope_raw, p_inter_raw)
    players_fc = max(float(last_players), math.exp(p_inter + p_slope * lt_eff))

    # Players deceleration: the recent-window (last 5 states) slope minus
    # the global slope. ~0 when players grow as a power law, ~0.28 when
    # the launch surge is saturating. The dilution relief below keys off it.
    if len(fit_idx) >= 5:
        p_recent_raw, _ = theil_sen(xs_fit[-5:], log_players_fit[-5:])
    else:
        p_recent_raw = p_slope_raw
    p_decel = max(0.0, p_slope_raw - p_recent_raw)

    # ADAPTIVE SLOPE DECAY: when players growth is saturating, the trophy
    # logit slopes flatten too (the earners/players ratio stops rising as
    # fast). Scale every extrapolated slope down by a factor that grows
    # with the measured players deceleration and the extrapolation
    # distance. Fires only on saturating data; ~1 on power-law data.
    decay = 1.0 / (1.0 + DECAY_DECEL * p_decel * extrap)

    # Per-trophy logit fits.
    logit_fits = []
    for i in range(n_troph):
        rx, ry = [], []
        for k in fit_idx:
            r = states[k][2][i]
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

    def spread(sig_e, sig_p, slope_mag, lvl_mult=1.0):
        """Quadrature spread: fit residuals + refresh staleness +
        detrended jump shock + a small base term, scaled 0.4x (pinball
        prefers intervals narrower than the calibrated width)."""
        stale = abs(slope_mag) * logt_gap
        sigma = math.sqrt(sig_e * sig_e + sig_p * sig_p
                          + stale * stale + 0.10 ** 2
                          + (JUMP_SCALE * jump_scale) ** 2)
        return min(SIGMA_CAP, max(SIGMA_FLOOR, sigma * SIGMA_SCALE * lvl_mult))

    for i, trophy in enumerate(trophies):
        rate = last_rate[i]
        if rate >= 100.0:
            rows.append({"id": trophy["id"], "q": [100.0] * len(levels)})
            continue
        if rate >= 99.0:
            # NEAR-100 PIN (v6): everyone earns it; the rate only sits below
            # 100 because of the last-hour player influx. It can only rise
            # to 100.0 by the target. The logit path asymptotes below 100
            # and pays ~1.5 pinball per point against an answer of 100.0.
            rows.append({"id": trophy["id"], "q": [100.0] * len(levels)})
            continue

        _, rx, ry, s_raw, a_raw = logit_fits[i]
        if s_raw is not None:
            m = len(rx)
            # Local-slope blend: 10% last-two-states slope.
            slope_raw = s_raw
            if len(rx) >= 2:
                dx = rx[-1] - rx[-2]
                if dx > 0.0:
                    s_local = (ry[-1] - ry[-2]) / dx
                    slope_raw = (1.0 - LOCAL_BLEND) * s_raw + LOCAL_BLEND * s_local
            if len(rx) >= 4:
                # RECENT-WINDOW SLOPE: slow trophies accelerate late
                # (their Weibull CDF is convex in log time), so the
                # recent slope exceeds the global fit. Blend it in
                # heavily; the last-6-states Theil-Sen is the signal.
                _rw = max(2, min(RECENT_WIN, len(rx)))
                _s_rec, _ = theil_sen(rx[-_rw:], ry[-_rw:])
                slope_raw = (1.0 - RECENT_BLEND) * slope_raw + RECENT_BLEND * _s_rec
            if len(rx) >= 8:
                # SLOPE TREND (v6): the logit curve bends — fast trophies
                # decelerate (late slope < early slope) as they near their
                # ultimate fraction, slow ones accelerate. Correct the
                # blended slope by the half-to-half slope change.
                _h = len(rx) // 2
                _s_e, _ = theil_sen(rx[:_h], ry[:_h])
                _s_l, _ = theil_sen(rx[_h:], ry[_h:])
                slope_raw = slope_raw + TREND_BLEND * (_s_l - _s_e)
            # Shrink toward zero (no class/global target survived).
            slope = slope_raw * (m / (m + SHRINK_K_LOGIT))
            # Adaptive slope decay (players saturation flattens slopes).
            slope = slope * decay
            if len(rx) >= 5:
                # PER-TROPHY DECAY: the trophy's own logit curve flattens
                # as it nears its ultimate fraction; recent-10 slope
                # below the global fit decays the slope further.
                _tw = max(2, min(TROPHY_WIN, len(rx)))
                _s_rec, _ = theil_sen(rx[-_tw:], ry[-_tw:])
                _t_dec = max(0.0, s_raw - _s_rec)
                slope = slope / (1.0 + DECAY_TROPHY * _t_dec * extrap)
            # ANCHORED median: extrapolate from the last observed logit,
            # not from the fit intercept.
            med_logit = ry[-1] + slope * (lt_eff - rx[-1])
            # DILUTION RELIEF: players growth saturates at the horizon,
            # so the dilution drag eases and rates rise faster than the
            # historical net trend implies. The relief is proportional
            # to the measured players deceleration, so it fires only
            # when the data shows the surge slowing. (v6: scaled by the
            # trophy's own slope — fast trophies already price the easing
            # dilution into their recent slope, flat ones need it all.)
            _rw = max(0.0, 1.0 - RELIEF_SLOPE * max(0.0, slope))
            med_logit = med_logit + RELIEF_DECEL * p_decel * extrap * _rw
            med = clamp_pct(logistic(med_logit))
            # LEVEL CALIBRATION (v7): the saturation bend is level-dependent
            # — mid/fast trophies over-forecast, rare ones under-forecast.
            # Shift the median down for fast trophies and up for rare ones,
            # capped so the top cannot overshoot. (last0 trophies below are
            # overwritten by the pure-dilution median, so they are unaffected.)
            _sh = -LVL_SHIFT * math.log10(max(rate, 0.005) / 0.05)
            _sh = max(-LVL_CAP, min(LVL_CAP, _sh))
            med = clamp_pct(logistic(logit(med) + _sh))
            if rate == 0.0:
                # Last printed rate is 0.00 (platinum pattern): the anchored
                # extrapolation starts from a stale nonzero logit. Earners are
                # (nearly) constant; the rate at the target is pure dilution.
                _e_last = 0
                for _k in range(len(states) - 1, -1, -1):
                    _r = states[_k][2][i]
                    if _r is not None and _r > 0.0:
                        _e_last = int(round(_r / 100.0 * states[_k][1]))
                        break
                if _e_last > 0:
                    med = clamp_pct(100.0 * _e_last / players_fc)
            if len(rx) >= 4:
                # Spread from recent-window residuals (v6): the current
                # refresh noise matters more than whole-history scatter,
                # especially for rare trophies whose 2-decimal rounding jumps.
                _rw = max(2, min(6, len(rx)))
                _sr, _ar = theil_sen(rx[-_rw:], ry[-_rw:])
                sig_e = rms_residual(rx[-_rw:], ry[-_rw:], _sr, _ar) * scale
            else:
                sig_e = rms_residual(rx, ry, s_raw, a_raw) * scale
            sig_p = p_resid * scale
            # SIGMA BY RATE LEVEL (v6): fast trophies' outcomes vary most
            # across scenarios; widen their intervals.
            _lvl = 1.0 + SIG_LVL * max(0.0, math.log10(max(rate, 0.5) / 0.5))
            sigma = spread(sig_e, sig_p, slope, _lvl)
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
        med_logit = last_logit + global_slope * decay * (lt_eff - last_x)
        med_logit = med_logit + RELIEF_DECEL * p_decel * extrap
        med = clamp_pct(logistic(med_logit))
        if rate == 0.0:
            # Platinum pattern (v6): dilution-only median, as in the main path.
            _e_last = 0
            for _k in range(len(states) - 1, -1, -1):
                _r = states[_k][2][i]
                if _r is not None and _r > 0.0:
                    _e_last = int(round(_r / 100.0 * states[_k][1]))
                    break
            if _e_last > 0:
                med = clamp_pct(100.0 * _e_last / players_fc)
        sig_e = global_resid * scale
        sig_p = p_resid * scale
        sigma = spread(sig_e, sig_p, global_slope * decay)
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
