# `pp_threshold` was never calibrated for this machine -- it's ~2-6x too high

## TL;DR

Primitive B's `pp_threshold=680` (used throughout `phase3/PrimitiveB/` and
the lever-tuning work in `phase3/ASAHI_REPORT.md`) was carried over
unchanged from the GoFetch README's macOS example invocation and never
independently measured against this machine's actual `CounterTimer`
tick rate. It should have been: on this hardware, a real L2 cache hit
reads a rock-solid **108 ticks** (zero variance across 500 samples) and
a real eviction reads **131-331 ticks** (mean 253). `680` is **2.05x the
highest evicted value ever observed** -- it sits entirely outside the
range either distribution can produce. The practical effect: the
`median_test_base >= pp_threshold` "noise environment" safety check in
`ctswap_attacker.rs` can never fire on this machine, no matter how bad
the measurement actually is, since `median_test_base` would need to
exceed 680 and nothing in 1000 samples ever got within 2x of that.

## Method

New example, `calibrate_pp.rs` (crypto_attacker crate), reusing the exact
same primitives `ctswap_attacker.rs` itself uses: `MyTimer`
(`CounterTimer`, the same busy-spin-thread AArch64 timer), and a real,
reduced L2 eviction set built via `evict_rs::eviction_set_generation`
(the project's own calibration/reduction logic, not a hand-rolled one).
For 500 iterations: load the victim and immediately re-time it (a
"cached" sample, no eviction attempt), then separately run the real
`EvictionSet::evict_and_time_once` (load, traverse the eviction set,
re-time -- the literal mechanism `ctswap_attacker.rs` uses) for an
"evicted" sample. Both written to `calibration_samples.csv`.

```bash
cd phase2/GoFetch/poc/crypto_attacker
cargo build --release --example calibrate_pp
setarch "$(uname -m)" -R ./target/release/examples/calibrate_pp 500
```

## Result

| | n | mean | std | min | max |
|---|---|---|---|---|---|
| cached | 500 | 108.0 | 0.00 | 108 | 108 |
| evicted | 500 | 252.9 | 23.09 | 131 | 331 |

The cached distribution isn't just tight -- it's **exactly 108 on every
single one of 500 samples**. The two distributions don't overlap at all:
a threshold anywhere in `[109, 130]` perfectly separates them with **zero
classification errors across all 1000 samples** (the search in
`calibrate_pp`'s analysis found the full zero-error range starts at 131,
i.e. the evicted distribution's own minimum).

`pp_threshold=680` is `2.05x` the single highest evicted sample ever
recorded, `2.69x` the evicted mean, and `6.30x` the (zero-variance!)
cached value. At `680`: `0/500` cached samples are (correctly) below it,
but **`500/500` evicted samples are also below it** -- meaning the
threshold doesn't discriminate anything in this specific check; it's
just always satisfied. `pp_threshold`'s only use in `ctswap_attacker.rs`
is the ceiling in `median_test_base >= pp_threshold` ("Noise Test
Environment" / bad-eviction-set detection) -- a genuine, designed safety
check that this machine's value has rendered permanently inert, since
nothing this project ever measured got anywhere close to 680.

## What this means for the rest of Primitive B's work

This doesn't contradict the earlier diagnosis in
`phase3/ASAHI_REPORT.md` ("the ceiling is gadget quality / search-space
noise, not a tunable classification knob") -- `diff_threshold` (the
*other* knob, tried and ruled out in lever 1) is a different parameter
from `pp_threshold`, and this calibration doesn't retroactively make
either lever's negative result wrong. What it does show is that the
*specific* safety mechanism `pp_threshold` is supposed to provide --
catching a search/measurement round where even the baseline looks
abnormally slow, e.g. from contention or a bad eviction set -- has never
actually been active during any run in this project. A properly
calibrated value (anywhere in the empty gap between 108 and 131, e.g.
`120`) would make that check meaningful for the first time, which is a
different kind of fix than either lever already tried (those adjusted
how *aggressively* to classify a signal; this adjusts whether the
noise-detection safety net exists at all). Whether that changes Primitive
B's headline TPR/FPR wasn't tested end-to-end here -- a reasonable next
step, not yet done.

## Caveats

- Measured with a single, simple L2 eviction set (12 cache lines,
  reduced from a fresh standard eviction set), not the full 64-compound-
  eviction-set search `ctswap_attacker.rs` actually runs. The *relative*
  gap (cached always ~108, evicted always well above it, both far below
  680) should generalize, since both use the identical `CounterTimer`
  and `EvictionSet` primitives, but the exact evicted-distribution
  numbers could shift slightly with a different/compound eviction set.
- Not re-validated end-to-end against a live ct-swap run (i.e., didn't
  re-run the attacker with a corrected `pp_threshold` to see if it
  changes TPR/FPR) -- this is a measurement of the timer/eviction-set
  behavior, not a confirmed improvement to the attack itself.

## Artifacts

- `calibrate_pp.rs` -- the calibration harness (lives at
  `phase2/GoFetch/poc/crypto_attacker/examples/calibrate_pp.rs` in the
  actual crate; copied here for the record).
- `calibration_samples.csv` -- the 500 raw (cached, evicted) tick pairs.
