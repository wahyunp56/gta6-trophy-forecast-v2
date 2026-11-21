# gta6-trophy-forecast

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/wahyunp56/gta6-trophy-forecast/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/wahyunp56/gta6-trophy-forecast/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Entry for the [make.fun](https://make.fun) competition
**gta6-trophy-rarity-forecast-01**: forecast, for every one of GTA VI's 55
PlayStation 5 trophies, five quantiles of its Exophase earn rate (percent)
at the target instant. Scored by mean pinball loss on the logit scale.

## Run

```sh
mkdir -p out
MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

`main.py` (Python 3.13, standard library only, no network) reads every
`*.in` case file in the input directory and writes one `*.out` forecast
per case. Deterministic, ~0.03 s per case (a 120-state stress case runs
in 0.067 s; the grader limit is 8,000 ms per case).

## Method (v6)

- Collapse the read history to distinct states (Exophase refresh points):
  identical consecutive reads are one stale page, not new information.
- Work in log time, `log(1 + hours since the first read)`, and extrapolate
  to an effective target shifted earlier by half the median refresh gap
  (the answer reflects the last refresh before the target).
- Median rate per trophy: an ANCHORED Theil–Sen fit of the rate's logit
  against log time — anchored at the LAST observed logit, not the fit
  intercept (earn curves saturate in log time, so a line fitted through
  early steep reads overshoots), with a 10% blend of the last-two-states
  local slope, an 80% blend of the last-6-states recent slope (slow
  trophies accelerate late — their Weibull CDF is convex in log time),
  shrinkage toward zero, an adaptive slope decay
  `slope /= (1 + 3.5 * decel * extrap)` (players saturation flattens
  slopes), and a per-trophy decay from the trophy's own recent-12 slope
  flattening.
- SLOPE TREND (the v6 core): the logit curve bends, so the global fit
  cannot see it — fast trophies decelerate as they near their ultimate
  fraction while slow ones accelerate. v6 corrects the blended slope by
  0.9× the half-to-half Theil–Sen slope change. It wins on ALL 14
  reality scenarios (incl. Weibull shape 1.2 and 2.0, frequent refresh,
  fast growth); capping the correction kills it (cap 1.0 → +0.016),
  so the large corrections are signal, not noise.
- LAST-RATE-0 DILUTION: a trophy whose last printed rate is 0.00%
  (platinum pattern) gets a pure-dilution median from its last nonzero
  earners over the forecast players — the anchored extrapolation used
  to start from a stale nonzero logit (bias −0.29 → 0.00).
- NEAR-100 PIN: a trophy at ≥ 99.0% ("Just Like Paradise": everyone
  earns it) gets all five quantiles pinned to 100.0 — the logit path
  asymptotes below 100 and pays ~1.5 pinball per point against an
  answer of 100.0. That one trophy was 11% of all v5 reality loss.
- DILUTION RELIEF, slope-scaled (v6): the relief `+4.5 * decel * extrap`
  is multiplied by `max(0, 1 − 0.5 * max(0, slope))` — fast trophies
  already price the easing dilution into their recent slope, flat ones
  need the full relief.
- Spread on the logit scale: residual scatter of the trophy's logit fit
  (v6: recent-window, last-6-states residuals — the current refresh
  noise matters more than whole-history scatter) plus residual scatter
  of the log-players fit (both vs their raw fits, growing with
  extrapolation distance) plus a refresh-lag term
  (|slope| × one mean refresh gap in log time) plus the detrended
  refresh-jump shock (RMS refresh-to-refresh logit change minus the
  trend-expected change, pooled as the median over trophies, weight
  1.5), root-sum-of-squares, floored at 0.15 and capped at 1.80, then
  scaled 0.40×, with a rate-level widening `× (1 + 0.5 * max(0,
  log10(rate / 0.5)))` — fast trophies' outcomes vary most across
  scenarios.
- ADAPTIVE DILUTION RELIEF (the v4 core): the players count is in its
  explosive launch phase (638 → 3868 in 4.7 h, past 80,000 by 33 h — the
  platinum sat at 0.63% = 4 earners at launch and 0.00% now, and earners
  never decrease, so P > 80,000). Launch-week sales are front-loaded, so
  that growth MUST saturate, and the dilution drag eases at the 4.5-day
  horizon: rates rise faster than the historical net trend implies.
  v4 adds the relief back — `med_logit += 4.5 * decel * extrap`, where
  `decel = max(0, global players slope − recent-5-states players slope)`.
  The deceleration is ~0.28 on saturating players and ~0.00 on power-law
  players, so the relief fires on the real (saturating) final and stays
  silent on power-law data. (v6 scales it by the trophy's own slope —
  see above.)
- Flat history (one distinct state, as in the practice cases): PURE
  DILUTION with exact earner counts. The last read's 2-decimal rates pin
  each trophy's integer earner count exactly (they sum to the reads'
  `trophies_earned` field), and at the first refresh the earners are
  unchanged — only the players count jumps, 638 → 3868, as the
  competition rules document. So the median is the PRINTED 2-decimal
  rate of earners / 3868, with a tight 0.05 logit spread. A trophy at
  100% stays at 100%. The flat path is byte-identical to v3/v4/v5, so the
  dev-board loss is unchanged.

## Scores (mean pinball, lower is better)

| suite | v2 | v3 | v4 | v5 | v6 |
|---|---|---|---|---|---|
| official suite14 | 0.1789 | 0.1683 | 0.1649 | 0.1612 | 0.2400 |
| official holdout14 | 0.1692 | 0.1569 | 0.1560 | 0.1508 | 0.2383 |
| reality suiteR | 0.9020 | 0.6594 | 0.4892 | 0.3703 | **0.2067** |
| reality holdoutR | 0.9145 | 0.6692 | 0.4861 | 0.3475 | **0.2075** |
| reality validation (fresh seeds) | — | — | 0.5056 / 0.4820 | 0.3690 / 0.3684 | **0.2126 / 0.2129** |
| reality val2 (fresh seeds 501–514 / 601–614) | — | — | — | 0.3520 / 0.3757 | **0.1990 / 0.2118** |
| reality val3 (fresh seeds 701–714 / 801–814, never used in tuning) | — | — | — | 0.3654 / 0.3763 | **0.2069 / 0.2114** |

The official suites are the v3 builder's 14-scenario power-law-players
suites. The reality suites (`work/gen_reality.py`) are calibrated to the
real launch data: saturating players (638 → 3868 → >80k at 33 h),
per-trophy Weibull medians pinned so the simulated rate at 33 h equals
the real Exophase rate fetched 2026-11-20 09:09Z, ultimate earn fractions
per trophy class, checkpoint 60 h, horizon 108 h. The validation suites
use fresh seeds (301–314 / 401–414) from the same generator, plus two
more fresh families (val2, val3) — the v6 win is confirmed on 84 unseen
scenarios, not overfit to the tuning set. The official (power-law) suite
degrades under v6 (the trend correction adds noise where logit curves do
not bend); the final is reality-shaped, so reality is the target.

## The dev board top is uncatchable — and it pays nothing

The live top entries score 0.000222 with typical miss exactly 0.00 pp.
A loss of 0.0002 with miss 0 means all five quantiles sit within
~0.0002 logit of the true rates on all 110 (case, trophy) items, which
requires sigma ≈ 0.001 AND exact medians. A statistical model cannot do
that (even a perfect median with an honest sigma of 0.05 scores 0.0098).
Those entries embed the exact dev answers as a lookup table. The dev
board pays nothing (RULES.txt: "The practice pays nothing"). The final
(26 Nov, real launch data) is what pays — a prize needs a loss strictly
below the best house entry — and v6 is built for that: on the
reality-calibrated final-shaped suites it beats v5 by 40–44% (and the
win is confirmed on three fresh validation seed families).

## Status

- v2 SUBMITTED (claim AF-RTYBB-JGG3Q-P4B12-DJ913): live #1,072/6,662,
  loss 0.163. v3 built (suite 0.1683 / holdout 0.1569), NOT submitted.
- v4 built (suiteR 0.4892 / holdoutR 0.4861), NOT submitted — superseded
  by v5.
- v5 built (suiteR 0.3703 / holdoutR 0.3475, validation 0.3690 / 0.3684),
  NOT submitted — superseded by v6.
- v6 built (suiteR 0.2067 / holdoutR 0.2075, validation 0.2126 / 0.2129,
  val2 0.1990 / 0.2118, val3 0.2069 / 0.2114), NOT submitted. Entries
  close 21 Nov 18:30 WIB; submits used 1 of max 3. Final window starts
  21 Nov 11:30 UTC; result ~10 Dec.
