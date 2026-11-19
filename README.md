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
per case. Deterministic, ~0.03 s per case.

## Method (v2)

- Collapse the read history to distinct states (Exophase refresh points):
  identical consecutive reads are one stale page, not new information.
- Work in log time, `log(1 + hours since the first read)`, and extrapolate
  to an effective target shifted earlier by half the median refresh gap
  (the answer reflects the last refresh before the target).
- Median rate per trophy: a structural Earners/Players forecast. Players
  come from a shrunk log-linear fit; the rate comes from a Theil–Sen fit
  of the logit's rate against log time (a straight line to log-earners
  overshoots: log-earners is concave in log time, so the rate's logit is
  the fit and earners follow as rate × players). The extrapolated logit
  is bounded by the observed range plus a pad (off by default: the pad
  hurt on the synthetic suite). The fallback for trophies with too few
  logit points uses the global logit slope at the trophy's own level.
- Spread on the logit scale: residual scatter of the trophy's logit fit
  plus residual scatter of the log-players fit (both vs their raw fits,
  growing with extrapolation distance) plus a refresh-lag term
  (|slope| × one mean refresh gap in log time), root-sum-of-squares,
  floored at 0.15 and capped at 1.80.
- Flat history (one distinct state, as in the practice cases): PURE
  DILUTION with exact earner counts. The last read's 2-decimal rates pin
  each trophy's integer earner count exactly (they sum to the reads'
  `trophies_earned` field), and at the first refresh the earners are
  unchanged — only the players count jumps, 638 → 3868, as the
  competition rules document. So the median is the PRINTED 2-decimal
  rate of earners / 3868, with a tight 0.05 logit spread. A trophy at
  100% stays at 100%. This is the "Counts + Dilution" structure the
  live top entries use (dev losses 0.006–0.03, typical miss 0.00pp).

Validated on the kit practice cases (valid, deterministic) and on a
14-scenario synthetic final-like suite (mean pinball loss 0.179, vs 0.966
for the house baseline and 0.344 for a logit-trend OLS baseline — better
than both on every scenario). Practice dev loss under the pure-dilution
truth: 0.0098 (v1: 0.1950); the 0.30 spread floor and the 1.15 earner
growth in v1's flat prior were the whole gap.
