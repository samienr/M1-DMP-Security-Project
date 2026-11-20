# Hard-pin vs. soft-hint hypothesis: tested, not confirmed

## TL;DR

`phase3/ASAHI_REPORT.md`'s Primitive A summary proposed that Linux's hard
`sched_setaffinity` pin (vs. macOS's QoS-class scheduling *hint*) might
explain why this project's Linux OOB-read accuracy (76.3%) beat the
paper's own macOS `mach_absolute_time` figure (70.2%), and resisted
in-session contention noise much better than the macOS run did (48.3%).
That was flagged explicitly as "plausible but not yet confirmed." We
built a direct test. **Result: not confirmed.** Pinned and unpinned
performed statistically indistinguishably, both at baseline and under a
synthetic CPU-saturation contention load. This is a clean negative
result, reported as one.

## Method

Added an `AUGURY_NO_PIN` environment-variable toggle to `pin_cpu()` in
`augury/util/linux-util.c`: when set, skip `sched_setaffinity` to the
single requested core and the `setpriority(-20)` boost, instead
restricting affinity to the whole Firestorm cluster (cores 4-7) --
mirroring what a QoS-class *hint* would do on macOS (bias toward the
right cluster, no hard guarantee of a specific core or elevated
priority). Normal invocations are unaffected (env var unset).

Built `oob-poc` with this change, then ran `drive_oob_poc.py` (120
trials each) in four conditions:
1. **Baseline, pinned** -- default behavior, no added load.
2. **Baseline, unpinned** -- `AUGURY_NO_PIN=1`, no added load.
3. **Contention, pinned** -- default behavior, with 4 CPU-saturating
   `yes > /dev/null` processes, one `taskset`-pinned to each of cores
   4-7 (the same cluster `oob-poc` itself uses).
4. **Contention, unpinned** -- `AUGURY_NO_PIN=1`, same contention.

## Result

| Condition | Accuracy | n |
|---|---|---|
| Baseline, pinned | 72.9% | 118 |
| Baseline, unpinned | 76.9% | 117 |
| Contention, pinned | 73.3% | 120 |
| Contention, unpinned | 75.0% | 120 |

(n is slightly below 120 in two runs because `drive_oob_poc.py` discards
a handful of trials per run on parse/timeout issues unrelated to this
test.)

Two-proportion z-tests on every pairwise comparison that matters:

```
baseline  pinned(86/118) vs unpinned(90/117):   z = -0.71
contention pinned(88/120) vs unpinned(90/120):  z = -0.29
pinned:   baseline(86/118) vs contention(88/120): z = -0.08
unpinned: baseline(90/117) vs contention(90/120): z =  0.35
```

All four `|z| < 1`, nowhere near the `|z| > 1.96` needed for p<0.05. **No
condition differs from any other in any statistically detectable way.**
If anything, unpinned slightly outperformed pinned in both the baseline
and contention conditions -- the opposite direction from the hypothesis
-- but the gap is well within noise given these sample sizes.

## Honest interpretation

This experiment does not support "Linux's hard pin explains the
better-than-paper accuracy." Two things worth being precise about,
rather than treating this as a clean refutation either:

- The synthetic contention (raw CPU-bound busy loops on the same
  cluster) may simply not replicate whatever actually degraded the
  original macOS in-session run. That could have been a different kind
  of interference entirely (I/O wait, memory-bus contention, something
  specific to this Claude Code session's own background activity) that
  a pure CPU-saturation test doesn't reproduce.
- This only tests Primitive A's OOB-read harness (`oob-poc`/`augury.c`),
  on this one machine, with this one kind of synthetic load. It doesn't
  establish that hard-pinning is *never* beneficial -- only that it
  didn't measurably matter for this specific contention scenario.

The real explanation for the Linux-vs-macOS accuracy gap remains open.
Plausible alternative candidates not tested here: `CLOCK_MONOTONIC`'s
timer resolution/granularity vs. `mach_absolute_time`'s (the user's own
early project notes flagged mach_absolute_time's ~42ns interrupt-driven
quantization as a potential factor), or something about XNU's scheduler
specifically rather than pinning mechanics in general.

## Caveats

- `AUGURY_NO_PIN`'s "unpinned" condition isn't a perfect emulation of
  macOS's QoS-class hint -- it's Linux's own CFS scheduler operating
  under a coarser (4-core) affinity mask with no priority boost, which
  is the closest analog available without actually running on macOS.
- Didn't test intermediate conditions (e.g., affinity to the single core
  without the priority boost, or vice versa) to isolate which half of
  "hard pin" (the affinity or the priority) might matter more; the
  current test only compares the two combined extremes.

## Reproduce

```bash
cd augury
make CC=gcc MACH=1 KEXT=0 bin/oob-poc   # rebuild after the linux-util.c change
cd ..
python3 phase3/PrimitiveA/drive_oob_poc.py augury/bin/oob-poc 120 out.csv --seed N
AUGURY_NO_PIN=1 python3 phase3/PrimitiveA/drive_oob_poc.py augury/bin/oob-poc 120 out.csv --seed N
# for the contention conditions, run in parallel with:
for c in 4 5 6 7; do taskset -c $c yes > /dev/null & done
# ...then kill those PIDs before the no-contention runs
```

## Artifacts

- `baseline_pinned.csv`, `baseline_unpinned.csv`, `contention_pinned.csv`,
  `contention_unpinned.csv` -- the four 120-trial per-trial result sets.
- The `pin_cpu()` change itself lives in `augury/util/linux-util.c` (not
  copied here) -- shared source, not a phase-specific output.
