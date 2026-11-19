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
whatever it's dereferencing -- full strength up to ~3 GiB apart, a sharp
falloff between 3.1-3.8 GiB, and complete failure beyond ~4 GiB,
regardless of where in the address space the pair sits.

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
not a probabilistic one. (The within-`data_buffer`-sized-1024MiB-buffer
offset of the actual dereferenced pointer value adds some slop to the
precise falloff numbers -- the pointer stored in the AoP targets a
pseudo-random offset inside `data_buffer`'s 1 GiB span, not necessarily
its start -- but the qualitative plateau/falloff/floor shape is clear
regardless.)

**This fully explains the earlier bimodal/probabilistic appearance** in
`gradient_results.csv`: those trials weren't randomly on/off at the
hardware level. AoP's own ASLR'd placement was randomly sampling
different points along this exact deterministic curve each run, since
only `data_buffer` was held fixed there.

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
- Didn't test whether the plateau/falloff shape is symmetric (data_buffer
  below vs. above aop) or whether 3-4 GiB holds at other absolute
  locations beyond the two spot-checked (`0x200000000`, `0x600000000`) --
  reasonable next steps if this gets written up further.
- The exact falloff numbers have some slop from the pointer's
  pseudo-random offset within `data_buffer`'s own 1 GiB span (noted
  above); a tighter measurement would force the exact dereferenced
  offset rather than a random one within the 1 GiB window.

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
- The `augury.c` change itself lives in `augury/augury.c` (not copied
  here) -- it's the project's shared source, not a phase-specific output.
