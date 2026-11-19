# M4 Augury existence-sweep -- final report

Source data: `sweep_results_20261116_225006/sweep.csv`
Failed/missing runs excluded from analysis: 0

Activation criterion (Augury paper): speedup > 2.0x AND AOP time < 150.0 ns.

## Per-training-size summary (this M4 sweep)

| Train | Offsets tested | Activating offsets | Median activating speedup | Median activating AOP (ns) |
|---|---|---|---|---|
| 1 | 16 | 0 | -- | -- |
| 2 | 16 | 0 | -- | -- |
| 4 | 16 | 0 | -- | -- |
| 8 | 16 | 0 | -- | -- |
| 16 | 16 | 0 | -- | -- |
| 32 | 16 | 0 | -- | -- |
| 64 | 16 | 0 | -- | -- |
| 128 | 16 | 0 | -- | -- |
| 256 | 16 | 0 | -- | -- |
| 512 | 16 | 0 | -- | -- |
| 1024 | 16 | 0 | -- | -- |
| 2048 | 16 | 0 | -- | -- |
| 4096 | 16 | 0 | -- | -- |
| 8192 | 16 | 0 | -- | -- |

## M1 reference (Augury_M1_Existence_Summary report)

| Train | Activating offsets | Median activating speedup | Median activating AOP (ns) |
|---|---|---|---|
| 1 | 0 | -- | -- |
| 2 | 1 | 4.0x | 87 |
| 4 | 2 | 4.0x | 102 |
| 8 | 0 | -- | -- |
| 16 | 1 | 5.4x | 127 |
| 32 | 9 | 8.4x | 74 |
| 64 | 7 | 6.6x | 90 |
| 256 | 9 | 16.3x | 42 |
| 1024 | 14 | 5.7x | 92 |
| 8192 | 19 | 3.8x | 46 |

## Verdict

Across all 224 (train, offset) configurations tested on the M4 in this sweep, **none met the paper's activation criterion** (speedup > 2.0x and AOP < 150.0 ns).

**This does not, by itself, establish that the M4 lacks a DMP, and it does not establish that the M4 is simply faster than the M1.** If AOP and baseline measurements continue to land in the same narrow nanosecond band (as in earlier M4 samples from this project), that pattern is equally consistent with a timer-resolution or measurement-harness limitation as with a genuine hardware difference -- and this sweep uses the same timing primitive (`mach_absolute_time`) as every prior M4 run, so it cannot resolve that ambiguity on its own. Treat this report as the authoritative result of the `existence_fast.sh`-style sweep for this project's M4 testing, not as an independently verified hardware conclusion about the M4's prefetcher.

## Residual limitations not addressed by this sweep
- `CORE=7` is a QoS-class hint to the scheduler, not a guarantee of which physical P-core/E-core the process actually ran on; `environment.txt` records this run's `hw.perflevel0.physicalcpu` / `hw.perflevel1.physicalcpu` counts, but core residency during execution was not independently confirmed (e.g. via `powermetrics`).
- The M1 reference table above reports each training size's own best/median offset, not necessarily the same offsets tested on the M4 -- a true matched comparison would need to compare specific (train, offset) pairs from `by_config.csv` against the M1 report's raw per-offset data, not its summary table.
- Whether the measured 0-42 ns banding on the M4 (if reproduced here) reflects timer quantization, cache/warmup ordering in the harness, or something else about the chip was never resolved by inspecting `oob-poc.c`'s timing and baseline code directly; this sweep only produces more samples of the same measurement, not that investigation.
