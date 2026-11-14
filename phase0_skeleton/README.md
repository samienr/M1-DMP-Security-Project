# Phase 0 Skeleton

Minimal scaffold matching the Phase 0 deliverable: pin to a P-core,
time a memory access, build a (non-minimal) eviction set.

## Build

    make

## Run

    ./phase0_skeleton

Expected output: timer calibration numbers, a confirmation that
QOS_CLASS_USER_INTERACTIVE was requested, a warm-access latency in ns,
and a rough evicted/not-evicted guess. The numbers matter more than
the yes/no right now -- see "What to do with the first run" below.

## What this is NOT yet

- **Not a minimal/congruent-class eviction set.** `evset_build_bruteforce`
  just thrashes with a big pool. For anything L2-set-targeted (needed
  for Prime+Probe against a specific line, and for GoFetch's compound
  eviction sets in Phase 3), you need the congruent-class construction
  from Vila et al. (referenced as [85] in GoFetch, [46] in Augury):
  start from a candidate pool, find one address that evicts a known
  target, then prune the candidate set down while preserving that
  conflict. Build this once Phase 1 needs real Prime+Probe.
- **Not hard core affinity.** QoS is a scheduler hint on Apple Silicon,
  not a guarantee. Verify empirically (see core_pin.c comment) rather
  than assuming it held.
- **Not PMC-based.** This uses `mach_absolute_time` only, per the
  project's Phase 0 decision to not assume `kperf` access. If you
  later confirm `kperf` access works for you, add a PMC-based timer
  path and keep this one as the fallback/cross-check -- Augury and
  GoFetch both report using both timers for different purposes.

## What to do with the first run

1. Run it 20-30 times, record `warm (hit) access latency` each time.
2. Separately, measure a guaranteed-miss latency: allocate a buffer
   much larger than L2 (tens of MB), stream through it, then time an
   access to `target` right after. That's your miss baseline.
3. Pick a threshold roughly halfway between the hit and miss medians.
   Hardcode nothing until you've looked at your own distributions --
   your M1 and M4 Pro will likely need different thresholds, and
   that's expected (chip-generation differences are part of your
   Phase 4 novel investigation).

## Next, outside this skeleton

- Clone Augury's tooling and read through it before extending this:
  https://github.com/FPSG-UIUC/augury
- Clone GoFetch's PoC repo (linked from https://gofetch.fail) --
  their eviction-set and Prime+Probe code is a superset of what
  Augury needed and is the better reference for compound eviction
  sets in Phase 3.
- If/when you investigate `kperf` access, do it as a side experiment,
  not a blocker: confirm feasibility, then decide whether it's worth
  switching your main experiments over to it.
