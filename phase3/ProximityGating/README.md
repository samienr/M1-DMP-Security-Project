# The M1 DMP's "address-range restriction" is actually AoP-to-target proximity

## TL;DR

The Augury paper (Table II, Section VI-B) lists two *separate* requirements
for the DMP to dereference a leakage target: "be within current prefetch
distance" and "not be `0x280000000`-`0xffff3f2b0000`". We show these are
not independent. The second one is a side effect of the first, misattributed
to absolute virtual address because the paper's own test methodology (and
our initial replication of it, `phase3/AddrRangeSweep/`) always left the
pointer array (AoP) at its OS-default placement while only forcing the
target buffer's address. **When we force both the AoP and the target
buffer to the same low addresses the paper calls "not dereferenceable,"
placed close together, the DMP activates fine.** The real, previously
unquantified mechanism is a GiB-scale distance limit between the AoP and
whatever it's dereferencing -- full strength up to ~3.7 GiB apart (true
distance; see the precise-offset correction below), a sharp falloff
through ~4.5 GiB, and complete failure beyond ~4.8 GiB -- **and it's
one-directional**: the target must sit at a *higher* address than the
AoP. The same distance below the AoP never activates it at all,
confirmed at matched true distances.

## Background

This follows directly from `phase3/AddrRangeSweep/`, which replicated
(not discovered -- see that directory's own correction) the paper's
published Asahi Linux boundary at ~255.99 TiB. That whole investigation
only ever forced `data_buffer`'s address via `augury.c`'s `FORCE_ADDR`
path; the AoP itself was always `mmap(0, ...)`-allocated with no hint,
landing wherever ASLR/the kernel's top-down allocator happened to place
it (confirmed to jitter by several GiB run-to-run).

A second, finer sweep (`gradient_results.csv`/`gradient_results2.csv`,
10 trials per address instead of 1-2) found something the original
8 MiB-bisected boundary missed entirely: individual trials at a *fixed*
forced `data_buffer` address were not consistently on or off -- they were
**bimodal** (each trial landed near either ~1.0x or ~4.0x, never
in-between) with a hit *rate* that varied by address, including an
unexplained dip back to 0% hit rate at one point (`+3233 MiB` from the
boundary) sandwiched between points with much higher hit rates. Capturing
AoP's own printed address per trial (`gradient_sweep2.py`) and computing
`|aop_addr - data_buffer_addr|` showed hit-trials average 1791 MiB of
separation vs. 4096 MiB for miss-trials -- and, crucially, **this held
even within a single fixed `data_buffer` address**, where the only thing
that varied between trials was AoP's own ASLR draw (10 of 13 addresses
with enough hit/miss mixing showed cleanly smaller hit-distances than
miss-distances). That's a controlled, within-address result: distance,
not absolute position, was doing the work.

## The decisive experiment

That still left an open question: is absolute address *also* independently
required (a true two-factor model), or does proximity alone explain
everything, with the paper's boundary being a pure artifact of where
unhinted `mmap` happens to place the AoP? The only way to tell is to force
*both* buffers and test proximity independent of absolute location.

`augury.c` didn't support forcing the AoP's own address -- only
`data_buffer` had a `FORCE_ADDR` path. Added one (optional 8th CLI arg,
`aop_base_addr`; see the diff context in `augury.c` -- the AoP mmap is now
declared once and conditionally assigned rather than redeclared per
branch, to avoid a double-declaration under `-DFORCE_ADDR`). Usage:
`./bin/augury <train> <offs> <reps> <core> <density> <data_buffer_addr> [aop_addr]`.

**Test 1** -- both forced 16 MiB apart, at `0x200000000` (~8 GiB),
deep inside the paper's documented dead zone:

```
trial 1-8: train_speedup = 3.88, 3.97, 3.97, 3.98, 3.88, 4.09, 4.19, 3.99
```
8/8 strong activation.

**Test 2 (control)** -- same dead-zone region, `aop=0x200000000`,
`data_buffer=0x400000000` (~8 GiB apart):
```
trial 1-5: train_speedup = 1.007, 0.999, 1.001, 1.000, 0.996
```
5/5 no activation. Same absolute region as Test 1 -- only separation
changed. Rules out "forcing AoP's address via `MAP_FIXED` itself breaks
something" as an alternative explanation.

**Test 3** -- a second, independent low address (`aop=0x600000000`,
`data_buffer=0x601000000`, 16 MiB apart, ~24 GiB):
```
trial 1-5: train_speedup = 3.88, 4.04, 4.11, 4.25, 4.29
```
5/5 strong activation. Rules out `0x200000000` being special.

Full transcript: `decisive_experiment_log.txt`.

**This settles it: the absolute-address restriction is not real on its
own terms.** The DMP will happily dereference pointers at addresses the
paper documents as categorically excluded, provided the AoP is close
enough to them. The published boundary exists only because the paper's
(and our initial) methodology never varied AoP's own position.

## Quantifying the reach

Held `aop` fixed at `0x200000000` and swept `data_buffer`'s distance from
it (`reach_sweep.py`, 5 trials per point, both buffers at fixed, non-ASLR'd
addresses -- so unlike the earlier bimodal data, every point here is
tightly reproducible):

| Distance | mean train_speedup | range | n |
|---|---|---|---|
| 8 MiB | 3.97 | 3.93-4.02 | 5 |
| 16-3072 MiB (12 points) | 3.94-4.34 | always 3.7-4.5 | 60 |
| 3328 MiB | 2.86 | 2.84-2.90 | 5 |
| 3584 MiB | 1.84 | 1.83-1.86 | 5 |
| 3840 MiB | 1.31 | 1.30-1.32 | 5 |
| 4096 MiB | 1.00 | 1.000-1.002 | 5 |
| 8192 MiB | 1.00 | 0.997-1.000 | 5 |

A flat ~4x plateau out to at least 3 GiB, a clean monotonic decay over
roughly 3.1-3.8 GiB, then a hard floor at baseline beyond ~4 GiB. Every
point's own 5 trials cluster within a few percent of each other -- this
is a deterministic property of the (aop, data_buffer) pair's separation,
not a probabilistic one.

**This fully explains the earlier bimodal/probabilistic appearance** in
`gradient_results.csv`: those trials weren't randomly on/off at the
hardware level. AoP's own ASLR'd placement was randomly sampling
different points along this exact deterministic curve each run, since
only `data_buffer` was held fixed there.

### Correcting the "slop": the internal offset is a fixed constant, not randomness

An earlier draft of this writeup called the within-`data_buffer` pointer
offset "pseudo-random... slop." It isn't random -- `augury.c` computes
`test_idx_in_data_buffer` via a deterministic Lehmer PRNG seeded with a
constant (`rand_idx = 1`), iterated a fixed number of times set entirely
by `train_len`/`offs_past_train_buf` (both held constant at 256/1
throughout this investigation). It is **exactly the same value, every
run**: `test_idx_in_data_buffer = 93776752`, i.e. a fixed
`93776752 * 16 * 8 = 750214016` bytes (**715.46 MiB**) past
`data_buffer`'s own start. So the table above is nominal
(`data_buffer_start - aop_start`), not the true distance to the actual
dereferenced byte -- add 715.46 MiB to every row above to get the real
number. The true plateau/falloff/floor, in terms of actual
AoP-to-dereferenced-byte distance, is: **full strength to ~3.7 GiB,
falloff ~3.8-4.5 GiB, dead beyond ~4.8 GiB.**

### Directionality: the effect is one-way, not symmetric

Repeated the same sweep with `data_buffer` placed *below* `aop` instead
of above (`symmetry_sweep.py`, two fresh locations, `0x600000000` and
`0xA00000000`, 3 trials per point, 8 points from 8 MiB to 6144 MiB
nominal gap). **Every single "below" trial showed zero activation**
(train_speedup pinned at 0.95-1.06, pure noise) -- including at nominal
gaps small enough that the equivalent "above" distance sits deep in the
confirmed plateau.

That raised an obvious objection: because `data_buffer` is ~1 GiB and the
dereferenced byte sits a fixed 715.46 MiB past its start, a small nominal
"below" gap doesn't actually place the dereferenced byte 715.46 MiB
*past* `aop` the way the "above" case does -- it's a genuinely different,
smaller true distance, computed using `DATA_BUFFER_SIZE - 715.46 MiB` =
308.54 MiB past `data_buffer`'s own, lower, start. So this needed a
matched-distance control, not just matched nominal gaps.

Solved for the exact `data_buffer` addresses that place the dereferenced
byte at the *same* true distance from `aop` as two already-confirmed
active "above" points (723 MiB and 2763 MiB, both deep in the plateau):

```
db=0x5a6188000 (below, true distance 723.01 MiB): 5/5 trials, train_speedup = 1.003, 0.997, 0.999, 1.003, 0.999
db=0x526988000 (below, true distance 2763.01 MiB): 5/5 trials, train_speedup = 0.998, 1.015, 1.019, 0.998, 1.002
```

10/10 trials, zero activation, at exactly the same distances where
"above" gives a clean ~4x every time. **The AoP-to-target proximity
effect is directional: the DMP only prefetches a target at a *higher*
address than the AoP, never a lower one, independent of distance.** This
is a second, independent axis of the mechanism neither paper documents
(their own "prefetch distance" concept, Table I, is inherently
forward-only by construction -- `offs_past_train_buf` is always a
positive offset *past* the training region within the same array -- so
the question of a *target buffer* being below the AoP was never posed in
the original methodology, the same way absolute address was never
disentangled from proximity until the decisive experiment above).

## Why this is more than "the paper's boundary, replicated"

This is a different claim than `phase3/AddrRangeSweep/`'s (honest)
non-finding. That investigation reproduced a number the authors already
published. This one shows **why** that number exists, and that the
paper's own framing of it (an independent address-range restriction,
separate from -- not reducible to -- the prefetch-distance requirement
in the same table) doesn't hold up under a direct test the paper's
methodology never performs. It also gives a new, specific, quantified
number (plateau to ~3 GiB, dead beyond ~4 GiB) for a mechanism
operating at a completely different scale than the paper's own
"prefetch distance" (Table I: a maximum of 64 KiB, measured *within* the
AoP's own contiguous training sequence via the `offs_past_train_buf`
parameter -- not between the AoP and an externally-located target
buffer). These are two different mechanisms operating at a
1000x-to-50000x difference in scale (KiB vs. GiB), and the paper's own
Table II conflates the GiB-scale one with absolute address.

## Caveats / what this doesn't establish

- Only tested on this Linux/Asahi machine, with this specific kernel's
  memory layout. Whether the ~3-4 GiB reach is a true hardware constant
  (e.g., tied to TLB reach, a physical cache/memory-controller property,
  or an address-translation structure) or something contingent on this
  kernel's page-table/huge-page behavior isn't established here -- that
  would need testing on another kernel or ideally on macOS to see if the
  same GiB-scale number reproduces.
- **Resolved since the first draft:** symmetry was tested (it isn't
  symmetric -- see Directionality above) and the reach was confirmed to
  hold at two more absolute locations (`0x600000000`, `0xA00000000`),
  not just the original `0x200000000` spot-check -- all three locations
  reproduce the same plateau/falloff/floor shape in the "above"
  direction.
- Still open: whether the ~3.7-4.8 GiB reach is a true hardware constant
  (e.g., tied to TLB reach, a physical cache/memory-controller property,
  or an address-translation structure) or something contingent on this
  kernel's page-table/huge-page behavior -- would need testing on
  another kernel, or ideally macOS, to see if the same GiB-scale number
  reproduces there too.
- Still open: *why* the effect is directional. Didn't probe whether this
  tracks something like TLB/page-table walk direction, a prefetcher
  design choice to only look "ahead," or something else -- this writeup
  establishes the asymmetry empirically, not its mechanism.

## Reproduce

```bash
cd augury
make CC=gcc MACH=1 KEXT=0 FORCEADDR=1 bin/augury   # augury.c now supports forcing aop too
mkdir -p out
./bin/augury 256 1 32 4 1 0x201000000 0x200000000  # close together, "dead zone" -> activates
./bin/augury 256 1 32 4 1 0x400000000 0x200000000  # far apart, same region -> doesn't
python3 reach_sweep.py                              # full distance curve (edit AOP_ADDR/addr list as needed)
```

## Artifacts

- `augury-linux-proximity` -- built binary with both-buffer `FORCE_ADDR`
  support (supersedes `phase3/AddrRangeSweep/augury-linux`).
- `decisive_experiment_log.txt` -- Tests 1-3 full transcript.
- `gradient_sweep.py`/`gradient_results.csv` -- the 17-point, 10-trial
  sweep that first revealed bimodal (not smooth-gradient) behavior.
- `gradient_sweep2.py`/`gradient_results2.csv` -- same sweep, also
  capturing AoP's own address per trial, used for the within-address
  distance-vs-hit analysis above.
- `reach_sweep.py`/`reach_results.csv`/`reach_results2.csv` -- the
  fixed-both-buffers distance curve (coarse pass + boundary-narrowing
  pass).
- `symmetry_sweep.py`/`symmetry_results.csv`/`symmetry_results_below.csv`
  -- the above-vs-below sweep at two fresh locations that found the
  directional asymmetry.
- `directionality_matched_distance_log.txt` -- the matched-true-distance
  confirmatory runs ruling out the "below" sweep's nominal-vs-true-distance
  confound as the explanation.
- The `augury.c` change itself lives in `augury/augury.c` (not copied
  here) -- it's the project's shared source, not a phase-specific output.
